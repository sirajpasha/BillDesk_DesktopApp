from __future__ import annotations
from datetime import datetime, timezone
import uuid
from typing import Any, Optional

def format_date(dt: datetime | str | None, fmt: str = "%d/%m/%Y") -> str:
    """Format datetime or ISO string to standard date display."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(dt[:10], "%Y-%m-%d")
            except ValueError:
                return dt
    return dt.strftime(fmt)

def format_datetime(dt: datetime | str | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Format datetime or ISO string to standard date and time display."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    return dt.strftime(fmt)

def log_user_activity(
    db: Any,
    user_id: str,
    username: str,
    action: str,
    details: Optional[dict] = None,
    session: Any = None
) -> None:
    """Record user activity audit directly to pre-existing user_activity_audits collection."""
    kw = {"session": session} if session else {}
    doc = {
        "audit_id": f"AUD-{uuid.uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "username": username,
        "timestamp": datetime.now(timezone.utc),
        "action": action,
        "details": details or {},
        "ip_address": "local",
        "device_type": "Desktop",
        "user_agent": "BillDesk Native",
    }
    db.collection("user_activity_audits").insert_one(doc, **kw)
