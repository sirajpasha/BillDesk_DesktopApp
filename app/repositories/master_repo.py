from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.base import BaseRepository

class ItemRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "items")

    def search_items(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {"is_deleted": 0}
        if query:
            filter_doc["$or"] = [
                {"item_id": {"$regex": query, "$options": "i"}},
                {"item_alias": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"category": {"$regex": query, "$options": "i"}},
            ]
        return self.find(filter_doc, sort=[("name", 1)], limit=limit)

    def find_by_alias_or_id(self, code: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"$or": [{"item_alias": code}, {"item_id": code}], "is_deleted": 0})

    def decrement_stock(self, item_id: str, qty: float, session: Optional[Any] = None) -> bool:
        return self.update_one({"item_id": item_id}, {"$inc": {"stock": -abs(qty)}}, session=session)

    def increment_stock(self, item_id: str, qty: float, session: Optional[Any] = None) -> bool:
        return self.update_one({"item_id": item_id}, {"$inc": {"stock": abs(qty)}}, session=session)

class CustomerRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "customers")

    def search_customers(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {"is_deleted": 0}
        if query:
            filter_doc["$or"] = [
                {"cust_id": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"bill_to_name": {"$regex": query, "$options": "i"}},
                {"phone": {"$regex": query, "$options": "i"}},
            ]
        return self.find(filter_doc, sort=[("name", 1)], limit=limit)

    def update_balance(self, cust_id: str, delta: float, session: Optional[Any] = None) -> bool:
        return self.update_one({"cust_id": cust_id}, {"$inc": {"current_balance": delta}}, session=session)

class SupplierRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "suppliers")

    def search_suppliers(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        filter_doc = {"is_deleted": 0}
        if query:
            filter_doc["$or"] = [
                {"supplier_id": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"phone": {"$regex": query, "$options": "i"}},
                {"gst_number": {"$regex": query, "$options": "i"}},
            ]
        return self.find(filter_doc, sort=[("name", 1)], limit=limit)

    def update_balance(self, supplier_id: str, delta: float, session: Optional[Any] = None) -> bool:
        return self.update_one({"supplier_id": supplier_id}, {"$inc": {"current_balance": delta}}, session=session)

class FixedPriceRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "fixed_prices")

    def get_active_fixed_price(self, customer_id: str, item_id: str, when: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        when = when or datetime.now(timezone.utc)
        return self.find_one({
            "customer_id": customer_id,
            "item_id": item_id,
            "is_active": True,
            "start_date": {"$lte": when},
            "end_date": {"$gte": when},
        })

class CompanyRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "companies")

    def get_default_company(self) -> Optional[Dict[str, Any]]:
        """The company flagged is_default, else the first active company."""
        return (self.find_one({"is_default": True, "is_deleted": {"$ne": 1}})
                or self.find_one({"is_deleted": {"$ne": 1}}, sort=[("company_id", 1)]))

    def get_all(self) -> List[Dict[str, Any]]:
        """Active companies (soft-deleted ones stay in the database so old invoices still resolve their company)."""
        return self.find({"is_deleted": {"$ne": 1}}, sort=[("company_id", 1)], limit=0)

    def get_by_id(self, company_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"company_id": company_id})
