from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid
from app.repositories.accounting_repo import AccountingRepository

class BankingService:
    def __init__(self, db: Any):
        self.db = db
        self.acc_repo = AccountingRepository(db)

    def get_bank_accounts(self) -> List[Dict[str, Any]]:
        return self.acc_repo.bank_accounts.find({"status": "active"})

    def save_bank_account(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        acc_id = account_data.get("account_id") or f"BNK-{uuid.uuid4().hex[:6].upper()}"
        account_data["account_id"] = acc_id
        if "created_at" not in account_data:
            account_data["created_at"] = datetime.now(timezone.utc)
        self.acc_repo.bank_accounts.insert_one(account_data)
        return account_data

    def get_statements(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        filter_doc = {}
        if account_id:
            filter_doc["account_id"] = account_id
        return self.acc_repo.bank_statements.find(filter_doc, sort=[("import_date", -1)])

    def auto_reconcile(self, account_id: str) -> Dict[str, Any]:
        """Auto-match statement lines against internal bank transactions based on reference and amount."""
        statements = self.acc_repo.bank_statements.find({"account_id": account_id, "status": "open"})
        internal_txns = self.acc_repo.internal_txns.find({"account_id": account_id, "reconciliation_status": "unreconciled"})

        matched_count = 0
        for stmt in statements:
            lines = stmt.get("lines", [])
            for line in lines:
                if line.get("reconciliation_status") == "reconciled":
                    continue

                ref = line.get("reference_no")
                amt = float(line.get("debit", 0.0) or line.get("credit", 0.0))

                for int_txn in internal_txns:
                    int_amt = float(int_txn.get("debit", 0.0) or int_txn.get("credit", 0.0))
                    int_ref = int_txn.get("reference_no")

                    if abs(amt - int_amt) < 0.01 and (ref and int_ref and ref == int_ref):
                        line["reconciliation_status"] = "reconciled"
                        line["matched_payment_id"] = int_txn.get("source_id")
                        self.acc_repo.internal_txns.update_one(
                            {"txn_id": int_txn["txn_id"]},
                            {"$set": {"reconciliation_status": "reconciled"}}
                        )
                        matched_count += 1
                        break

            self.acc_repo.bank_statements.update_one(
                {"statement_id": stmt["statement_id"]},
                {"$set": {"lines": lines}}
            )

        return {"matched_count": matched_count}

    def get_brs_report(self, account_id: str) -> Dict[str, Any]:
        """Compute Bank Reconciliation Statement (BRS)."""
        account = self.acc_repo.bank_accounts.find_one({"account_id": account_id})
        book_balance = float(account.get("current_balance", 0.0)) if account else 0.0

        unreconciled_receipts = sum(
            float(t.get("debit", 0.0)) for t in self.acc_repo.internal_txns.find(
                {"account_id": account_id, "reconciliation_status": "unreconciled", "debit": {"$gt": 0}}
            )
        )
        unreconciled_payments = sum(
            float(t.get("credit", 0.0)) for t in self.acc_repo.internal_txns.find(
                {"account_id": account_id, "reconciliation_status": "unreconciled", "credit": {"$gt": 0}}
            )
        )

        bank_balance = book_balance + unreconciled_payments - unreconciled_receipts
        return {
            "account_id": account_id,
            "book_balance": book_balance,
            "unreconciled_receipts": unreconciled_receipts,
            "unreconciled_payments": unreconciled_payments,
            "calculated_bank_balance": bank_balance,
        }
