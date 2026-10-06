from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.base import BaseRepository

class InventoryRepository:
    """Manages stock transactions, waste logs, and crate transactions in pre-existing collections."""
    def __init__(self, db: Any):
        self.db = db
        self.stock_txns = BaseRepository(db, "stock_transactions")
        self.waste_logs = BaseRepository(db, "waste_logs")
        self.crate_txns = BaseRepository(db, "crate_transactions")

    def record_stock_txn(
        self,
        item_id: str,
        item_name: str,
        qty: float,
        txn_type: str,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
        created_by: str = "system",
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        doc = {
            "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "item_id": item_id,
            "item_name": item_name,
            "qty": qty,
            "type": txn_type,
            "reference_id": reference_id,
            "notes": notes,
            "date": datetime.now(timezone.utc),
            "is_deleted": 0,
            "created_by": created_by,
        }
        return self.stock_txns.insert_one(doc, session=session)

    def record_waste(
        self,
        item_id: str,
        item_name: str,
        qty: float,
        rate: float,
        reason: str,
        created_by: str = "system",
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        doc = {
            "waste_id": f"WST-{uuid.uuid4().hex[:8].upper()}",
            "item_id": item_id,
            "item_name": item_name,
            "qty": qty,
            "rate": rate,
            "amount": qty * rate,
            "reason": reason,
            "date": datetime.now(timezone.utc),
            "is_deleted": 0,
            "created_by": created_by,
        }
        return self.waste_logs.insert_one(doc, session=session)

    def record_crate_txn(
        self,
        party_id: str,
        party_type: str,
        item_id: str,
        item_name: str,
        issued_qty: float,
        returned_qty: float,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
        created_by: str = "system",
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        doc = {
            "txn_id": f"CRT-{uuid.uuid4().hex[:8].upper()}",
            "party_id": party_id,
            "party_type": party_type,
            "item_id": item_id,
            "item_name": item_name,
            "issued_qty": issued_qty,
            "returned_qty": returned_qty,
            "reference_id": reference_id,
            "notes": notes,
            "date": datetime.now(timezone.utc),
            "created_by": created_by,
        }
        return self.crate_txns.insert_one(doc, session=session)
