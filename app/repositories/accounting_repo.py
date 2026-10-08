from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.base import BaseRepository

class AccountingRepository:
    def __init__(self, db: Any):
        self.db = db
        self.accounts = BaseRepository(db, "accounts")
        self.journals = BaseRepository(db, "journal_entries")
        self.ledger = BaseRepository(db, "ledger_transactions")
        self.payments = BaseRepository(db, "payments")
        self.bank_accounts = BaseRepository(db, "bank_accounts")
        self.bank_statements = BaseRepository(db, "bank_statements")
        self.internal_txns = BaseRepository(db, "internal_bank_transactions")
        self.misc = BaseRepository(db, "miscellaneous_entries")

    def next_payment_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"PAY-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def next_journal_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"JRN-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def next_ledger_txn_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"LTX-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def record_journal(
        self,
        reference: str,
        source_type: str,
        lines: List[Dict[str, Any]],
        created_by: str = "system",
        session: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Verify sum(debit) == sum(credit) before posting to journal_entries."""
        if len(lines) < 2:
            raise ValueError("A journal entry needs at least two lines")
        for l in lines:
            d, c = float(l.get("debit", 0.0) or 0.0), float(l.get("credit", 0.0) or 0.0)
            if d < 0 or c < 0:
                raise ValueError("Debit and credit amounts cannot be negative")
            if d > 0 and c > 0:
                raise ValueError("A journal line cannot have both a debit and a credit")
            if d == 0 and c == 0:
                raise ValueError("A journal line must have a debit or a credit amount")
        debits = sum(float(l.get("debit", 0.0)) for l in lines)
        credits = sum(float(l.get("credit", 0.0)) for l in lines)
        if abs(debits - credits) > 0.001:
            raise ValueError(f"Unbalanced journal entry: debits ({debits:.2f}) != credits ({credits:.2f})")

        doc = {
            "entry_id": self.next_journal_id(),
            "date": datetime.now(timezone.utc),
            "reference": reference,
            "source_type": source_type,
            "lines": lines,
            "state": "posted",
            "created_at": datetime.now(timezone.utc),
            "created_by": created_by,
        }
        return self.journals.insert_one(doc, session=session)
