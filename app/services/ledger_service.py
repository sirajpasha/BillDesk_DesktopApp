from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.repositories.accounting_repo import AccountingRepository
from app.utils.currency import money

# Account codes used by the automatic postings (see DEFAULT_CHART_OF_ACCOUNTS).
CASH, BANK, RECEIVABLES, INVENTORY = "1000", "1100", "1200", "1300"
PAYABLES, TDS_PAYABLE, EQUITY = "2100", "2200", "3000"
SALES, FEE_INCOME = "4000", "4100"          # commission, and (for now) mandi fee / other charges
PURCHASES, WASTE, OPEX, COGS = "5000", "5100", "5200", "5050"

DEFAULT_CHART_OF_ACCOUNTS = [
    {"code": CASH, "name": "Cash on Hand", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": BANK, "name": "Bank Accounts", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": RECEIVABLES, "name": "Accounts Receivable (Debtors)", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": INVENTORY, "name": "Inventory / Stock", "type": "Asset", "root_type": "Asset", "is_bs_account": True},
    {"code": PAYABLES, "name": "Accounts Payable (Creditors)", "type": "Liability", "root_type": "Liability", "is_bs_account": True},
    {"code": TDS_PAYABLE, "name": "TDS Payable", "type": "Liability", "root_type": "Liability", "is_bs_account": True},
    {"code": EQUITY, "name": "Owner Capital / Equity", "type": "Equity", "root_type": "Equity", "is_bs_account": True},
    {"code": SALES, "name": "Produce Sales Revenue", "type": "Income", "root_type": "Income", "is_pl_account": True},
    {"code": FEE_INCOME, "name": "Commission & Mandi Fee Income", "type": "Income", "root_type": "Income", "is_pl_account": True},
    {"code": PURCHASES, "name": "Produce Purchases (direct expensing)", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
    {"code": COGS, "name": "Cost of Goods Sold", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
    {"code": WASTE, "name": "Spoilage & Waste Expense", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
    {"code": OPEX, "name": "Operating & Miscellaneous Expenses", "type": "Expense", "root_type": "Expense", "is_pl_account": True},
]


def settlement_account(method: Optional[str]) -> str:
    """Cash drawer for cash; everything else (UPI, cheque, NEFT/RTGS, card...) clears through the bank."""
    return CASH if (method or "Cash").strip().lower() == "cash" else BANK


class LedgerService:
    """Double-entry general ledger: automatic postings from business events and the financial statements."""

    def __init__(self, db: Any):
        self.db = db
        self.acc_repo = AccountingRepository(db)

    # ------------------------------------------------------------------ chart of accounts
    def get_accounts(self) -> List[Dict[str, Any]]:
        accs = self.acc_repo.accounts.find({"is_deleted": 0}, sort=[("code", 1)])
        if not accs:
            return DEFAULT_CHART_OF_ACCOUNTS
        return accs

    def _account_index(self) -> Dict[str, Dict[str, Any]]:
        index = {a["code"]: a for a in DEFAULT_CHART_OF_ACCOUNTS}
        for a in self.get_accounts():
            if a.get("code"):
                index[str(a["code"])] = {**index.get(str(a["code"]), {}), **a}
        return index

    # ------------------------------------------------------------------ posting primitives
    def post_journal_entry(self, reference: str, source_type: str, lines: List[Dict[str, Any]],
                           user_id: str = "system", entry_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Post a strictly balanced double-entry journal record."""
        return self.acc_repo.record_journal(
            reference=reference, source_type=source_type, lines=lines, created_by=user_id, entry_date=entry_date
        )

    def has_entry(self, reference: str, source_type: str) -> bool:
        return self.acc_repo.journals.count_documents({"reference": reference, "source_type": source_type}) > 0

    @staticmethod
    def _balance_lines(debits: List[tuple], credits: List[tuple]) -> List[Dict[str, Any]]:
        """Build journal lines; any sub-paisa rounding difference is absorbed by the largest credit."""
        d = [(a, money(v)) for a, v in debits if money(v) > 0]
        c = [(a, money(v)) for a, v in credits if money(v) > 0]
        diff = round(sum(v for _, v in d) - sum(v for _, v in c), 2)
        if diff and c:
            i = max(range(len(c)), key=lambda k: c[k][1])
            c[i] = (c[i][0], round(c[i][1] + diff, 2))
        return ([{"account_id": a, "debit": v, "credit": 0.0} for a, v in d]
                + [{"account_id": a, "debit": 0.0, "credit": v} for a, v in c])

    # ------------------------------------------------------------------ automatic postings
    def post_sale(self, bill: Dict[str, Any], received: float = 0.0, method: str = "Cash",
                  user_id: str = "system", entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Sales invoice. Customer sale: Dr Receivables. Walk-in sale: Dr Cash/Bank for what was received,
        Dr Receivables only for any unpaid remainder."""
        total = money(bill.get("total_amount"))
        if total <= 0 or self.has_entry(bill["invoice_no"], "sale"):
            return None
        revenue = money(sum(float(i.get("amount", 0.0)) for i in bill.get("items", [])))
        fees = money(float(bill.get("commission_amt") or 0) + float(bill.get("mandi_fee_amt") or 0) + float(bill.get("other_charges") or 0))
        debits: List[tuple] = []
        if bill.get("customer_id") == "CASH":
            received = min(money(received), total)
            debits += [(settlement_account(method), received), (RECEIVABLES, total - received)]
        else:
            debits.append((RECEIVABLES, total))
        credits = [(SALES, revenue if revenue > 0 else total - fees), (FEE_INCOME, fees)]
        return self.post_journal_entry(bill["invoice_no"], "sale", self._balance_lines(debits, credits), user_id, entry_date)

    def post_cogs(self, invoice_no: str, cost: float, user_id: str = "system",
                  entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Cost of the goods sold (weighted-average cost): Dr COGS, Cr Inventory."""
        cost = money(cost)
        if cost <= 0 or self.has_entry(invoice_no, "cogs"):
            return None
        return self.post_journal_entry(invoice_no, "cogs", self._balance_lines([(COGS, cost)], [(INVENTORY, cost)]), user_id, entry_date)

    def post_receipt(self, payment: Dict[str, Any], user_id: str = "system",
                     entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Customer receipt: Dr Cash/Bank, Cr Receivables."""
        amt = money(payment.get("amount"))
        ref = payment.get("payment_id")
        if amt <= 0 or not ref or self.has_entry(ref, "receipt"):
            return None
        lines = self._balance_lines([(settlement_account(payment.get("payment_method")), amt)], [(RECEIVABLES, amt)])
        return self.post_journal_entry(ref, "receipt", lines, user_id, entry_date)

    def post_purchase_bill(self, bill: Dict[str, Any], user_id: str = "system",
                           entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Vendor bill: Dr Inventory (gross), Cr Payables (net of TDS), Cr TDS Payable."""
        gross = money(bill.get("total_amount"))
        ref = bill.get("purchase_id")
        if gross <= 0 or not ref or self.has_entry(ref, "purchase"):
            return None
        tds = money(bill.get("tds_amount"))
        lines = self._balance_lines([(INVENTORY, gross)], [(PAYABLES, gross - tds), (TDS_PAYABLE, tds)])
        return self.post_journal_entry(ref, "purchase", lines, user_id, entry_date)

    def post_supplier_payment(self, payment: Dict[str, Any], user_id: str = "system",
                              entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Payment to supplier: Dr Payables, Cr Cash/Bank."""
        amt = money(payment.get("net_amount_paid"))
        ref = payment.get("payment_id")
        if amt <= 0 or not ref or self.has_entry(ref, "supplier_payment"):
            return None
        lines = self._balance_lines([(PAYABLES, amt)], [(settlement_account(payment.get("payment_method")), amt)])
        return self.post_journal_entry(ref, "supplier_payment", lines, user_id, entry_date)

    def post_waste(self, waste: Dict[str, Any], user_id: str = "system",
                   entry_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """Spoilage: Dr Waste expense, Cr Inventory."""
        amt = money(waste.get("amount"))
        ref = waste.get("waste_id")
        if amt <= 0 or not ref or self.has_entry(ref, "waste"):
            return None
        return self.post_journal_entry(ref, "waste", self._balance_lines([(WASTE, amt)], [(INVENTORY, amt)]), user_id, entry_date)

    def reverse_entries(self, reference: str, source_types: List[str], user_id: str = "system",
                        entry_date: Optional[datetime] = None) -> int:
        """Post mirror-image entries for every un-reversed entry of `reference` (used when a bill is voided)."""
        n = 0
        for entry in self.acc_repo.journals.find({"reference": reference, "source_type": {"$in": source_types}, "state": "posted"}, limit=0):
            if entry.get("reversed_by"):
                continue
            mirror = [{"account_id": l["account_id"], "debit": float(l.get("credit", 0.0)), "credit": float(l.get("debit", 0.0))}
                      for l in entry.get("lines", [])]
            rev = self.acc_repo.record_journal(reference=reference, source_type=f"{entry['source_type']}_reversal",
                                               lines=mirror, created_by=user_id, entry_date=entry_date, extra={"reverses": entry["entry_id"]})
            self.acc_repo.journals.update_one({"entry_id": entry["entry_id"]}, {"$set": {"reversed_by": rev["entry_id"]}})
            n += 1
        return n

    # ------------------------------------------------------------------ reads & statements
    def get_journal_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.acc_repo.journals.find({}, sort=[("date", -1)], limit=limit)

    def get_account_balances(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Dict[str, float]]:
        """{code: {debit, credit}} summed over posted journals (optionally within a date range)."""
        query: Dict[str, Any] = {"state": "posted"}
        if date_from or date_to:
            rng: Dict[str, Any] = {}
            if date_from:
                rng["$gte"] = date_from
            if date_to:
                rng["$lte"] = date_to
            query["date"] = rng
        totals: Dict[str, Dict[str, float]] = {}
        for j in self.acc_repo.journals.find(query, limit=0):
            for line in j.get("lines", []):
                t = totals.setdefault(str(line.get("account_id", "Unknown")), {"debit": 0.0, "credit": 0.0})
                t["debit"] += float(line.get("debit", 0.0))
                t["credit"] += float(line.get("credit", 0.0))
        return totals

    def get_trial_balance(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Trial Balance: net debit/credit per account across all posted journals."""
        index = self._account_index()
        rows = []
        tot_debit = tot_credit = 0.0
        for code, t in sorted(self.get_account_balances(date_from, date_to).items()):
            net_debit = round(max(0.0, t["debit"] - t["credit"]), 2)
            net_credit = round(max(0.0, t["credit"] - t["debit"]), 2)
            tot_debit += net_debit
            tot_credit += net_credit
            rows.append({"account_code": code, "account_name": index.get(code, {}).get("name", "(unknown account)"),
                         "debit": net_debit, "credit": net_credit})
        return {
            "rows": rows,
            "total_debit": round(tot_debit, 2),
            "total_credit": round(tot_credit, 2),
            "is_balanced": abs(tot_debit - tot_credit) < 0.01,
        }

    def get_profit_and_loss(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Profit & Loss from the ledger: revenue - cost of goods sold - other expenses."""
        bal = self.get_account_balances(date_from, date_to)

        def credit_net(code: str) -> float:
            t = bal.get(code, {"debit": 0.0, "credit": 0.0})
            return round(t["credit"] - t["debit"], 2) + 0.0     # + 0.0 turns -0.0 into 0.0

        def debit_net(code: str) -> float:
            return 0.0 - credit_net(code)

        sales, fees = credit_net(SALES), credit_net(FEE_INCOME)
        cogs, waste, purchases, opex = debit_net(COGS), debit_net(WASTE), debit_net(PURCHASES), debit_net(OPEX)
        other_expense_codes = [c for c in bal if c.startswith("5") and c not in (COGS, WASTE, PURCHASES, OPEX)]
        other = round(sum(debit_net(c) for c in other_expense_codes), 2)
        other_income = round(sum(credit_net(c) for c in bal if c.startswith("4") and c not in (SALES, FEE_INCOME)), 2)
        revenue = round(sales + fees + other_income, 2)
        gross = round(revenue - cogs - purchases, 2)
        net = round(gross - waste - opex - other, 2)
        return {
            "total_sales": sales,
            "fee_income": fees,
            "other_income": other_income,
            "total_revenue": revenue,
            "cost_of_goods_sold": cogs,
            "total_purchases": purchases,          # only non-zero if purchases are expensed directly (legacy/manual)
            "gross_profit": gross,
            "total_waste": waste,
            "operating_expenses": round(opex + other, 2),
            "net_profit": net,
        }

    def get_balance_sheet(self, as_of: Optional[datetime] = None) -> Dict[str, Any]:
        """Balance Sheet: Assets = Liabilities + Equity (equity includes current earnings from the P&L accounts)."""
        index = self._account_index()
        bal = self.get_account_balances(date_to=as_of)
        assets, liabilities, equity = [], [], []
        for code, t in sorted(bal.items()):
            net = round(t["debit"] - t["credit"], 2)
            name = index.get(code, {}).get("name", "(unknown account)")
            if code.startswith("1"):
                assets.append({"account_code": code, "account_name": name, "amount": net})
            elif code.startswith("2"):
                liabilities.append({"account_code": code, "account_name": name, "amount": -net})
            elif code.startswith("3"):
                equity.append({"account_code": code, "account_name": name, "amount": -net})
        earnings = self.get_profit_and_loss(date_to=as_of)["net_profit"]
        equity.append({"account_code": "-", "account_name": "Current period profit / (loss)", "amount": earnings})
        total_assets = round(sum(a["amount"] for a in assets), 2)
        total_liab = round(sum(a["amount"] for a in liabilities), 2)
        total_equity = round(sum(a["amount"] for a in equity), 2)
        return {
            "assets": assets, "liabilities": liabilities, "equity": equity,
            "total_assets": total_assets, "total_liabilities": total_liab, "total_equity": total_equity,
            "is_balanced": abs(total_assets - (total_liab + total_equity)) < 0.01,
        }
