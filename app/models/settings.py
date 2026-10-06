from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class Session(BaseModel):
    session_id: str
    user_id: str
    username: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    opening_cash: float = 0.0
    expected_cash: float = 0.0
    actual_cash: float = 0.0
    difference: float = 0.0
    status: str = "open"  # open, closed
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SystemSettings(BaseModel):
    setting_key: str = "general_config"
    backup_schedule: List[str] = Field(default_factory=lambda: ["00:00", "15:00"])
    backup_target: str = "local"
    local_retention_days: int = 7
    invoice_number_format: str = "yyyymmdd-xxxx"
    date_format: str = "dd/mm/yyyy"
    default_commission_rate: float = 0.0
    default_mandi_fee_rate: float = 0.0
    print_header_color: str = "#ed286c"
    default_layout_id: str = "default"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = "system"

class PrintBlock(BaseModel):
    id: str
    type: str
    config: dict = Field(default_factory=dict)

class PrintLayout(BaseModel):
    layout_id: str
    name: str
    page_size_type: str = "A4"
    width_mm: float = 210.0
    margin_mm: float = 10.0
    font_family: str = "Helvetica"
    blocks: List[PrintBlock] = Field(default_factory=list)
    font_size: str = "10pt"
    primary_color: str = "#1e6091"
    secondary_color: str = "#333333"
    is_default: bool = True
