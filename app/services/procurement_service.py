from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.procurement_repo import ProcurementRepository
from app.repositories.master_repo import ItemRepository, SupplierRepository
from app.repositories.inventory_repo import InventoryRepository
from app.models.procurement import PurchaseOrder, PurchaseItem

class ProcurementService:
    def __init__(self, db: Any):
        self.db = db
        self.proc_repo = ProcurementRepository(db)
        self.item_repo = ItemRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.inv_repo = InventoryRepository(db)

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

    def record_grn(self, po_id: str, received_items: List[Dict[str, Any]], received_by: str = "system") -> Dict[str, Any]:
        """Record receipt of physical produce against a PO, incrementing warehouse stock."""
        po = self.proc_repo.pos.find_one({"po_id": po_id})
        if not po:
            raise ValueError(f"Purchase Order '{po_id}' not found")

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
        self.proc_repo.pos.update_one({"po_id": po_id}, {"$set": {"status": "received"}})
        return grn_doc

    # ---------------- PURCHASE BILLS (VENDOR INVOICES) ----------------
    def get_purchase_bills(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.proc_repo.bills.find({"is_deleted": 0}, sort=[("bill_date", -1)], limit=limit)

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
            "match_status": "matched" if (po_id and grn_id) else "direct",
            "status": "active",
            "is_deleted": 0,
            "notes": notes,
            "created_by": user_id,
            "created_at": now,
        }
        self.proc_repo.bills.insert_one(doc)

        # Update supplier AP balance
        self.supp_repo.update_balance(supplier_id, payable_amount)
        return doc
