from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.billing_repo import BillRepository
from app.repositories.master_repo import CustomerRepository, SupplierRepository
from app.repositories.procurement_repo import ProcurementRepository
from app.services.ledger_service import LedgerService
from app.database.connection import transactional

class PaymentService:
    def __init__(self, db: Any):
        self.db = db
        self.acc_repo = AccountingRepository(db)
        self.bill_repo = BillRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.proc_repo = ProcurementRepository(db)
        self.ledger = LedgerService(db)

    # ---------------- CUSTOMER PAYMENTS (AR) ----------------
    @transactional
    def record_customer_payment(
        self,
        customer_id: str,
        amount: float,
        payment_method: str = "Cash",
        reference_no: Optional[str] = None,
        invoice_no: Optional[str] = None,
        notes: str = "",
        user_id: str = "system"
    ) -> Dict[str, Any]:
        """Record customer payment receipt, allocate to invoices (FIFO or specific), and reduce AR balance."""
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        customer = self.cust_repo.find_one({"cust_id": customer_id})
        if not customer:
            raise ValueError(f"Customer '{customer_id}' not found")

        remaining = amount
        allocations = []

        if invoice_no:
            # Specific invoice allocation
            bill = self.bill_repo.find_one({"invoice_no": invoice_no, "is_deleted": 0})
            if not bill:
                raise ValueError(f"Invoice '{invoice_no}' not found")
            due = float(bill.get("balance_due", 0.0))
            if amount > due:
                raise ValueError(f"Allocation amount {amount:.2f} exceeds invoice balance due {due:.2f}")

            alloc_amt = min(amount, due)
            allocations.append({"invoice_id": invoice_no, "amount": alloc_amt})
            new_due = due - alloc_amt
            new_status = "paid" if new_due == 0 else "partial"
            self.bill_repo.update_one({"invoice_no": invoice_no}, {"$set": {"balance_due": new_due, "status": new_status}})
            remaining -= alloc_amt
        else:
            # Automatic FIFO allocation across open bills
            open_bills = self.bill_repo.find(
                {"customer_id": customer_id, "status": {"$in": ["unpaid", "partial"]}, "is_deleted": 0},
                sort=[("created_at", 1)]
            )
            for b in open_bills:
                if remaining <= 0:
                    break
                due = float(b.get("balance_due", 0.0))
                if due > 0:
                    alloc_amt = min(remaining, due)
                    allocations.append({"invoice_id": b["invoice_no"], "amount": alloc_amt})
                    new_due = due - alloc_amt
                    new_status = "paid" if new_due == 0 else "partial"
                    self.bill_repo.update_one({"invoice_no": b["invoice_no"]}, {"$set": {"balance_due": new_due, "status": new_status}})
                    remaining -= alloc_amt

        payment_id = self.acc_repo.next_payment_id()
        now = datetime.now(timezone.utc)
        doc = {
            "payment_id": payment_id,
            "party_id": customer_id,
            "party_type": "customer",
            "amount": amount,
            "payment_date": now,
            "payment_method": payment_method,
            "reference_no": reference_no,
            "is_advance": remaining > 0,
            "allocation_status": "full" if remaining == 0 else ("partial" if allocations else "unallocated"),
            "allocations": allocations,
            "reconciliation_status": "unreconciled",
            "notes": notes,
            "is_deleted": 0,
            "created_by": user_id,
            "created_at": now,
        }
        self.acc_repo.payments.insert_one(doc)
        self.ledger.post_receipt(doc, user_id=user_id)

        # Decrement customer current balance
        self.cust_repo.update_balance(customer_id, -amount)

        # Log ledger entry
        self.acc_repo.ledger.insert_one({
            "transaction_id": self.acc_repo.next_ledger_txn_id(),
            "date": now,
            "account_id": customer_id,
            "account_name": customer["name"],
            "type": "credit",
            "amount": amount,
            "reference_id": payment_id,
            "reference_type": "payment",
            "description": f"Payment receipt ({payment_method})",
            "created_by": user_id,
            "created_at": now,
        })
        return doc

    # ---------------- SUPPLIER PAYMENTS (AP) ----------------
    @transactional
    def record_supplier_payment(
        self,
        purchase_id: str,
        supplier_id: str,
        amount: float,
        payment_method: str = "NEFT",
        reference_no: Optional[str] = None,
        notes: str = "",
        user_id: str = "system"
    ) -> Dict[str, Any]:
        """Disburse payment to supplier, reducing AP balance and bill balance due."""
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        bill = self.proc_repo.bills.find_one({"purchase_id": purchase_id})
        if not bill:
            raise ValueError(f"Purchase Bill '{purchase_id}' not found")

        due = float(bill.get("balance_due", 0.0))
        if amount > due:
            raise ValueError(f"Payment amount {amount:.2f} exceeds purchase balance due {due:.2f}")

        new_due = due - amount
        new_status = "paid" if new_due == 0 else "partial"
        self.proc_repo.bills.update_one({"purchase_id": purchase_id}, {"$set": {"balance_due": new_due, "status": new_status}})

        pay_id = self.proc_repo.next_payment_id()
        now = datetime.now(timezone.utc)
        doc = {
            "payment_id": pay_id,
            "purchase_id": purchase_id,
            "supplier_id": supplier_id,
            "total_bill_amount": float(bill.get("total_amount", 0.0)),
            "tds_deducted": float(bill.get("tds_amount", 0.0)),
            "net_amount_paid": amount,
            "payment_date": now,
            "payment_method": payment_method,
            "reference_no": reference_no,
            "notes": notes,
            "is_deleted": 0,
            "created_by": user_id,
            "created_at": now,
        }
        self.proc_repo.ap_payments.insert_one(doc)
        self.ledger.post_supplier_payment(doc, user_id=user_id)

        # Reduce supplier balance
        self.supp_repo.update_balance(supplier_id, -amount)
        return doc

    # ---------------- AR AGING BUCKETS ----------------
    @staticmethod
    def _age_days(created: Any, now: datetime) -> int:
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None
        if not isinstance(created, datetime):
            return 0
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0, (now - created).days)

    @staticmethod
    def _bucket(days: int) -> str:
        if days == 0:
            return "current"
        if days <= 30:
            return "1_30"
        if days <= 60:
            return "31_60"
        if days <= 90:
            return "61_90"
        return "90_plus"

    def get_ar_aging(self) -> Dict[str, Any]:
        """Receivables aging. The customer balance (which the ledger reconciles to) is the single source of truth
        for how much each customer owes; the bills only decide how old it is. The balance is matched against the
        newest invoices first, and whatever is older than every invoice on file (opening / legacy balance) falls
        into 90+. Customers with a credit balance are advances, not receivables: reported separately."""
        now = datetime.now(timezone.utc)
        keys = ("current", "1_30", "31_60", "61_90", "90_plus")
        buckets = {k: 0.0 for k in keys}
        buckets["total"] = 0.0
        advances = 0.0
        rows: List[Dict[str, Any]] = []

        bills_by_cust: Dict[str, List[Dict[str, Any]]] = {}
        for b in self.bill_repo.find({"is_deleted": 0, "status": {"$nin": ["void", "cancelled"]}}, limit=0):
            bills_by_cust.setdefault(b.get("customer_id"), []).append(b)

        for c in self.cust_repo.find({"is_deleted": 0}, limit=0):
            bal = round(float(c.get("current_balance", 0.0) or 0.0), 2)
            if bal < 0:
                advances += -bal
                continue
            if bal == 0:
                continue
            row = {"customer_id": c.get("cust_id"), "customer_name": c.get("name") or c.get("cust_id") or "Unknown",
                   **{k: 0.0 for k in keys}, "total": bal}
            remaining = bal
            invoices = sorted(bills_by_cust.get(c.get("cust_id"), []), key=lambda x: str(x.get("created_at") or ""), reverse=True)
            for b in invoices:
                if remaining <= 0.005:
                    break
                part = min(remaining, float(b.get("total_amount", 0.0) or 0.0))
                if part <= 0:
                    continue
                row[self._bucket(self._age_days(b.get("created_at"), now))] += part
                remaining -= part
            if remaining > 0.005:
                row["90_plus"] += remaining
            for k in keys:
                row[k] = round(row[k], 2)
                buckets[k] += row[k]
            buckets["total"] += bal
            rows.append(row)

        rows.sort(key=lambda r: r["total"], reverse=True)
        buckets = {k: round(v, 2) for k, v in buckets.items()}
        buckets["advances"] = round(advances, 2)
        return {"summary": buckets, "customers": rows}

    # ---------------- CUSTOMER STATEMENT ----------------
    @staticmethod
    def _as_date(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        if isinstance(value, str) and value:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                return None
        return None

    def customer_statement(self, customer_id: str, date_from: Optional[datetime] = None,
                           date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Running-balance statement for one customer: invoices (debit) and receipts (credit).

        The closing balance always equals the customer balance used everywhere else (up to `date_to`). Money owed
        from before the bills on file is the "Balance brought forward"; receipts the system never recorded show as
        one "Adjustment" credit, so the statement still ends on the figure the owner chases."""
        cust = self.cust_repo.find_one({"cust_id": customer_id})
        if not cust:
            raise ValueError(f"Customer '{customer_id}' not found")

        events: List[Dict[str, Any]] = []
        for b in self.bill_repo.find({"customer_id": customer_id, "is_deleted": 0,
                                      "status": {"$nin": ["void", "cancelled"]}}, limit=0):
            events.append({"date": self._as_date(b.get("invoice_date") or b.get("created_at")) or datetime.min,
                           "type": "Invoice", "ref": b.get("invoice_no", ""),
                           "debit": float(b.get("total_amount", 0.0) or 0.0), "credit": 0.0,
                           "note": b.get("ship_to_name") or ""})
        for p in self.acc_repo.payments.find({"party_id": customer_id, "party_type": "customer", "is_deleted": {"$ne": 1}}, limit=0):
            events.append({"date": self._as_date(p.get("payment_date") or p.get("created_at")) or datetime.min,
                           "type": "Receipt", "ref": p.get("payment_id", ""),
                           "debit": 0.0, "credit": float(p.get("amount", 0.0) or 0.0),
                           "note": " ".join(x for x in (p.get("payment_method"), p.get("reference_no")) if x)})

        for r in self.db.collection("sales_returns").find({"customer_id": customer_id, "is_deleted": 0, "status": {"$ne": "cancelled"}}):
            events.append({"date": self._as_date(r.get("return_date") or r.get("created_at")) or datetime.min,
                           "type": "Return", "ref": r.get("return_id", ""), "debit": 0.0,
                           "credit": float(r.get("total_refund_amount", 0.0) or 0.0), "note": f"Goods returned, invoice {r.get('original_invoice_no', '')}"})

        current = round(float(cust.get("current_balance", 0.0) or 0.0), 2)
        brought_forward = round(current - sum(e["debit"] - e["credit"] for e in events), 2)
        events.sort(key=lambda e: (e["date"], e["type"] != "Invoice", str(e["ref"])))
        if brought_forward < -0.005:
            # The bills on file add up to more than the customer owes: the difference was received outside the
            # system (older bills carry no receipts). Show it as one credit at the end, not as a huge opening "advance".
            events.append({"date": datetime.now(), "type": "Adjustment", "ref": "", "debit": 0.0,
                           "credit": -brought_forward, "note": "Receipts not itemised (earlier / outside the system)"})
            brought_forward = 0.0

        lo = self._as_date(date_from)
        hi = self._as_date(date_to)
        if hi is not None and hi.hour == 0 and hi.minute == 0:
            hi = hi.replace(hour=23, minute=59, second=59, microsecond=999999)

        opening = brought_forward
        rows: List[Dict[str, Any]] = []
        total_debit = total_credit = 0.0
        for e in events:
            if lo is not None and e["date"] < lo:
                opening += e["debit"] - e["credit"]
                continue
            if hi is not None and e["date"] > hi:
                continue
            total_debit += e["debit"]
            total_credit += e["credit"]
            rows.append(e)

        running = opening
        for r in rows:
            running += r["debit"] - r["credit"]
            r["balance"] = round(running, 2)
        return {"customer": cust, "date_from": lo, "date_to": hi, "opening": round(opening, 2), "rows": rows,
                "total_debit": round(total_debit, 2), "total_credit": round(total_credit, 2),
                "closing": round(running, 2)}
