from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

class StockTransaction(BaseModel):
    transaction_id: str
    item_id: str
    item_name: str
    qty: float  # Negative for sale/waste, positive for purchase/receipt, signed for adjustment
    company_id: Optional[str] = None
    type: str  # sale, purchase, waste, adjustment
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: int = 0
    created_by: str

class WasteLog(BaseModel):
    waste_id: str
    item_id: str
    item_name: str
    qty: float
    rate: float = 0.0
    amount: float = 0.0
    company_id: Optional[str] = None
    reason: str
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: int = 0
    created_by: str

class CrateTransaction(BaseModel):
    txn_id: str
    party_id: str
    party_type: str  # customer or supplier
    item_id: str
    item_name: str
    issued_qty: float = 0.0
    returned_qty: float = 0.0
    reference_id: Optional[str] = None
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
    created_by: str
