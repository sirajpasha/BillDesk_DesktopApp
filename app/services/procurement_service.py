from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.procurement_repo import ProcurementRepository
from app.repositories.master_repo import ItemRepository, SupplierRepository
from app.repositories.inventory_repo import InventoryRepository
from app.models.procurement import PurchaseOrder, PurchaseItem
from app.services.ledger_service import LedgerService
from app.database.connection import transactional

class ProcurementService:
    def __init__(self, db: Any):
        self.db = db
        self.proc_repo = ProcurementRepository(db)
        self.item_repo = ItemRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.ledger = LedgerService(db)

    # ---------------- PURCHASE ORDERS ----------------
    def get_purchase_orders(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {}
        if status:
            filter_doc["status"] = status
        return self.proc_repo.pos.find(filter_doc, sort=[("date", -1)], limit=limit)

    def create_purchase_order(self, supplier_id: str, items: List[Dict[str, Any]], notes: str = "", user_id: str = "system") -> Dict[str, Any]:
        supplier = self.supp_repo.find_one({"supplier_id": supplier_id})
        if not supplier:
            raise ValueError(f"Supplier '{supplier_id}' not found")
        if not items:
            raise ValueError("PO must contain at least one item")

        total = sum(float(i["qty"]) * float(i["rate"]) for i in items)
        po_id = self.proc_repo.next_po_number()
        doc = {
            "po_id": po_id,
            "supplier_id": supplier_id,
            "supplier_name": supplier["name"],
            "date": datetime.now(timezone.utc),
            "items": items,
            "total_amount": total,
            "status": "draft",
            "notes": notes,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc),
        }
        return self.proc_repo.pos.insert_one(doc)

    # ---------------- GOODS RECEIPT NOTES (GRN) ----------------
    def get_grns(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.proc_repo.grns.find({"is_deleted": 0}, sort=[("date", -1)], limit=limit)

    @transactional
    def record_grn(self, po_id: str, received_items: List[Dict[str, Any]], received_by: str = "system") -> Dict[str, Any]:
        """Record receipt of physical produce against a PO, incrementing warehouse stock.

        A PO cannot be received after it is fully received/cancelled, items must be on the PO, and
        cumulative receipts may not exceed the ordered quantity (partial deliveries are allowed)."""
        po = self.proc_repo.pos.find_one({"po_id": po_id})
        if not po:
            raise ValueError(f"Purchase Order '{po_id}' not found")
        if po.get("status") in ("received", "cancelled"):
            raise ValueError(f"Purchase Order '{po_id}' is already {po['status']}")

        ordered: Dict[str, float] = {}
        for it in po.get("items") or []:
            ordered[it["item_id"]] = ordered.get(it["item_id"], 0.0) + float(it["qty"])
        already: Dict[str, float] = {}
        for g in self.proc_repo.grns.find({"po_id": po_id, "is_deleted": 0}, limit=0):
            for it in g.get("items") or []:
                already[it["item_id"]] = already.get(it["item_id"], 0.0) + float(it["qty"])

        this_receipt: Dict[str, float] = {}
        for item in received_items:
            qty = float(item["qty"])
            if qty < 0:
                raise ValueError("Received quantity cannot be negative")
            if qty == 0:
                continue
            i_id = item["item_id"]
            this_receipt[i_id] = this_receipt.get(i_id, 0.0) + qty
            if ordered:
                if i_id not in ordered:
                    raise ValueError(f"Item '{i_id}' is not on Purchase Order '{po_id}'")
                if already.get(i_id, 0.0) + this_receipt[i_id] > ordered[i_id] + 1e-9:
                    raise ValueError(
                        f"Receiving {this_receipt[i_id]:g} of '{i_id}' would exceed the ordered quantity "
                        f"({ordered[i_id]:g}, already received {already.get(i_id, 0.0):g})"
                    )
        if not this_receipt:
            raise ValueError("Nothing received: enter at least one quantity greater than zero")

        grn_id = self.proc_repo.next_grn_number()
        now = datetime.now(timezone.utc)

        for item in received_items:
            i_id = item["item_id"]
            qty = float(item["qty"])
            if qty > 0:
                self.item_repo.increment_stock(i_id, qty)
                self.inv_repo.record_stock_txn(
                    item_id=i_id,
                    item_name=item.get("name", i_id),
                    qty=qty,
                    txn_type="purchase",
                    reference_id=grn_id,
                    notes=f"GRN against PO {po_id}",
                    created_by=received_by,
                )

        grn_doc = {
            "grn_id": grn_id,
            "po_id": po_id,
            "date": now,
            "supplier_id": po["supplier_id"],
            "supplier_name": po["supplier_name"],
            "items": received_items,
            "received_by": received_by,
            "status": "active",
            "is_deleted": 0,
        }
        self.proc_repo.grns.insert_one(grn_doc)
        fully = (not ordered) or all(already.get(i, 0.0) + this_receipt.get(i, 0.0) >= q - 1e-9 for i, q in ordered.items())
        self.proc_repo.pos.update_one({"po_id": po_id}, {"$set": {"status": "received" if fully else "partially_received"}})
        return grn_doc

    # ---------------- PURCHASE BILLS (VENDOR INVOICES) ----------------
    def get_purchase_bills(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.proc_repo.bills.find({"is_deleted": 0}, sort=[("bill_date", -1)], limit=limit)

    @transactional
    def create_purchase_bill(
        self,
        supplier_id: str,
        supplier_bill_no: str,
        items: List[Dict[str, Any]],
        po_id: Optional[str] = None,
        grn_id: Optional[str] = None,
        notes: str = "",
        user_id: str = "system"
    ) -> Dict[str, Any]:
        """Record vendor purchase invoice with automatic TDS calculation and AP liability booking."""
        supplier = self.supp_repo.find_one({"supplier_id": supplier_id})
        if not supplier:
            raise ValueError(f"Supplier '{supplier_id}' not found")

        subtotal = sum(float(i["qty"]) * float(i["rate"]) for i in items)
        tds_amount = 0.0
        tds_section = supplier.get("tds_section")
        if supplier.get("tds_applicable"):
            rate = float(supplier.get("tds_rate", 0.0))
            tds_amount = subtotal * (rate / 100.0)

        payable_amount = subtotal - tds_amount
        match_status, match_issues = self._three_way_match(items, po_id, grn_id)
        purchase_id = self.proc_repo.next_purchase_id()
        now = datetime.now(timezone.utc)

        doc = {
            "purchase_id": purchase_id,
            "supplier_id": supplier_id,
            "supplier_name": supplier["name"],
            "supplier_bill_no": supplier_bill_no,
            "bill_date": now,
            "items": items,
            "total_amount": subtotal,
            "tds_amount": tds_amount,
            "tds_section_code": tds_section,
            "payable_amount": payable_amount,
            "balance_due": payable_amount,
            "po_id": po_id,
            "grn_id": grn_id,
            "match_status": match_status,
            "match_issues": match_issues,
            "status": "active",
            "is_deleted": 0,
            "notes": notes,
            "created_by": user_id,
            "created_at": now,
        }
        self.proc_repo.bills.insert_one(doc)
        self._update_item_costs(items)
        self.ledger.post_purchase_bill(doc, user_id=user_id)

        # Update supplier AP balance
        self.supp_repo.update_balance(supplier_id, payable_amount)
        return doc

    def _update_item_costs(self, items: List[Dict[str, Any]]) -> None:
        """Weighted-average cost: avg_cost over the costed quantity (cost_qty), updated by each vendor bill."""
        for it in items:
            item = self.item_repo.find_one({"item_id": it["item_id"]})
            qty, rate = float(it["qty"]), float(it["rate"])
            if not item or qty <= 0:
                continue
            cq, avg = float(item.get("cost_qty") or 0.0), float(item.get("avg_cost") or 0.0)
            new_avg = (cq * avg + qty * rate) / (cq + qty)
            self.item_repo.update_one({"item_id": it["item_id"]},
                                      {"$set": {"avg_cost": round(new_avg, 4), "cost_qty": cq + qty, "last_purchase_rate": rate}})

    def _three_way_match(self, items: List[Dict[str, Any]], po_id: Optional[str], grn_id: Optional[str]):
        """Compare the vendor bill with the PO (rates) and the GRN (quantities actually received)."""
        if not (po_id and grn_id):
            return "direct", []
        issues: List[str] = []
        po = self.proc_repo.pos.find_one({"po_id": po_id})
        grn = self.proc_repo.grns.find_one({"grn_id": grn_id})
        if not po:
            issues.append(f"PO {po_id} not found")
        if not grn:
            issues.append(f"GRN {grn_id} not found")
        if po and grn:
            received: Dict[str, float] = {}
            for it in grn.get("items") or []:
                received[it["item_id"]] = received.get(it["item_id"], 0.0) + float(it["qty"])
            po_rate = {it["item_id"]: float(it.get("rate", 0.0)) for it in po.get("items") or []}
            for it in items:
                i_id, qty, rate = it["item_id"], float(it["qty"]), float(it["rate"])
                if qty > received.get(i_id, 0.0) + 1e-9:
                    issues.append(f"{i_id}: billed {qty:g} but only {received.get(i_id, 0.0):g} received on {grn_id}")
                if i_id in po_rate and abs(rate - po_rate[i_id]) > 0.01:
                    issues.append(f"{i_id}: billed rate {rate:g} differs from PO rate {po_rate[i_id]:g}")
        return ("matched" if not issues else "mismatch"), issues
