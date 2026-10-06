from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.accounting_repo import AccountingRepository
from app.repositories.billing_repo import BillRepository
from app.repositories.master_repo import CustomerRepository, SupplierRepository
from app.repositories.procurement_repo import ProcurementRepository

class PaymentService:
    def __init__(self, db: Any):
        self.db = db
        self.acc_repo = AccountingRepository(db)
        self.bill_repo = BillRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.proc_repo = ProcurementRepository(db)

    # ---------------- CUSTOMER PAYMENTS (AR) ----------------
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

        # Reduce supplier balance
        self.supp_repo.update_balance(supplier_id, -amount)
        return doc

    # ---------------- AR AGING BUCKETS ----------------
    def get_ar_aging(self) -> Dict[str, Any]:
        """Compute AR aging analysis across open bills: Current, 1-30, 31-60, 61-90, 90+ days."""
        now = datetime.now(timezone.utc)
        open_bills = self.bill_repo.find(
            {"status": {"$in": ["unpaid", "partial"]}, "is_deleted": 0}
        )

        buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0, "total": 0.0}
        customer_breakdown: Dict[str, Dict[str, Any]] = {}

        for b in open_bills:
            due = float(b.get("balance_due", 0.0))
            if due <= 0:
                continue

            created = b.get("created_at")
            if isinstance(created, datetime):
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            elif created:
                try:
                    created = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    created = now
            else:
                created = now

            days_overdue = max(0, (now - created).days)
            cust_name = b.get("customer_name", "Unknown")
            if cust_name not in customer_breakdown:
                customer_breakdown[cust_name] = {
                    "customer_name": cust_name,
                    "current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0, "total": 0.0
                }

            if days_overdue == 0:
                tag = "current"
            elif days_overdue <= 30:
                tag = "1_30"
            elif days_overdue <= 60:
                tag = "31_60"
            elif days_overdue <= 90:
                tag = "61_90"
            else:
                tag = "90_plus"

            buckets[tag] += due
            buckets["total"] += due
            customer_breakdown[cust_name][tag] += due
            customer_breakdown[cust_name]["total"] += due

        return {"summary": buckets, "customers": list(customer_breakdown.values())}
