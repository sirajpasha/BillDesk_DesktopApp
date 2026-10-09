"""Read-only access to the audit trail: what was done to bills, and who signed in / did what."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.repositories.base import BaseRepository


def _dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str) and value:
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return d.replace(tzinfo=None) if d.tzinfo else d
        except ValueError:
            return None
    return None


def _describe(details: Any) -> str:
    if isinstance(details, dict):
        return ", ".join(f"{k}: {v}" for k, v in details.items() if v not in (None, ""))
    return str(details or "")


class AuditService:
    LIMIT = 2000

    def __init__(self, db: Any):
        self.db = db
        self.bill_audits = BaseRepository(db, "bill_audits")
        self.activity = BaseRepository(db, "user_activity_audits")

    @staticmethod
    def _range(date_from: Optional[datetime], date_to: Optional[datetime]) -> Dict[str, Any]:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        if date_to:
            rng["$lte"] = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        return rng

    @staticmethod
    def _matches(row: Dict[str, Any], query: str) -> bool:
        q = (query or "").strip().lower()
        return not q or any(q in str(v).lower() for v in row.values())

    def bill_changes(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, action: str = "", query: str = "") -> List[Dict[str, Any]]:
        """Newest first: CREATE, VOID, RETURN, RETURN_CANCELLED ... with the invoice, who did it and what changed."""
        flt: Dict[str, Any] = {}
        rng = self._range(date_from, date_to)
        if rng:
            flt["changed_at"] = rng
        if action and action.lower() != "all":
            flt["action"] = action
        rows = []
        for a in self.bill_audits.find(flt, sort=[("changed_at", -1)], limit=self.LIMIT):
            row = {"when": _dt(a.get("changed_at")), "user": a.get("changed_by", ""), "invoice_no": a.get("invoice_no", ""), "action": a.get("action", ""),
                   "field": a.get("field_changed") or "", "old": a.get("old_value") or "", "new": a.get("new_value") or ""}
            if self._matches(row, query):
                rows.append(row)
        return rows

    def user_activity(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, action: str = "", query: str = "") -> List[Dict[str, Any]]:
        flt: Dict[str, Any] = {}
        rng = self._range(date_from, date_to)
        if rng:
            flt["timestamp"] = rng
        if action and action.lower() != "all":
            flt["action"] = action
        rows = []
        for a in self.activity.find(flt, sort=[("timestamp", -1)], limit=self.LIMIT):
            row = {"when": _dt(a.get("timestamp")), "user": a.get("username", ""), "action": a.get("action", ""), "details": _describe(a.get("details"))}
            if self._matches(row, query):
                rows.append(row)
        return rows

    def bill_actions(self) -> List[str]:
        return sorted({a.get("action") for a in self.bill_audits.find({}, limit=0) if a.get("action")})

    def activity_actions(self) -> List[str]:
        return sorted({a.get("action") for a in self.activity.find({}, limit=0) if a.get("action")})
