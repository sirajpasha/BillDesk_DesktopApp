from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.accounting_repo import AccountingRepository

DEFAULT_CHART_OF_ACCOUNTS = [
    {"code": "1000", "name": "Cash on Hand", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": "1100", "name": "Bank Accounts", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": "1200", "name": "Accounts Receivable (Debtors)", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": "1300", "name": "Inventory / Stock", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": "2100", "name": "Accounts Payable (Creditors)", "type": "Liability", "root_type": "Liability", "is_bs_account": True},
    {"code": "2200", "name": "TDS Payable", "type": "Liability", "root_type": "Liability", "is_bs_account": True},
    {"code": "3000", "name": "Owner Capital / Equity", "type": "Equity", "root_type": "Equity", "is_bs_account": True},
    {"code": "4000", "name": "Produce Sales Revenue", "type": "Income", "root_type": "Income", "is_pl_account": True},
    {"code": "4100", "name": "Commission & Mandi Fee Income", "type": "Income", "root_type": "Income", "is_pl_account": True},
    {"code": "5000", "name": "Produce Purchases", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
    {"code": "5100", "name": "Spoilage & Waste Expense", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
    {"code": "5200", "name": "Operating & Miscellaneous Expenses", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
]

class LedgerService:
    def __init__(self, db: Any):
        self.db = db
        self.acc_repo = AccountingRepository(db)

    def get_accounts(self) -> List[Dict[str, Any]]:
        accs = self.acc_repo.accounts.find({"is_deleted": 0}, sort=[("code", 1)])
        if not accs:
            return DEFAULT_CHART_OF_ACCOUNTS
        return accs

    def post_journal_entry(
        self,
        reference: str,
        source_type: str,
        lines: List[Dict[str, Any]],
        user_id: str = "system"
    ) -> Dict[str, Any]:
        """Post a strictly balanced double-entry journal record."""
        return self.acc_repo.record_journal(
            reference=reference,
            source_type=source_type,
            lines=lines,
            created_by=user_id
        )

    def get_journal_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.acc_repo.journals.find({}, sort=[("date", -1)], limit=limit)

    def get_trial_balance(self) -> Dict[str, Any]:
        """Compute Trial Balance: sums debits and credits for all posted journals."""
        journals = self.acc_repo.journals.find({"state": "posted"})
        account_totals: Dict[str, Dict[str, float]] = {}

        for j in journals:
            for line in j.get("lines", []):
                code = line.get("account_id", "Unknown")
                if code not in account_totals:
                    account_totals[code] = {"debit": 0.0, "credit": 0.0}
                account_totals[code]["debit"] += float(line.get("debit", 0.0))
                account_totals[code]["credit"] += float(line.get("credit", 0.0))

        rows = []
        tot_debit = 0.0
        tot_credit = 0.0
        for code, totals in sorted(account_totals.items()):
            net_debit = max(0.0, totals["debit"] - totals["credit"])
            net_credit = max(0.0, totals["credit"] - totals["debit"])
            tot_debit += net_debit
            tot_credit += net_credit
            rows.append({
                "account_code": code,
                "debit": net_debit,
                "credit": net_credit,
            })

        return {
            "rows": rows,
            "total_debit": tot_debit,
            "total_credit": tot_credit,
            "is_balanced": abs(tot_debit - tot_credit) < 0.01,
        }

    def get_profit_and_loss(self) -> Dict[str, Any]:
        """Compute P&L: Total Revenue - Total Cost of Goods & Expenses."""
        bills = self.db.collection("bills").find({"status": {"$ne": "void"}, "is_deleted": 0})
        total_sales = sum(float(b.get("total_amount", 0.0)) for b in bills)

        purchases = self.db.collection("purchase_bills").find({"is_deleted": 0})
        total_purchases = sum(float(p.get("total_amount", 0.0)) for p in purchases)

        waste = self.db.collection("waste_logs").find({"is_deleted": 0})
        total_waste = sum(float(w.get("amount", 0.0)) for w in waste)

        gross_profit = total_sales - total_purchases
        net_profit = gross_profit - total_waste

        return {
            "total_sales": total_sales,
            "total_purchases": total_purchases,
            "total_waste": total_waste,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
        }
