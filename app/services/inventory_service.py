from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.master_repo import ItemRepository
from app.repositories.inventory_repo import InventoryRepository

class InventoryService:
    def __init__(self, db: Any):
        self.db = db
        self.item_repo = ItemRepository(db)
        self.inv_repo = InventoryRepository(db)

    def get_stock_overview(self, category: Optional[str] = None, search: str = "") -> List[Dict[str, Any]]:
        filter_doc: Dict[str, Any] = {"is_deleted": 0}
        if category and category != "All":
            filter_doc["category"] = category
        if search:
            filter_doc["$or"] = [
                {"item_id": {"$regex": search, "$options": "i"}},
                {"item_alias": {"$regex": search, "$options": "i"}},
                {"name": {"$regex": search, "$options": "i"}},
            ]
        return self.item_repo.find(filter_doc, sort=[("name", 1)], limit=200)

    def adjust_stock(self, item_id: str, delta_qty: float, reason: str, user_id: str = "system") -> Dict[str, Any]:
        """Manually adjust item stock (+ or -) with mandatory reason and immutable audit log."""
        item = self.item_repo.find_one({"item_id": item_id, "is_deleted": 0})
        if not item:
            raise ValueError(f"Item '{item_id}' not found")
        if delta_qty == 0:
            raise ValueError("Adjustment quantity cannot be zero")

        new_stock = float(item.get("stock", 0.0)) + delta_qty
        if new_stock < 0:
            raise ValueError(f"Adjustment would result in negative stock ({new_stock:.2f})")

        self.item_repo.update_one({"item_id": item_id}, {"$inc": {"stock": delta_qty}})
        txn = self.inv_repo.record_stock_txn(
            item_id=item_id,
            item_name=item["name"],
            qty=delta_qty,
            txn_type="adjustment",
            notes=reason,
            created_by=user_id,
        )
        return {"item_id": item_id, "delta_qty": delta_qty, "new_stock": new_stock, "transaction_id": txn["transaction_id"]}

    def record_waste(self, item_id: str, qty: float, rate: float, reason: str, user_id: str = "system") -> Dict[str, Any]:
        """Record produce spoilage/waste, decrement stock, and log financial loss."""
        item = self.item_repo.find_one({"item_id": item_id, "is_deleted": 0})
        if not item:
            raise ValueError(f"Item '{item_id}' not found")
        if qty <= 0:
            raise ValueError("Waste quantity must be greater than zero")

        # Deduct stock
        self.item_repo.decrement_stock(item_id, qty)
        self.inv_repo.record_stock_txn(
            item_id=item_id,
            item_name=item["name"],
            qty=-abs(qty),
            txn_type="waste",
            notes=f"Waste: {reason}",
            created_by=user_id,
        )
        return self.inv_repo.record_waste(
            item_id=item_id,
            item_name=item["name"],
            qty=qty,
            rate=rate,
            reason=reason,
            created_by=user_id,
        )

    def get_stock_transactions(self, item_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {}
        if item_id:
            filter_doc["item_id"] = item_id
        return self.inv_repo.stock_txns.find(filter_doc, sort=[("date", -1)], limit=limit)

    def get_waste_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.inv_repo.waste_logs.find({}, sort=[("date", -1)], limit=limit)

    def get_crate_transactions(self, party_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {}
        if party_id:
            filter_doc["party_id"] = party_id
        return self.inv_repo.crate_txns.find(filter_doc, sort=[("date", -1)], limit=limit)
