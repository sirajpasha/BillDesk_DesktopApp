from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.base import BaseRepository

class BillRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "bills")

    def next_invoice_number(self, date_prefix: Optional[str] = None) -> str:
        prefix = date_prefix or (datetime.now().strftime("%Y%m%d") + "-")
        last = self.find_one({"invoice_no": {"$regex": f"^{prefix}"}}, sort=[("invoice_no", -1)])
        seq = 1
        if last:
            try:
                seq = int(last["invoice_no"].split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f"{prefix}{seq:04d}"

    def search_bills(
        self,
        query: str = "",
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        filter_doc: Dict[str, Any] = {"is_deleted": 0}
        if query:
            filter_doc["$or"] = [
                {"invoice_no": {"$regex": query, "$options": "i"}},
                {"customer_name": {"$regex": query, "$options": "i"}},
                {"customer_id": {"$regex": query, "$options": "i"}},
            ]
        if status:
            filter_doc["status"] = status
        if date_from or date_to:
            date_filter: Dict[str, Any] = {}
            if date_from:
                date_filter["$gte"] = date_from
            if date_to:
                date_filter["$lte"] = date_to
            filter_doc["invoice_date"] = date_filter
        return self.find(filter_doc, sort=[("created_at", -1)], limit=limit, skip=skip)

    def log_audit(
        self,
        invoice_no: str,
        action: str,
        changed_by: str,
        field_changed: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        session: Optional[Any] = None
    ) -> None:
        doc = {
            "audit_id": f"BA-{uuid.uuid4().hex[:10].upper()}",
            "invoice_no": invoice_no,
            "action": action,
            "field_changed": field_changed,
            "old_value": old_value,
            "new_value": new_value,
            "changed_by": changed_by,
            "changed_at": datetime.now(timezone.utc),
            "ip_address": "local",
            "user_agent": "BillDesk Native",
        }
        kw = {"session": session} if session else {}
        self.db.collection("bill_audits").insert_one(doc, **kw)

class SalesReturnRepository(BaseRepository):
    def __init__(self, db: Any):
        super().__init__(db, "sales_returns")

    def next_return_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"RET-{date_str}-{uuid.uuid4().hex[:6].upper()}"
