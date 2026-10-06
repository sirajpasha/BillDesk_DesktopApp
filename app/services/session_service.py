from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.admin_repo import AdminRepository

class SessionService:
    def __init__(self, db: Any):
        self.db = db
        self.admin_repo = AdminRepository(db)

    def get_active_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.admin_repo.sessions.find_one({"user_id": user_id, "status": "open"})

    def open_session(self, user_id: str, username: str, opening_cash: float) -> Dict[str, Any]:
        """Open a new cashier drawer session."""
        active = self.get_active_session(user_id)
        if active:
            raise ValueError("You already have an open cashier session. Please close it first.")

        session_id = self.admin_repo.next_session_id()
        now = datetime.now(timezone.utc)
        doc = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "start_time": now,
            "opening_cash": opening_cash,
            "expected_cash": opening_cash,
            "actual_cash": 0.0,
            "difference": 0.0,
            "status": "open",
            "created_at": now,
        }
        return self.admin_repo.sessions.insert_one(doc)

    def compute_expected_cash(self, session_id: str) -> float:
        """Calculate expected drawer cash: opening_cash + cash sales + cash receipts - cash refunds."""
        session = self.admin_repo.sessions.find_one({"session_id": session_id})
        if not session:
            return 0.0

        opening = float(session.get("opening_cash", 0.0))
        start_time = session.get("start_time")

        # Cash sales
        cash_bills = self.db.collection("bills").find({
            "created_by": session["username"],
            "created_at": {"$gte": start_time},
            "status": {"$ne": "void"},
            "is_deleted": 0,
        })
        cash_sales = sum(float(b.get("total_amount", 0.0)) for b in cash_bills)

        # Cash receipts
        cash_payments = self.db.collection("payments").find({
            "created_by": session["username"],
            "created_at": {"$gte": start_time},
            "payment_method": "Cash",
            "is_deleted": 0,
        })
        cash_receipts = sum(float(p.get("amount", 0.0)) for p in cash_payments)

        return opening + cash_sales + cash_receipts

    def close_session(self, session_id: str, actual_cash: float, notes: str = "") -> Dict[str, Any]:
        """Close cashier drawer session, calculate variance (actual - expected), and return Z-report."""
        session = self.admin_repo.sessions.find_one({"session_id": session_id})
        if not session:
            raise ValueError(f"Session '{session_id}' not found")
        if session.get("status") == "closed":
            raise ValueError(f"Session '{session_id}' is already closed")

        expected = self.compute_expected_cash(session_id)
        difference = actual_cash - expected
        now = datetime.now(timezone.utc)

        update_data = {
            "end_time": now,
            "expected_cash": expected,
            "actual_cash": actual_cash,
            "difference": difference,
            "status": "closed",
            "notes": notes,
        }
        self.admin_repo.sessions.update_one({"session_id": session_id}, {"$set": update_data})
        session.update(update_data)
        return session
