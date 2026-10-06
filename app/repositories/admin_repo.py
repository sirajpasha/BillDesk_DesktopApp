from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.base import BaseRepository

class AdminRepository:
    def __init__(self, db: Any):
        self.db = db
        self.users = BaseRepository(db, "users")
        self.roles = BaseRepository(db, "roles")
        self.role_permissions = BaseRepository(db, "role_permissions")
        self.sessions = BaseRepository(db, "sessions")
        self.settings = BaseRepository(db, "system_settings")
        self.companies = BaseRepository(db, "companies")
        self.user_audits = BaseRepository(db, "user_activity_audits")

    def next_session_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"SES-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def get_settings(self) -> Dict[str, Any]:
        doc = self.settings.find_one({"setting_key": "general_config"})
        if not doc:
            doc = {
                "setting_key": "general_config",
                "invoice_number_format": "yyyymmdd-xxxx",
                "date_format": "dd/mm/yyyy",
                "default_commission_rate": 0.0,
                "default_mandi_fee_rate": 0.0,
            }
        return doc
