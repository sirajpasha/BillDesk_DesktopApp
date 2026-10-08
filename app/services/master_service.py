from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.master_repo import (
    ItemRepository, CustomerRepository, SupplierRepository, FixedPriceRepository, CompanyRepository
)
from app.models.master import Item, Customer, Supplier, FixedPrice, Company
from app.config.settings import settings

class MasterService:
    def __init__(self, db: Any):
        self.db = db
        self.item_repo = ItemRepository(db)
        self.cust_repo = CustomerRepository(db)
        self.supp_repo = SupplierRepository(db)
        self.price_repo = FixedPriceRepository(db)
        self.company_repo = CompanyRepository(db)

    # ----------------- ITEMS -----------------
    def search_items(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        return self.item_repo.search_items(query, limit=limit)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.item_repo.find_one({"item_id": item_id, "is_deleted": 0})

    def save_item(self, item_data: Dict[str, Any], is_new: bool = False) -> Dict[str, Any]:
        item_id = item_data.get("item_id", "").strip()
        alias = item_data.get("item_alias", "").strip()
        if not item_id or not item_data.get("name", "").strip():
            raise ValueError("Item ID and Name are required")
        for rate_field in ("standard_rate", "rate", "default_rate"):
            if item_data.get(rate_field) is not None and float(item_data[rate_field]) < 0:
                raise ValueError("Item rate cannot be negative")

        if is_new:
            if self.item_repo.find_one({"item_id": item_id}):
                raise ValueError(f"Item ID '{item_id}' already exists")
            if alias and self.item_repo.find_one({"item_alias": alias}):
                raise ValueError(f"Item alias '{alias}' is already in use")
            doc = Item(**item_data).model_dump()
            self.item_repo.insert_one(doc)
            return doc
        else:
            if alias:
                existing = self.item_repo.find_one({"item_alias": alias, "item_id": {"$ne": item_id}})
                if existing:
                    raise ValueError(f"Item alias '{alias}' is already in use by another item")
            self.item_repo.update_one({"item_id": item_id}, {"$set": item_data})
            return item_data

    def delete_item(self, item_id: str) -> bool:
        # Soft delete
        return self.item_repo.update_one({"item_id": item_id}, {"$set": {"is_deleted": 1, "status": "inactive"}})

    # ----------------- CUSTOMERS -----------------
    def search_customers(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        return self.cust_repo.search_customers(query, limit=limit)

    def get_customer(self, cust_id: str) -> Optional[Dict[str, Any]]:
        return self.cust_repo.find_one({"cust_id": cust_id, "is_deleted": 0})

    def save_customer(self, cust_data: Dict[str, Any], is_new: bool = False) -> Dict[str, Any]:
        cust_id = cust_data.get("cust_id", "").strip()
        name = cust_data.get("name", "").strip()
        if not cust_id or not name:
            raise ValueError("Customer ID and Name are required")
        if cust_data.get("credit_limit") is not None and float(cust_data["credit_limit"]) < 0:
            raise ValueError("Credit limit cannot be negative")

        if is_new:
            if self.cust_repo.find_one({"cust_id": cust_id}):
                raise ValueError(f"Customer ID '{cust_id}' already exists")
            doc = Customer(**cust_data).model_dump()
            self.cust_repo.insert_one(doc)
            return doc
        else:
            # ledger-owned fields are changed only by bills/payments, never by editing the master record
            safe = {k: v for k, v in cust_data.items() if k not in ("current_balance", "crate_balances")}
            self.cust_repo.update_one({"cust_id": cust_id}, {"$set": safe})
            return safe

    def delete_customer(self, cust_id: str) -> bool:
        cust = self.cust_repo.find_one({"cust_id": cust_id, "is_deleted": 0})
        if cust and abs(float(cust.get("current_balance") or 0.0)) > 0.005:
            raise ValueError(f"Customer {cust_id} has an outstanding balance of {float(cust['current_balance']):.2f}; settle it before deleting")
        if self.db.collection("bills").find_one({"customer_id": cust_id, "status": {"$in": ["unpaid", "partial"]}, "is_deleted": 0}):
            raise ValueError(f"Customer {cust_id} has unpaid bills; settle them before deleting")
        return self.cust_repo.update_one({"cust_id": cust_id}, {"$set": {"is_deleted": 1, "status": "inactive"}})

    # ----------------- SUPPLIERS -----------------
    def search_suppliers(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        return self.supp_repo.search_suppliers(query, limit=limit)

    def get_supplier(self, supplier_id: str) -> Optional[Dict[str, Any]]:
        return self.supp_repo.find_one({"supplier_id": supplier_id, "is_deleted": 0})

    def save_supplier(self, supp_data: Dict[str, Any], is_new: bool = False) -> Dict[str, Any]:
        supplier_id = supp_data.get("supplier_id", "").strip()
        name = supp_data.get("name", "").strip()
        if not supplier_id or not name:
            raise ValueError("Supplier ID and Name are required")

        if is_new:
            if self.supp_repo.find_one({"supplier_id": supplier_id}):
                raise ValueError(f"Supplier ID '{supplier_id}' already exists")
            doc = Supplier(**supp_data).model_dump()
            self.supp_repo.insert_one(doc)
            return doc
        else:
            self.supp_repo.update_one({"supplier_id": supplier_id}, {"$set": supp_data})
            return supp_data

    # ----------------- FIXED PRICING -----------------
    def get_fixed_prices(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        filter_doc = {"is_active": True}
        if customer_id:
            filter_doc["customer_id"] = customer_id
        return self.price_repo.find(filter_doc, sort=[("start_date", -1)])

    def save_fixed_price(self, customer_id: str, item_id: str, rate: float, start_date: datetime, end_date: datetime, created_by: str = "system") -> Dict[str, Any]:
        if rate <= 0:
            raise ValueError("Fixed rate must be greater than zero")
        if start_date > end_date:
            raise ValueError("Start date must be before end date")

        # Deactivate existing active overlapping price
        self.price_repo.update_one(
            {"customer_id": customer_id, "item_id": item_id, "is_active": True},
            {"$set": {"is_active": False}}
        )

        doc = {
            "customer_id": customer_id,
            "item_id": item_id,
            "rate": rate,
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "created_by": created_by,
        }
        return self.price_repo.insert_one(doc)

    # ----------------- COMPANY -----------------
    def get_all_companies(self) -> List[Dict[str, Any]]:
        return self.company_repo.get_all()

    def get_company(self, company_id: Optional[str] = None) -> Dict[str, Any]:
        doc = None
        if company_id:
            doc = self.company_repo.get_by_id(company_id)
        if not doc:
            doc = self.company_repo.get_default_company()
        if not doc:
            doc = {
                "company_id": "Company0001",
                "name": settings.default_company_name,
                "address": "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.",
                "phone": "9380645132 , 9382179443 , 9444042275",
                "email": "info@svveg.com",
                "gst_number": "33ABCDE1234F1Z5",
                "terms_and_conditions": "",
                "signatory_label": "Authorized Signatory",
                "logo_url": "/images/logo.png"
            }
        return doc

    def save_company(self, data: Dict[str, Any]) -> Dict[str, Any]:
        company_id = data.get("company_id", "DEFAULT")
        existing = self.company_repo.find_one({"company_id": company_id})
        if existing:
            self.company_repo.update_one({"company_id": company_id}, {"$set": data})
        else:
            self.company_repo.insert_one(data)
        return data
