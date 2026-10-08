from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from app.models.billing import BillCreate, BillLine
from app.repositories.billing_repo import BillRepository
from app.repositories.master_repo import ItemRepository, CustomerRepository, FixedPriceRepository
from app.repositories.inventory_repo import InventoryRepository
from app.services.payment_service import PaymentService

CASH_CUSTOMER_ID = "CASH"

class BillingService:
    def __init__(self, db: Any):
        self.db = db
        self.bill_repo = BillRepository(db)
        self.item_repo = ItemRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.price_repo = FixedPriceRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.payment_svc = PaymentService(db)
        self.parked_bills: List[Dict[str, Any]] = []

    def next_invoice_number(self) -> str:
        return self.bill_repo.next_invoice_number()

    def search_items(self, text: str, limit: int = 30) -> List[Dict[str, Any]]:
        return self.item_repo.search_items(text, limit=limit)

    def search_customers(self, text: str, limit: int = 30) -> List[Dict[str, Any]]:
        return self.cust_repo.search_customers(text, limit=limit)

    def fixed_rate(self, customer_id: str, item_id: str, when: datetime | None = None) -> Optional[Dict[str, Any]]:
        return self.price_repo.get_active_fixed_price(customer_id, item_id, when)

    def create_bill(self, bill: BillCreate) -> Dict[str, Any]:
        if not bill.items:
            raise ValueError("At least one item is required")
        for item in bill.items:
            if item.qty <= 0:
                raise ValueError("Item quantity must be greater than zero")
            if item.rate < 0:
                raise ValueError("Item rate cannot be negative")

        received = bill.amount_received
        if received is not None:
            if received < 0:
                raise ValueError("Amount received cannot be negative")
            if received - bill.total_amount > 0.005:
                raise ValueError(
                    f"Amount received ({received:.2f}) exceeds the bill total ({bill.total_amount:.2f})"
                )

        if bill.invoice_no is None:
            bill.invoice_no = self.next_invoice_number()
        if self.bill_repo.find_one({"invoice_no": bill.invoice_no}):
            raise ValueError(f"Invoice {bill.invoice_no} already exists")

        customer = None
        if bill.customer_id != CASH_CUSTOMER_ID:
            customer = self.cust_repo.find_one({"cust_id": bill.customer_id, "status": "active", "is_deleted": 0})
            if not customer:
                raise ValueError("Customer not found")
            limit = float(customer.get("credit_limit") or 0.0)
            if limit > 0 and float(customer.get("current_balance") or 0.0) + bill.total_amount > limit:
                raise ValueError(f"Credit limit exceeded ({limit:.2f})")

        now = datetime.now(timezone.utc)
        try:
            invoice_dt = datetime.strptime(bill.invoice_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            invoice_dt = now

        terms = int(customer.get("payment_terms_days", 30)) if customer else 30
        due_date = invoice_dt + timedelta(days=terms) if customer else None

        doc = bill.model_dump(exclude={"amount_received", "payment_method", "payment_reference"})
        if received is not None:
            doc["balance_due"] = round(bill.total_amount, 2)   # payment applied below
        doc.update({
            "invoice_no": bill.invoice_no,
            "created_at": now,
            "due_date": due_date,
            "status": "unpaid",
            "is_deleted": 0,
            "version_number": 1,
            "gl_account_id": "1200-AR",
            "currency_code": "INR",
        })

        session = None
        if getattr(self.db, "client", None) is not None and getattr(self.db, "supports_transactions", False):
            session = self.db.client.start_session()
            try:
                with session.start_transaction():
                    self._write_bill(doc, customer, bill, session)
            finally:
                session.end_session()
        else:
            self._write_bill(doc, customer, bill, None)

        if received is not None:
            self._apply_counter_payment(doc, bill, received)
        return doc

    def _apply_counter_payment(self, doc: Dict[str, Any], bill: BillCreate, received: float) -> None:
        """Record the payment taken while saving the bill and settle the bill/customer balance."""
        received = round(received, 2)
        if received <= 0:
            return
        method = bill.payment_method or "Cash"
        if bill.customer_id != CASH_CUSTOMER_ID:
            # Lowers customer.current_balance, settles this bill, writes payments + ledger rows.
            self.payment_svc.record_customer_payment(
                customer_id=bill.customer_id, amount=received, payment_method=method,
                reference_no=bill.payment_reference, invoice_no=bill.invoice_no,
                notes="Received at billing", user_id=bill.created_by,
            )
        else:
            # Walk-in sale: no customer ledger, but the receipt is still recorded.
            due = round(bill.total_amount - received, 2)
            now = datetime.now(timezone.utc)
            self.bill_repo.update_one(
                {"invoice_no": bill.invoice_no},
                {"$set": {"balance_due": due, "status": "paid" if due <= 0 else "partial"}},
            )
            acc = self.payment_svc.acc_repo
            acc.payments.insert_one({
                "payment_id": acc.next_payment_id(), "party_id": CASH_CUSTOMER_ID, "party_type": "walk-in",
                "amount": received, "payment_date": now, "payment_method": method,
                "reference_no": bill.payment_reference, "is_advance": False, "allocation_status": "full",
                "allocations": [{"invoice_id": bill.invoice_no, "amount": received}],
                "reconciliation_status": "unreconciled", "notes": "Received at billing",
                "is_deleted": 0, "created_by": bill.created_by, "created_at": now,
            })
        fresh = self.bill_repo.find_one({"invoice_no": bill.invoice_no}) or {}
        doc["balance_due"] = fresh.get("balance_due", doc.get("balance_due"))
        doc["status"] = fresh.get("status", doc.get("status"))

    def _write_bill(self, doc: Dict[str, Any], customer: Optional[Dict[str, Any]], bill: BillCreate, session: Any):
        kw = {"session": session} if session else {}
        self.db.collection("bills").insert_one(doc, **kw)
        if customer:
            self.db.collection("customers").update_one(
                {"cust_id": customer["cust_id"]},
                {"$inc": {"current_balance": bill.total_amount}},
                **kw
            )
            # Crate tracking
            net_crates = float(bill.crates_issued or 0.0) - float(bill.crates_returned or 0.0)
            if net_crates != 0 and bill.crate_item_id:
                self.inv_repo.record_crate_txn(
                    party_id=bill.customer_id,
                    party_type="customer",
                    item_id=bill.crate_item_id,
                    item_name="Crate",
                    issued_qty=bill.crates_issued,
                    returned_qty=bill.crates_returned,
                    reference_id=bill.invoice_no,
                    created_by=bill.created_by,
                    session=session
                )

        for line in bill.items:
            self.db.collection("items").update_one(
                {"item_id": line.item_id},
                {"$inc": {"stock": -abs(line.qty)}},
                **kw
            )
            self.db.collection("stock_transactions").insert_one({
                "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
                "item_id": line.item_id,
                "item_name": line.name,
                "qty": -abs(line.qty),
                "type": "sale",
                "reference_id": bill.invoice_no,
                "created_by": bill.created_by,
                "created_at": datetime.now(timezone.utc),
            }, **kw)

        self.db.collection("bill_audits").insert_one({
            "audit_id": f"BA-{uuid.uuid4().hex[:10].upper()}",
            "invoice_no": bill.invoice_no,
            "action": "CREATE",
            "changed_by": bill.created_by,
            "changed_at": datetime.now(timezone.utc),
            "user_agent": "BillDesk Native",
            "ip_address": "local",
        }, **kw)

    def void_bill(self, invoice_no: str, user_id: str = "system") -> Dict[str, Any]:
        """Void bill and execute full financial, stock, and crate reversal."""
        bill = self.bill_repo.find_one({"invoice_no": invoice_no, "is_deleted": 0})
        if not bill:
            raise ValueError(f"Invoice {invoice_no} not found")
        if bill.get("status") == "void":
            raise ValueError(f"Invoice {invoice_no} is already voided")

        # 1. Restore Customer Balance
        cust_id = bill.get("customer_id")
        total_amount = float(bill.get("total_amount", 0.0))
        if cust_id and cust_id != CASH_CUSTOMER_ID:
            self.cust_repo.update_balance(cust_id, -total_amount)

        # 2. Restore Stock
        for line in bill.get("items", []):
            item_id = line["item_id"]
            qty = float(line["qty"])
            self.item_repo.increment_stock(item_id, qty)
            self.inv_repo.record_stock_txn(
                item_id=item_id,
                item_name=line.get("name", ""),
                qty=qty,
                txn_type="adjustment",
                reference_id=invoice_no,
                notes=f"Reversal of voided bill {invoice_no}",
                created_by=user_id,
            )

        # 3. Mark Bill Status Void
        self.bill_repo.update_one({"invoice_no": invoice_no}, {"$set": {"status": "void", "balance_due": 0.0}})

        # 4. Record Audit Entry
        self.bill_repo.log_audit(
            invoice_no=invoice_no,
            action="VOID",
            changed_by=user_id,
            field_changed="status",
            old_value=bill.get("status"),
            new_value="void"
        )
        return {"invoice_no": invoice_no, "status": "void", "reverted_amount": total_amount}

    def park_bill(self, bill_data: Dict[str, Any]) -> int:
        """Park bill in memory queue for fast recall (F6/F7)."""
        self.parked_bills.append(bill_data)
        return len(self.parked_bills)

    def get_parked_bills(self) -> List[Dict[str, Any]]:
        return self.parked_bills

    def recall_parked_bill(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.parked_bills):
            return self.parked_bills.pop(index)
        return None

    def search_bills(
        self,
        query: str = "",
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        return self.bill_repo.search_bills(query, status, date_from, date_to, limit, skip)

    def recent_bills(self, limit: int = 25) -> List[Dict[str, Any]]:
        return self.bill_repo.find({"is_deleted": 0}, sort=[("created_at", -1)], limit=limit)

    def get_unique_bill_to_entities(self) -> List[Dict[str, Any]]:
        """Return unique billing entities (combining bill_to_name or customer name) for reports."""
        customers = self.cust_repo.find({"is_deleted": 0}, sort=[("name", 1)], limit=0)
        seen = set()
        results = []
        for c in customers:
            bill_to_name = (c.get("bill_to_name") or c.get("name") or "").strip()
            if not bill_to_name or bill_to_name.lower() in ("cash", "____", ""):
                continue
            if bill_to_name not in seen:
                seen.add(bill_to_name)
                results.append({
                    "cust_id": c.get("cust_id"),
                    "name": bill_to_name,
                    "bill_to_name": bill_to_name,
                    "bill_to_address": c.get("bill_to_address") or c.get("address") or "",
                    "bill_to_phone": c.get("bill_to_phone") or c.get("contact_person_phone") or c.get("phone") or "",
                })
        results.sort(key=lambda x: x["name"])
        return results

    def get_consolidated_report(
        self,
        customer_id_or_name: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Generate consolidated item-wise and bill-wise report across shipping locations."""
        if not customer_id_or_name:
            raise ValueError("Customer ID or Bill-To name is required")

        # 1. Fetch base customer or find by bill_to_name
        base_customer = self.cust_repo.find_one({"cust_id": customer_id_or_name, "is_deleted": 0})
        if not base_customer:
            base_customer = self.cust_repo.find_one({
                "bill_to_name": {"$regex": f"^{customer_id_or_name.strip()}$", "$options": "i"},
                "is_deleted": 0
            })
        if not base_customer:
            base_customer = self.cust_repo.find_one({
                "name": {"$regex": f"^{customer_id_or_name.strip()}$", "$options": "i"},
                "is_deleted": 0
            })
        if not base_customer:
            base_customer = self.cust_repo.find_one({
                "$or": [
                    {"bill_to_name": {"$regex": customer_id_or_name.strip(), "$options": "i"}},
                    {"name": {"$regex": customer_id_or_name.strip(), "$options": "i"}}
                ],
                "is_deleted": 0
            })

        if not base_customer:
            raise ValueError(f"Customer or Billing entity '{customer_id_or_name}' not found")

        # 2. Determine Bill-To name and find siblings
        bill_to_name = (base_customer.get("bill_to_name") or base_customer.get("name") or "").strip()
        query_customers = [base_customer.get("cust_id")]

        if bill_to_name:
            siblings = self.cust_repo.find({
                "bill_to_name": {"$regex": f"^{bill_to_name}$", "$options": "i"},
                "is_deleted": 0
            }, limit=0)
            sibling_ids = [c.get("cust_id") for c in siblings if c.get("cust_id")]
            if sibling_ids:
                query_customers = list(set(query_customers + sibling_ids))

        # 3. Query all qualifying bills
        bill_query = {
            "customer_id": {"$in": query_customers},
            "invoice_date": {"$gte": start_date, "$lte": end_date},
            "status": {"$nin": ["cancelled", "void"]},
            "is_deleted": 0
        }
        bills = self.bill_repo.find(bill_query, sort=[("invoice_date", 1), ("invoice_no", 1)], limit=0)

        # 4. Group and Consolidate
        ship_to_groups: Dict[str, Dict[str, Any]] = {}
        grand_total_items: Dict[str, Dict[str, Any]] = {}
        bill_summary: List[Dict[str, Any]] = []

        sorted_bills = sorted(bills, key=lambda x: (x.get("invoice_date") or "", x.get("invoice_no") or ""))

        for bill in sorted_bills:
            ship_to = bill.get("customer_name") or "Unknown"
            amt = float(bill.get("total_amount", 0.0))

            bill_summary.append({
                "date": bill.get("invoice_date", ""),
                "ship_to": ship_to,
                "amount": amt,
                "invoice_no": bill.get("invoice_no", "")
            })

            if ship_to not in ship_to_groups:
                ship_to_groups[ship_to] = {"items": {}, "total_amount": 0.0}

            ship_to_groups[ship_to]["total_amount"] += amt

            for item in bill.get("items", []):
                item_name = item.get("name") or "Item"
                item_key = item.get("item_alias") or item.get("item_id") or item_name
                qty = float(item.get("qty", 0.0))
                item_amt = float(item.get("amount", 0.0))
                unit = item.get("unit") or "kg"

                # Per Ship To Consolidation
                if item_key not in ship_to_groups[ship_to]["items"]:
                    ship_to_groups[ship_to]["items"][item_key] = {
                        "name": item_name,
                        "qty": 0.0,
                        "unit": unit,
                        "total_val": 0.0
                    }
                ship_to_groups[ship_to]["items"][item_key]["qty"] += qty
                ship_to_groups[ship_to]["items"][item_key]["total_val"] += item_amt

                # Grand Total Consolidation
                if item_key not in grand_total_items:
                    grand_total_items[item_key] = {
                        "name": item_name,
                        "qty": 0.0,
                        "unit": unit,
                        "total_val": 0.0
                    }
                grand_total_items[item_key]["qty"] += qty
                grand_total_items[item_key]["total_val"] += item_amt

        # Format ship_to_reports
        report_data = []
        for ship_to in sorted(ship_to_groups.keys()):
            data = ship_to_groups[ship_to]
            items_list = []
            for k, v in data["items"].items():
                avg_rate = (v["total_val"] / v["qty"]) if v["qty"] > 0 else 0.0
                items_list.append({
                    "item_id": k,
                    "name": v["name"],
                    "qty": round(v["qty"], 3),
                    "unit": v["unit"],
                    "rate": round(avg_rate, 2),
                    "amount": round(v["total_val"], 2)
                })
            items_list.sort(key=lambda x: x["name"])
            report_data.append({
                "ship_to": ship_to,
                "items": items_list,
                "total_amount": round(data["total_amount"], 2)
            })

        # Format grand_total_consolidation
        grand_total_list = []
        for k, v in grand_total_items.items():
            avg_rate = (v["total_val"] / v["qty"]) if v["qty"] > 0 else 0.0
            grand_total_list.append({
                "item_id": k,
                "name": v["name"],
                "qty": round(v["qty"], 3),
                "unit": v["unit"],
                "rate": round(avg_rate, 2),
                "amount": round(v["total_val"], 2)
            })
        grand_total_list.sort(key=lambda x: x["name"])

        total_bill_amount = sum(d["total_amount"] for d in report_data)

        return {
            "bill_to": bill_to_name,
            "customer_id": base_customer.get("cust_id"),
            "customer": base_customer,
            "date_range": {"start": start_date, "end": end_date},
            "ship_to_reports": report_data,
            "grand_total_consolidation": grand_total_list,
            "total_bill_amount": round(total_bill_amount, 2),
            "bill_summary": bill_summary
        }
