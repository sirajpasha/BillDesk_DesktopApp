from __future__ import annotations
import base64
import csv
import io
import re
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
    GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")
    EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    PHONE_RE = re.compile(r"^[0-9+()\-\s,/]+$")
    COMPANY_FIELDS = ("name", "address", "phone", "email", "gst_number", "terms_and_conditions", "signatory_label", "logo_url")

    def get_all_companies(self) -> List[Dict[str, Any]]:
        return self.company_repo.get_all()

    def list_companies(self, query: str = "") -> List[Dict[str, Any]]:
        q = (query or "").strip().lower()
        rows = self.company_repo.get_all()
        if not q:
            return rows
        return [c for c in rows if any(q in str(c.get(k, "")).lower() for k in ("company_id", "name", "phone", "email", "gst_number", "address"))]

    def default_company_id(self) -> Optional[str]:
        comp = self.company_repo.get_default_company()
        return comp.get("company_id") if comp else None

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

    def _next_company_id(self) -> str:
        nums = []
        for c in self.company_repo.find({}, limit=0):
            m = re.fullmatch(r"Company(\d+)", str(c.get("company_id", "")))
            if m:
                nums.append(int(m.group(1)))
        return f"Company{(max(nums) + 1) if nums else 1:04d}"

    def _clean_company(self, data: Dict[str, Any]) -> Dict[str, Any]:
        clean = {k: (str(data[k]).strip() if data.get(k) is not None else "") for k in self.COMPANY_FIELDS if k in data}
        if "name" in clean and not clean["name"]:
            raise ValueError("Company name is required")
        if clean.get("gst_number"):
            clean["gst_number"] = clean["gst_number"].upper()
            if not self.GSTIN_RE.match(clean["gst_number"]):
                raise ValueError("GSTIN must be 15 letters/digits (leave it blank if not applicable)")
        if clean.get("email") and not self.EMAIL_RE.match(clean["email"]):
            raise ValueError("Email address is not valid")
        if clean.get("phone") and not self.PHONE_RE.match(clean["phone"]):
            raise ValueError("Phone may only contain digits, spaces and + ( ) - , /")
        return clean

    def save_company(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create (no company_id) or update (company_id given) a company. Names must be unique among active companies.
        `is_default=True` makes it the default company (invoices use it when a bill names no company)."""
        company_id = data.get("company_id")
        existing = self.company_repo.find_one({"company_id": company_id}) if company_id else None
        if company_id and not existing:
            raise ValueError(f"Company '{company_id}' not found")
        clean = self._clean_company(data if existing else {"name": "", **data})
        name = clean.get("name", existing.get("name") if existing else "")
        for c in self.company_repo.get_all():
            if c.get("company_id") != company_id and str(c.get("name", "")).strip().lower() == name.lower():
                raise ValueError(f"A company named '{name}' already exists")
        now = datetime.now(timezone.utc)
        if existing:
            self.company_repo.update_one({"company_id": company_id}, {"$set": {**clean, "updated_at": now}})
            saved_id = company_id
        else:
            saved_id = self._next_company_id()
            doc = {"company_id": saved_id, "terms_and_conditions": "", "signatory_label": "Authorized Signatory", "logo_url": "",
                   **clean, "is_deleted": 0, "created_at": now, "created_by": data.get("created_by", "system")}
            self.company_repo.insert_one(doc)
        no_default_yet = not self.company_repo.find_one({"is_default": True, "is_deleted": {"$ne": 1}})
        if data.get("is_default") or (no_default_yet and not existing and len(self.company_repo.get_all()) == 1):
            self.set_default_company(saved_id)
        return self.company_repo.find_one({"company_id": saved_id})

    def set_default_company(self, company_id: str) -> None:
        if not self.company_repo.find_one({"company_id": company_id, "is_deleted": {"$ne": 1}}):
            raise ValueError(f"Company '{company_id}' not found")
        self.db.collection("companies").update_many({"is_default": True}, {"$set": {"is_default": False}})
        self.company_repo.update_one({"company_id": company_id}, {"$set": {"is_default": True}})

    def company_usage(self, company_id: str) -> int:
        """How many bills name this company (they keep working after a delete: the company is only hidden)."""
        return self.db.collection("bills").count_documents({"company_id": company_id})

    def delete_company(self, company_id: str) -> bool:
        comp = self.company_repo.find_one({"company_id": company_id, "is_deleted": {"$ne": 1}})
        if not comp:
            raise ValueError(f"Company '{company_id}' not found")
        if company_id == self.default_company_id():
            raise ValueError("This is the default company. Make another company the default before deleting it.")
        if len(self.company_repo.get_all()) <= 1:
            raise ValueError("At least one company must remain")
        self.company_repo.update_one({"company_id": company_id}, {"$set": {"is_deleted": 1, "deleted_at": datetime.now(timezone.utc)}})
        return True

    @staticmethod
    def logo_data_uri(path: str, max_px: int = 256) -> str:
        """Read an image file and return a small PNG data URI (kept small: it is stored inside the company document)."""
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGBA")
            im.thumbnail((max_px, max_px))
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    CSV_COLUMNS = ("company_id", "name", "address", "phone", "email", "gst_number", "terms_and_conditions", "signatory_label")

    def export_companies_csv(self, path: str) -> int:
        rows = self.company_repo.get_all()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return len(rows)

    def import_companies_csv(self, path: str, created_by: str = "import") -> Dict[str, Any]:
        """Add companies from a CSV with a `name` column (other columns optional). Existing names are skipped, bad rows reported."""
        added, skipped, errors = 0, 0, []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for n, row in enumerate(csv.DictReader(f), start=2):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                row.pop("company_id", None)                               # ids are always assigned here
                if not row.get("name"):
                    errors.append(f"line {n}: name is empty")
                    continue
                try:
                    self.save_company({k: v for k, v in row.items() if k in self.COMPANY_FIELDS} | {"created_by": created_by})
                    added += 1
                except ValueError as exc:
                    if "already exists" in str(exc):
                        skipped += 1
                    else:
                        errors.append(f"line {n} ({row.get('name')}): {exc}")
        return {"added": added, "skipped": skipped, "errors": errors}
