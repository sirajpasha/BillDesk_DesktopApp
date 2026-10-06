from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from app.repositories.base import BaseRepository

class OrderRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "orders")

    def next_order_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        prefix = f"ORD-{date_str}-"
        last = self.find_one({"order_id": {"$regex": f"^{prefix}"}}, sort=[("order_id", -1)])
        seq = 1
        if last:
            try:
                seq = int(last["order_id"].split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f"{prefix}{seq:04d}"

    def search_orders(
        self,
        query: str = "",
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        filter_doc: Dict[str, Any] = {"is_deleted": 0}
        if query:
            filter_doc["$or"] = [
                {"order_id": {"$regex": query, "$options": "i"}},
                {"customer_name": {"$regex": query, "$options": "i"}},
                {"customer_id": {"$regex": query, "$options": "i"}},
            ]
        if status:
            filter_doc["status"] = status
        return self.find(filter_doc, sort=[("order_date", -1)], limit=limit)
