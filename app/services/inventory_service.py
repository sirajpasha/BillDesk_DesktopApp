from __future__ import annotations
from app.utils import validation as V
from typing import Any, Dict, List, Optional
from app.repositories.master_repo import ItemRepository
from app.repositories.inventory_repo import InventoryRepository
from app.services.ledger_service import LedgerService
from app.database.connection import transactional

class InventoryService:
    def __init__(self, db: Any):
        self.db = db
        self.item_repo = ItemRepository(db)
        self.inv_repo = InventoryRepository(db)
        self.ledger = LedgerService(db)

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

    @transactional
    def adjust_stock(self, item_id: str, delta_qty: float, reason: str, user_id: str = "system") -> Dict[str, Any]:
        """Manually adjust item stock (+ or -) with mandatory reason and immutable audit log."""
        item = self.item_repo.find_by_alias_or_id((item_id or "").strip())
        if not item:
            raise ValueError(f"Item '{item_id}' not found")
        item_id = item["item_id"]
        delta_qty = V.number(delta_qty, "Adjustment quantity", minimum=-10_000_000, maximum=10_000_000)
        if delta_qty == 0:
            raise ValueError("Adjustment quantity cannot be zero")
        if not (reason or "").strip():
            raise ValueError("A reason is required for a stock adjustment")

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

    @transactional
    def record_waste(self, item_id: str, qty: float, rate: float, reason: str, user_id: str = "system") -> Dict[str, Any]:
        """Record produce spoilage/waste, decrement stock, and log financial loss."""
        item = self.item_repo.find_by_alias_or_id((item_id or "").strip())
        if not item:
            raise ValueError(f"Item '{item_id}' not found")
        item_id = item["item_id"]
        qty = V.number(qty, "Waste quantity", greater_than=0, maximum=10_000_000)
        rate = V.number(rate, "Waste rate", minimum=0, maximum=1_000_000)
        if not (reason or "").strip():
            raise ValueError("A reason is required to log waste")
        on_hand = float(item.get("stock") or 0.0)
        # on_hand == 0 means stock is not tracked for this item; only reject when tracked stock is exceeded
        if on_hand > 0 and qty > on_hand + 1e-9:
            raise ValueError(f"Waste quantity {qty:g} exceeds stock on hand {on_hand:g}")

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
        waste = self.inv_repo.record_waste(
            item_id=item_id,
            item_name=item["name"],
            qty=qty,
            rate=rate,
            reason=reason,
            created_by=user_id,
        )
        self.ledger.post_waste(waste, user_id=user_id)
        return waste

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
