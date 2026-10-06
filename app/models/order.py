from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class OrderItem(BaseModel):
    item_id: str
    name: str
    qty: float
    unit: str
    rate: float = 0.0
    amount: float = 0.0

class OrderCreate(BaseModel):
    customer_id: str
    customer_name: str
    company_id: Optional[str] = None
    order_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    items: List[OrderItem]
    total_amount: float = 0.0
    status: Optional[str] = "pending"
    crates_issued: int = 0
    crates_returned: int = 0
    commission_amt: float = 0.0
    mandi_fee_amt: float = 0.0
    notes: Optional[str] = None
    created_by: str

class Order(BaseModel):
    order_id: str
    order_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivery_date: Optional[datetime] = None
    customer_id: str
    customer_name: str
    company_id: Optional[str] = None
    items: List[OrderItem]
    total_amount: float
    status: str = "pending"  # pending, confirmed, delivered, billed, cancelled
    crates_issued: int = 0
    crates_returned: int = 0
    commission_amt: float = 0.0
    mandi_fee_amt: float = 0.0
    linked_bill_ids: List[str] = Field(default_factory=list)
    linked_purchase_ids: List[str] = Field(default_factory=list)
    is_deleted: int = 0
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
