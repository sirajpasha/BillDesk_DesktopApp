from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class BillItem(BaseModel):
    item_id: str
    item_alias: Optional[str] = None
    name: str
    qty: float
    unit: str
    rate: float
    amount: float

BillLine = BillItem

class BillCreate(BaseModel):
    invoice_no: Optional[str] = None
    invoice_date: str
    customer_id: str
    customer_name: str
    items: List[BillItem]
    total_amount: float
    balance_due: float
    created_by: str
    commission_amt: float = 0.0
    mandi_fee_amt: float = 0.0
    other_charges: float = 0.0
    crates_issued: float = 0.0
    crates_returned: float = 0.0
    crate_item_id: Optional[str] = None
    notes: Optional[str] = None
    bill_type: str = "bill"

class Bill(BaseModel):
    invoice_no: str
    invoice_date: str
    due_date: Optional[datetime] = None
    customer_id: str
    customer_name: str
    company_id: Optional[str] = None
    total_amount: float
    balance_due: float = 0.0
    gl_account_id: str = "1200-AR"
    currency_code: str = "INR"
    version_number: int = 1
    linked_source_id: Optional[str] = None
    status: str = "unpaid"  # unpaid, partial, paid, void, cancelled
    is_voidable: bool = True
    is_deleted: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    items: List[BillItem]
    commission_amt: float = 0.0
    mandi_fee_amt: float = 0.0
    other_charges: float = 0.0
    crates_issued: float = 0.0
    crates_returned: float = 0.0
    crate_item_id: Optional[str] = None
    notes: Optional[str] = None
    bill_type: str = "bill"

class BillAudit(BaseModel):
    audit_id: str
    invoice_no: str
    action: str  # CREATE, UPDATE, VOID, DELETE
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = "local"
    user_agent: Optional[str] = "BillDesk Native"

class SalesReturnItem(BaseModel):
    item_id: str
    name: str
    qty: float
    unit: str
    rate: float
    amount: float
    is_waste: bool = False

class SalesReturn(BaseModel):
    return_id: str
    return_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    original_invoice_no: Optional[str] = None
    customer_id: str
    customer_name: str
    items: List[SalesReturnItem]
    total_refund_amount: float
    status: str = "completed"
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
