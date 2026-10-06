from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

class User(BaseModel):
    user_id: str
    username: str
    password_hash: str
    email: str = ""
    phone: str = ""
    roles: List[str] = Field(default_factory=list)
    company_id: Optional[str] = None
    status: str = "active"
    is_deleted: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
    date_format: str = "dd/mm/yyyy"

class CurrentUser(BaseModel):
    user_id: str
    username: str
    roles: List[str]
    company_id: Optional[str] = None

class Role(BaseModel):
    role_id: str
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

class RolePermission(BaseModel):
    role: str
    menus: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCustomerMapping(BaseModel):
    user_id: str
    assigned_customer_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserActivityAudit(BaseModel):
    audit_id: str
    user_id: str
    username: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str
    details: Optional[dict] = None
    ip_address: str = "local"
    device_type: str = "Desktop"
    user_agent: str = "BillDesk Native"
