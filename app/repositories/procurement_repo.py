from __future__ import annotations
from typing import Any
from datetime import datetime
import uuid
from app.repositories.base import BaseRepository

class ProcurementRepository:
    def __init__(self, db: Any):
        self.db = db
        self.pos = BaseRepository(db, "purchase_orders")
        self.grns = BaseRepository(db, "grns")
        self.bills = BaseRepository(db, "purchase_bills")
        self.ap_payments = BaseRepository(db, "ap_payments")
        self.returns = BaseRepository(db, "purchase_returns")

    def next_po_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"PO-{date_str}-{uuid.uuid4().hex[:4].upper()}"

    def next_grn_number(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"GRN-{date_str}-{uuid.uuid4().hex[:4].upper()}"

    def next_purchase_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PUR-{date_str}-{uuid.uuid4().hex[:4].upper()}"

    def next_purchase_return_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"PRET-{date_str}-{uuid.uuid4().hex[:6].upper()}"

    def next_payment_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        return f"APPAY-{date_str}-{uuid.uuid4().hex[:6].upper()}"
