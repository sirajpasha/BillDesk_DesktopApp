from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Item(BaseModel):
    item_id: str
    item_alias: str = ""
    name: str
    unit: str = "kg"
    category: str = "Vegetables"
    company_id: Optional[str] = None
    stock: float = 0.0
    is_crate: bool = False
    status: str = "active"
    is_deleted: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class Customer(BaseModel):
    model_config = {"extra": "allow"}

    cust_id: str
    company_id: Optional[str] = None
    dc_company_id: Optional[str] = None
    name: str
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_person_name: Optional[str] = None
    contact_person_phone: Optional[str] = None
    contact_person_whatsapp: Optional[str] = None
    contact_person_email: Optional[str] = None
    bill_to_name: Optional[str] = None
    bill_to_address: Optional[str] = None
    bill_to_phone: Optional[str] = None
    bill_to_whatsapp: Optional[str] = None
    bill_to_email: Optional[str] = None
    phone: Optional[str] = None
    gst_number: Optional[str] = None
    opening_balance: float = 0.0
    opening_balance_date: Optional[datetime] = None
    opening_balance_type: str = "debit"
    current_balance: float = 0.0
    gl_control_id: str = "1200-AR"
    credit_limit: float = 0.0
    payment_terms_days: int = 30
    crate_balances: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    is_deleted: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class Supplier(BaseModel):
    supplier_id: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gst_number: Optional[str] = None
    company_id: Optional[str] = None
    opening_balance: float = 0.0
    opening_balance_date: Optional[datetime] = None
    opening_balance_type: str = "credit"
    current_balance: float = 0.0
    pan_number: Optional[str] = None
    msme_status: bool = False
    gl_control_id: str = "2100-AP"
    tds_applicable: bool = False
    tds_rate: float = 0.0
    tds_section: Optional[str] = None
    payment_terms_days: int = 30
    crate_balances: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "active"
    is_deleted: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class FixedPrice(BaseModel):
    customer_id: str
    item_id: str
    rate: float
    start_date: datetime
    end_date: datetime
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class Company(BaseModel):
    company_id: str
    name: str
    address: str
    phone: str
    email: str
    gst_number: Optional[str] = None
    terms_and_conditions: Optional[str] = (
        "1. Goods once sold will not be taken back.\n"
        "2. Interest @ 24% p.a. will be charged if bill is not paid within due date.\n"
        "3. Subject to City Jurisdiction only."
    )
    signatory_label: Optional[str] = "Authorized Signatory"
    logo_url: Optional[str] = "/images/logo.png"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
