from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timezone
from app.repositories.master_repo import FixedPriceRepository, ItemRepository

class PricingService:
    def __init__(self, db: Any):
        self.db = db
        self.price_repo = FixedPriceRepository(db)
        self.item_repo = ItemRepository(db)

    def resolve_rate(self, customer_id: str, item_id: str, when: Optional[datetime] = None, default_rate: float = 0.0) -> Tuple[float, bool]:
        """Resolves rate for a customer/item combination.
        Returns: (rate, is_fixed_price)
        """
        when = when or datetime.now(timezone.utc)
        fixed = self.price_repo.get_active_fixed_price(customer_id, item_id, when)
        if fixed and "rate" in fixed:
            return float(fixed["rate"]), True

        # Fallback to item standard rate / rate / default_rate
        item = self.item_repo.find_one({"item_id": item_id, "is_deleted": 0})
        if item:
            val = item.get("standard_rate") or item.get("rate") or item.get("default_rate")
            if val is not None:
                return float(val), False
            if default_rate:
                return float(default_rate), False
        return float(default_rate or 0.0), False
