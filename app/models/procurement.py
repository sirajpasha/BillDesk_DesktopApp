from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class PurchaseItem(BaseModel):
    item_id: str
    name: str
    qty: float
    unit: str
    rate: float
    amount: float

class PurchaseOrder(BaseModel):
    po_id: str
    company_id: Optional[str] = None
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    supplier_id: str
    supplier_name: str
    items: List[PurchaseItem]
    total_amount: float
    status: str = "draft"  # draft, sent, partial_receive, closed, cancelled
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

class GRN(BaseModel):
    grn_id: str
    company_id: Optional[str] = None
    po_id: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    supplier_id: str
    supplier_name: str
    items: List[PurchaseItem]
    received_by: str
    status: str = "active"
    is_deleted: int = 0
    notes: Optional[str] = None

class PurchaseBill(BaseModel):
    purchase_id: str
    supplier_id: str
    supplier_name: str
    company_id: Optional[str] = None
    supplier_bill_no: Optional[str] = None
    bill_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: Optional[datetime] = None
    items: List[PurchaseItem]
    total_amount: float
    balance_due: float = 0.0
    tds_amount: float = 0.0
    tds_section_code: Optional[str] = None
    payable_amount: float = 0.0
    gst_compliance_status: str = "MATCHED"
    po_id: Optional[str] = None
    grn_id: Optional[str] = None
    is_approved: bool = False
    match_status: str = "pending"  # pending, matched, mismatch
    status: str = "active"  # active, paid, partial, hold, cancelled
    is_deleted: int = 0
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str

class APPayment(BaseModel):
    payment_id: str
    company_id: Optional[str] = None
    purchase_id: str
    supplier_id: str
    total_bill_amount: float
    tds_deducted: float = 0.0
    net_amount_paid: float
    payment_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payment_method: str = "NEFT"
    bank_account_id: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    is_deleted: int = 0
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
