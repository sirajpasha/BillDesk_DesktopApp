"""Purchase returns (debit notes): goods sent back to a supplier after their invoice was recorded."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.database.connection import transactional
from app.repositories.inventory_repo import InventoryRepository
from app.repositories.master_repo import ItemRepository, SupplierRepository
from app.repositories.procurement_repo import ProcurementRepository
from app.services.ledger_service import LedgerService
from app.utils.currency import money


class PurchaseReturnsService:
    def __init__(self, db: Any):
        self.db = db
        self.proc_repo = ProcurementRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.item_repo = ItemRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.ledger = LedgerService(db)

    # ------------------------------------------------------------------ reads
    def returns_for_purchase(self, purchase_id: str) -> List[Dict[str, Any]]:
        return self.proc_repo.returns.find({"purchase_id": purchase_id, "is_deleted": 0, "status": {"$ne": "cancelled"}}, limit=0)

    def returnable_lines(self, purchase_id: str) -> List[Dict[str, Any]]:
        bill = self.proc_repo.bills.find_one({"purchase_id": purchase_id, "is_deleted": 0})
        if not bill:
            raise ValueError(f"Purchase bill {purchase_id} not found")
        back: Dict[str, float] = {}
        for r in self.returns_for_purchase(purchase_id):
            for l in r.get("items", []):
                back[l["item_id"]] = back.get(l["item_id"], 0.0) + float(l.get("qty", 0.0))
        merged: Dict[str, Dict[str, Any]] = {}
        for l in bill.get("items", []):
            m = merged.setdefault(l["item_id"], {"item_id": l["item_id"], "name": l.get("name", ""), "unit": l.get("unit", ""),
                                                 "rate": float(l.get("rate", 0.0)), "billed": 0.0})
            m["billed"] += float(l.get("qty", 0.0))
        for m in merged.values():
            m["returned"] = round(back.get(m["item_id"], 0.0), 3)
            m["returnable"] = round(m["billed"] - m["returned"], 3)
        return list(merged.values())

    # ------------------------------------------------------------------ write
    @transactional
    def create_return(self, purchase_id: str, lines: List[Dict[str, Any]], reason: str = "", user_id: str = "system") -> Dict[str, Any]:
        """Send goods back to the supplier.

        lines: [{"item_id", "qty"}]. Value is at the rate on the vendor bill; TDS that was deducted on the bill comes back in the
        same proportion, so what we owe the supplier falls by the NET amount. That reduces what is still due on the bill first; any
        excess is a credit with the supplier. Stock is taken off only when the goods were received into stock (the bill has a GRN)."""
        bill = self.proc_repo.bills.find_one({"purchase_id": purchase_id, "is_deleted": 0})
        if not bill:
            raise ValueError(f"Purchase bill {purchase_id} not found")
        wanted = [l for l in lines if float(l.get("qty") or 0) > 0]
        if not wanted:
            raise ValueError("Enter a quantity to return for at least one item")
        avail = {l["item_id"]: l for l in self.returnable_lines(purchase_id)}

        items: List[Dict[str, Any]] = []
        for l in wanted:
            line = avail.get(l["item_id"])
            if not line:
                raise ValueError(f"Item {l['item_id']} is not on purchase bill {purchase_id}")
            qty = round(float(l["qty"]), 3)
            if qty - line["returnable"] > 0.0005:
                raise ValueError(f"{line['name']}: only {line['returnable']:g} {line['unit']} can still be returned "
                                 f"(bought {line['billed']:g}, already returned {line['returned']:g})")
            items.append({"item_id": line["item_id"], "name": line["name"], "qty": qty, "unit": line["unit"], "rate": line["rate"],
                          "amount": money(qty * line["rate"])})
        gross = money(sum(i["amount"] for i in items))
        bill_total = float(bill.get("total_amount") or 0.0)
        tds = money(float(bill.get("tds_amount") or 0.0) * gross / bill_total) if bill_total > 0 else 0.0
        net = money(gross - tds)

        due = float(bill.get("balance_due") or 0.0)
        applied = min(net, max(due, 0.0))
        credit = money(net - applied)
        if applied > 0:
            new_due = money(due - applied)
            self.proc_repo.bills.update_one({"purchase_id": purchase_id}, {"$set": {"balance_due": new_due,
                                                                                     "status": "paid" if new_due <= 0 else "partial"}})
        self.supp_repo.update_balance(bill["supplier_id"], -net)

        now = datetime.now(timezone.utc)
        doc = {
            "return_id": self.proc_repo.next_purchase_return_id(), "return_date": now, "purchase_id": purchase_id,
            "supplier_id": bill["supplier_id"], "supplier_name": bill.get("supplier_name", ""),
            "supplier_bill_no": bill.get("supplier_bill_no", ""), "items": items, "gross_amount": gross, "tds_amount": tds,
            "net_amount": net, "applied_to_bill": money(applied), "credit_amount": credit,
            "status": "completed", "notes": reason, "is_deleted": 0, "created_by": user_id, "created_at": now,
        }
        self.proc_repo.returns.insert_one(doc)

        if bill.get("grn_id"):
            for i in items:
                master = self.item_repo.find_by_alias_or_id(i["item_id"])
                stock_id = master["item_id"] if master else i["item_id"]
                self.item_repo.decrement_stock(stock_id, i["qty"])
                self.inv_repo.record_stock_txn(item_id=stock_id, item_name=i["name"], qty=-i["qty"], txn_type="purchase_return",
                                               reference_id=doc["return_id"], notes=f"Returned to supplier against {purchase_id}", created_by=user_id)
        for i in items:
            master = self.item_repo.find_by_alias_or_id(i["item_id"])
            if master:
                left = max(0.0, float(master.get("cost_qty") or 0.0) - i["qty"])
                self.item_repo.update_one({"item_id": master["item_id"]}, {"$set": {"cost_qty": left}})
        self.ledger.post_purchase_return(doc, user_id=user_id)
        return doc

    # ------------------------------------------------------------------ cancel
    @transactional
    def cancel_return(self, return_id: str, user_id: str = "system", reason: str = "") -> Dict[str, Any]:
        """Undo a debit note made by mistake: what is owed to the supplier, the vendor bill's balance due, stock (when the goods had
        been received into stock) and the ledger go back to what they were; the debit note is marked cancelled and no longer counts."""
        ret = self.proc_repo.returns.find_one({"return_id": return_id, "is_deleted": {"$ne": 1}})
        if not ret:
            raise ValueError(f"Return {return_id} not found")
        if ret.get("status") == "cancelled":
            raise ValueError(f"Return {return_id} is already cancelled")
        bill = self.proc_repo.bills.find_one({"purchase_id": ret["purchase_id"], "is_deleted": 0})
        net = money(ret.get("net_amount"))
        self.supp_repo.update_balance(ret["supplier_id"], net)
        applied = money(ret.get("applied_to_bill"))
        if bill and applied > 0:
            payable = float(bill.get("payable_amount") or 0.0)
            new_due = money(min(payable, float(bill.get("balance_due") or 0.0) + applied))
            self.proc_repo.bills.update_one({"purchase_id": ret["purchase_id"]}, {"$set": {
                "balance_due": new_due, "status": "active" if new_due >= payable - 0.005 else "partial"}})
        for i in ret.get("items", []):
            master = self.item_repo.find_by_alias_or_id(i["item_id"])
            stock_id = master["item_id"] if master else i["item_id"]
            if bill and bill.get("grn_id"):
                self.item_repo.increment_stock(stock_id, float(i["qty"]))
                self.inv_repo.record_stock_txn(item_id=stock_id, item_name=i.get("name", ""), qty=float(i["qty"]), txn_type="purchase_return_cancelled",
                                               reference_id=return_id, notes=f"Return {return_id} cancelled", created_by=user_id)
            if master:
                self.item_repo.update_one({"item_id": master["item_id"]}, {"$inc": {"cost_qty": float(i["qty"])}})
        self.ledger.reverse_entries(return_id, ["purchase_return"], user_id)
        self.proc_repo.returns.update_one({"return_id": return_id}, {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc),
                                                                              "cancelled_by": user_id, "cancel_reason": reason}})
        return self.proc_repo.returns.find_one({"return_id": return_id}) or ret
