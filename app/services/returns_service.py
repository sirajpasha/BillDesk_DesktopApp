"""Sales returns (credit notes): goods brought back after an invoice was issued."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database.connection import transactional
from app.repositories.billing_repo import BillRepository, SalesReturnRepository
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.master_repo import CustomerRepository, ItemRepository
from app.services.ledger_service import LedgerService
from app.utils.currency import money

CASH_CUSTOMER_ID = "CASH"


class ReturnsService:
    def __init__(self, db: Any):
        self.db = db
        self.bill_repo = BillRepository(db)
        self.ret_repo = SalesReturnRepository(db)
        self.item_repo = ItemRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.ledger = LedgerService(db)

    # ------------------------------------------------------------------ reads
    def _canon(self) -> Dict[str, str]:
        """code or id -> the item master's item_id. Older bills store the item's code; older returns store its id."""
        m: Dict[str, str] = {}
        for it in self.item_repo.find({}, limit=0):
            iid = it.get("item_id")
            if iid:
                m[str(iid)] = iid
                if it.get("item_alias"):
                    m.setdefault(str(it["item_alias"]), iid)
        return m

    def returns_for_invoice(self, invoice_no: str) -> List[Dict[str, Any]]:
        # returns made by the older web app have no is_deleted field and sometimes a leading space in the invoice number
        return self.ret_repo.find({"original_invoice_no": {"$in": [invoice_no, " " + invoice_no]}, "is_deleted": {"$ne": 1},
                                   "status": {"$ne": "cancelled"}}, limit=0)

    def returnable_lines(self, invoice_no: str) -> List[Dict[str, Any]]:
        """Each invoice line with how much was billed, already returned, and is still returnable."""
        bill = self.bill_repo.find_one({"invoice_no": invoice_no, "is_deleted": 0})
        if not bill:
            raise ValueError(f"Invoice {invoice_no} not found")
        canon = self._canon()
        back: Dict[str, float] = {}
        for r in self.returns_for_invoice(invoice_no):
            for l in r.get("items", []):
                k = canon.get(str(l["item_id"]), l["item_id"])
                back[k] = back.get(k, 0.0) + float(l.get("qty", 0.0))
        merged: Dict[str, Dict[str, Any]] = {}
        for l in bill.get("items", []):
            m = merged.setdefault(l["item_id"], {"item_id": l["item_id"], "name": l.get("name", ""), "unit": l.get("unit", ""),
                                                 "rate": float(l.get("rate", 0.0)), "billed": 0.0, "amount": 0.0})
            m["billed"] += float(l.get("qty", 0.0))
            m["amount"] += float(l.get("amount", 0.0))
        for m in merged.values():
            m["returned"] = round(back.get(canon.get(str(m["item_id"]), m["item_id"]), 0.0), 3)
            m["returnable"] = round(m["billed"] - m["returned"], 3)
        return list(merged.values())

    # ------------------------------------------------------------------ write
    @transactional
    def create_return(self, invoice_no: str, lines: List[Dict[str, Any]], reason: str = "",
                      refund_method: str = "Cash", user_id: str = "system") -> Dict[str, Any]:
        """Take goods back against an invoice.

        lines: [{"item_id", "qty", "is_waste"}]. The credit is at the rate billed. Good stock goes back on the shelf at the
        cost it was sold at; spoiled goods (is_waste) are credited to the customer but not added back to stock.
        A customer's credit first reduces what is still due on that invoice; any excess stays as credit on their account.
        A walk-in (cash) customer is refunded in `refund_method`."""
        bill = self.bill_repo.find_one({"invoice_no": invoice_no, "is_deleted": 0})
        if not bill:
            raise ValueError(f"Invoice {invoice_no} not found")
        if bill.get("status") in ("void", "cancelled"):
            raise ValueError(f"Invoice {invoice_no} is void; nothing can be returned against it")
        wanted = [l for l in lines if float(l.get("qty") or 0) > 0]
        if not wanted:
            raise ValueError("Enter a quantity to return for at least one item")
        avail = {l["item_id"]: l for l in self.returnable_lines(invoice_no)}

        items: List[Dict[str, Any]] = []
        for l in wanted:
            line = avail.get(l["item_id"])
            if not line:
                raise ValueError(f"Item {l['item_id']} is not on invoice {invoice_no}")
            qty = round(float(l["qty"]), 3)
            if qty - line["returnable"] > 0.0005:
                raise ValueError(f"{line['name']}: only {line['returnable']:g} {line['unit']} can still be returned "
                                 f"(billed {line['billed']:g}, already returned {line['returned']:g})")
            items.append({"item_id": line["item_id"], "name": line["name"], "qty": qty, "unit": line["unit"], "rate": line["rate"],
                          "amount": money(qty * line["rate"]), "is_waste": bool(l.get("is_waste"))})
        refund = money(sum(i["amount"] for i in items))

        # cost that was booked for these goods, in proportion to their share of the invoice
        billed_amount = sum(float(x.get("amount", 0.0)) for x in bill.get("items", [])) or 1.0
        booked_cost = float(bill.get("cost_of_goods") or 0.0)
        restock_cost = money(sum(booked_cost * i["amount"] / billed_amount for i in items if not i["is_waste"]))

        cust_id = bill.get("customer_id")
        walk_in = not cust_id or cust_id == CASH_CUSTOMER_ID
        applied, credit = 0.0, 0.0
        if not walk_in:
            self.cust_repo.update_balance(cust_id, -refund)
            due = float(bill.get("balance_due") or 0.0) if bill.get("status") in ("unpaid", "partial") else 0.0
            applied = min(refund, due)
            credit = money(refund - applied)
            if applied > 0:
                new_due = money(due - applied)
                self.bill_repo.update_one({"invoice_no": invoice_no}, {"$set": {"balance_due": new_due,
                                                                                "status": "paid" if new_due <= 0 else "partial"}})

        now = datetime.now(timezone.utc)
        doc = {
            "return_id": self.ret_repo.next_return_id(), "return_date": now, "original_invoice_no": invoice_no,
            "customer_id": cust_id, "customer_name": bill.get("customer_name", ""), "items": items,
            "total_refund_amount": refund, "applied_to_bill": money(applied), "credit_amount": credit,
            "refund_method": refund_method if walk_in else "Credit to account", "restock_cost": restock_cost,
            "status": "completed", "notes": reason, "is_deleted": 0, "created_by": user_id, "created_at": now,
        }
        self.ret_repo.insert_one(doc)

        for i in items:
            if i["is_waste"]:
                continue
            master = self.item_repo.find_by_alias_or_id(i["item_id"])      # older bills store the item's code, not its id
            stock_id = master["item_id"] if master else i["item_id"]
            self.item_repo.increment_stock(stock_id, i["qty"])
            self.item_repo.update_one({"item_id": stock_id}, {"$inc": {"cost_qty": i["qty"]}})
            self.inv_repo.record_stock_txn(item_id=stock_id, item_name=i["name"], qty=i["qty"], txn_type="return",
                                           reference_id=doc["return_id"], notes=f"Returned against {invoice_no}", created_by=user_id)
        self.ledger.post_sales_return(doc, refund_method=refund_method, user_id=user_id)
        self.bill_repo.log_audit(invoice_no=invoice_no, action="RETURN", changed_by=user_id, field_changed="return",
                                 old_value="", new_value=f"{doc['return_id']} Rs {refund:.2f}")
        return doc

    # ------------------------------------------------------------------ cancel
    @transactional
    def cancel_return(self, return_id: str, user_id: str = "system", reason: str = "") -> Dict[str, Any]:
        """Undo a return made by mistake: the customer's balance, the invoice's balance due, stock and the ledger go back to
        what they were before it, and the credit note is marked cancelled (it stays on file; it no longer counts anywhere).
        Returns made by the older web app are not handled here: they were not recorded with enough detail to undo safely."""
        ret = self.ret_repo.find_one({"return_id": return_id, "is_deleted": {"$ne": 1}})
        if not ret:
            raise ValueError(f"Return {return_id} not found")
        if ret.get("status") == "cancelled":
            raise ValueError(f"Return {return_id} is already cancelled")
        if "applied_to_bill" not in ret:
            raise ValueError(f"Return {return_id} was made by the older BillDesk and cannot be cancelled here")
        invoice_no = str(ret.get("original_invoice_no") or "").strip()
        bill = self.bill_repo.find_one({"invoice_no": invoice_no, "is_deleted": 0})
        if bill and bill.get("status") in ("void", "cancelled"):
            raise ValueError(f"Invoice {invoice_no} is void; this return can no longer be cancelled")

        refund = money(ret.get("total_refund_amount"))
        cust_id = ret.get("customer_id")
        if cust_id and cust_id != CASH_CUSTOMER_ID:
            self.cust_repo.update_balance(cust_id, refund)                                  # the credit given is taken back
            applied = money(ret.get("applied_to_bill"))
            if bill and applied > 0:
                total = float(bill.get("total_amount") or 0.0)
                new_due = money(min(total, float(bill.get("balance_due") or 0.0) + applied))
                self.bill_repo.update_one({"invoice_no": invoice_no}, {"$set": {
                    "balance_due": new_due, "status": "unpaid" if new_due >= total - 0.005 else "partial"}})

        for i in ret.get("items", []):
            if i.get("is_waste"):
                continue
            master = self.item_repo.find_by_alias_or_id(i["item_id"])
            stock_id = master["item_id"] if master else i["item_id"]
            self.item_repo.decrement_stock(stock_id, float(i["qty"]))
            self.item_repo.update_one({"item_id": stock_id}, {"$inc": {"cost_qty": -float(i["qty"])}})
            self.inv_repo.record_stock_txn(item_id=stock_id, item_name=i.get("name", ""), qty=-float(i["qty"]), txn_type="return_cancelled",
                                           reference_id=return_id, notes=f"Return {return_id} cancelled", created_by=user_id)
        self.ledger.reverse_entries(return_id, ["sales_return", "sales_return_cogs"], user_id)
        now = datetime.now(timezone.utc)
        self.ret_repo.update_one({"return_id": return_id}, {"$set": {"status": "cancelled", "cancelled_at": now, "cancelled_by": user_id,
                                                                     "cancel_reason": reason}})
        self.bill_repo.log_audit(invoice_no=invoice_no, action="RETURN_CANCELLED", changed_by=user_id, field_changed="return",
                                 old_value=f"{return_id} Rs {refund:.2f}", new_value="cancelled")
        return self.ret_repo.find_one({"return_id": return_id}) or ret
