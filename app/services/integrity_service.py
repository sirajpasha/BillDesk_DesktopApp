"""Read-only data-integrity checks: do the books agree with each other?

Every check only READS. Each returns a result with a status:
  ok    - consistent            warn - needs a look (often legacy data / opening balances / not yet journaled)
  fail  - the data contradicts itself (a bug or manual database edit)   info - for your information
Run from the Accounts > Integrity Check screen or `python scripts/integrity_check.py`.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List

from app.repositories.base import BaseRepository
from app.services.ledger_service import LedgerService, RECEIVABLES

log = logging.getLogger(__name__)
TOL = 0.011                      # one paisa of rounding
MAX_DETAILS = 200
INVOICE_RE = re.compile(r"^\d{8}-\d{4,}$")
OPEN_STATUSES = ("unpaid", "partial")


def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


class IntegrityService:
    def __init__(self, db: Any):
        self.db = db
        self.ledger = LedgerService(db)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------ data access (one read per collection)
    def _rows(self, name: str, query: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        key = f"{name}:{query}"
        if key not in self._cache:
            self._cache[key] = BaseRepository(self.db, name).find(query or {}, limit=0)
        return self._cache[key]

    def _live(self, name: str) -> List[Dict[str, Any]]:
        return [r for r in self._rows(name) if not r.get("is_deleted")]

    @staticmethod
    def _result(cid: str, title: str, status: str, summary: str, details: List[str] | None = None) -> Dict[str, Any]:
        details = details or []
        extra = f"... and {len(details) - MAX_DETAILS} more" if len(details) > MAX_DETAILS else None
        return {"id": cid, "title": title, "status": status, "summary": summary,
                "details": details[:MAX_DETAILS] + ([extra] if extra else []), "count": len(details)}

    # ------------------------------------------------------------------ the checks
    def check_journals_balanced(self):
        bad = []
        for j in self._rows("journal_entries"):
            d = sum(_f(l.get("debit")) for l in j.get("lines", []))
            c = sum(_f(l.get("credit")) for l in j.get("lines", []))
            if abs(d - c) > TOL:
                bad.append(f"{j.get('entry_id')} ref {j.get('reference')}: debits {d:.2f} != credits {c:.2f}")
        tb = self.ledger.get_trial_balance()
        if bad:
            return self._result("ledger_balanced", "Every journal entry balances", "fail", f"{len(bad)} unbalanced entries", bad)
        if not self._rows("journal_entries"):
            return self._result("ledger_balanced", "Every journal entry balances", "info", "No journal entries yet")
        status = "ok" if tb["is_balanced"] else "fail"
        return self._result("ledger_balanced", "Every journal entry balances", status,
                            f"{len(self._rows('journal_entries'))} entries, trial balance {'balanced' if tb['is_balanced'] else 'OUT OF BALANCE'} "
                            f"(Dr {tb['total_debit']:,.2f} / Cr {tb['total_credit']:,.2f})")

    def check_balance_sheet(self):
        if not self._rows("journal_entries"):
            return self._result("balance_sheet", "Balance sheet balances (Assets = Liabilities + Equity)", "info", "No journal entries yet")
        bs = self.ledger.get_balance_sheet()
        return self._result("balance_sheet", "Balance sheet balances (Assets = Liabilities + Equity)", "ok" if bs["is_balanced"] else "fail",
                            f"Assets {bs['total_assets']:,.2f}; Liabilities {bs['total_liabilities']:,.2f} + Equity {bs['total_equity']:,.2f}")

    def check_receivables_vs_customers(self):
        customers = [c for c in self._live("customers")]
        subledger = round(sum(_f(c.get("current_balance")) for c in customers), 2)
        if not self._rows("journal_entries"):
            return self._result("ar_vs_customers", "Receivables ledger equals the sum of customer balances", "info",
                                f"No ledger yet (customer balances total {subledger:,.2f}); run scripts/backfill_ledger.py")
        t = self.ledger.get_account_balances().get(RECEIVABLES, {"debit": 0.0, "credit": 0.0})
        gl = round(t["debit"] - t["credit"], 2)
        diff = round(gl - subledger, 2)
        if abs(diff) <= TOL:
            return self._result("ar_vs_customers", "Receivables ledger equals the sum of customer balances", "ok", f"Both {gl:,.2f}")
        return self._result("ar_vs_customers", "Receivables ledger equals the sum of customer balances", "warn",
                            f"Ledger {gl:,.2f} vs customers {subledger:,.2f} (difference {diff:,.2f}). Usually opening balances that were never "
                            f"journaled, or history not yet backfilled.")

    def check_customer_balances(self):
        expected: Dict[str, float] = defaultdict(float)
        for b in self._live("bills"):
            if b.get("status") in OPEN_STATUSES and b.get("customer_id") != "CASH":
                expected[b["customer_id"]] += _f(b.get("balance_due"))
        for p in self._live("payments"):
            if p.get("party_type") == "customer":
                unallocated = _f(p.get("amount")) - sum(_f(a.get("amount")) for a in p.get("allocations", []))
                if unallocated > TOL:
                    expected[p.get("party_id")] -= unallocated
        bad = []
        for c in self._live("customers"):
            cid = c.get("cust_id")
            want, have = round(expected.get(cid, 0.0), 2), round(_f(c.get("current_balance")), 2)
            if abs(want - have) > TOL:
                bad.append(f"{cid} {c.get('name')}: balance {have:,.2f}, open bills less credit {want:,.2f} (difference {have - want:,.2f})")
        if not bad:
            return self._result("customer_balances", "Customer balance = open bills - unallocated payments", "ok",
                                f"{len(self._live('customers'))} customers agree")
        return self._result("customer_balances", "Customer balance = open bills - unallocated payments", "warn",
                            f"{len(bad)} of {len(self._live('customers'))} customers differ (opening balances or legacy data are common causes)", bad)

    def check_bill_arithmetic(self):
        bad = []
        for b in self._live("bills"):
            if b.get("status") == "void":
                continue
            lines = b.get("items", [])
            for l in lines:
                if abs(_f(l.get("qty")) * _f(l.get("rate")) - _f(l.get("amount"))) > TOL:
                    bad.append(f"{b['invoice_no']}: line '{l.get('name')}' {l.get('qty')} x {l.get('rate')} != {l.get('amount')}")
            want = sum(_f(l.get("amount")) for l in lines) + _f(b.get("commission_amt")) + _f(b.get("mandi_fee_amt")) + _f(b.get("other_charges"))
            if lines and abs(want - _f(b.get("total_amount"))) > TOL:
                bad.append(f"{b['invoice_no']}: total {_f(b.get('total_amount')):,.2f} but lines + charges = {want:,.2f}")
        n = len(self._live("bills"))
        return self._result("bill_arithmetic", "Bill totals equal their lines (qty x rate, charges)", "fail" if bad else "ok",
                            f"{len(bad)} problems in {n} bills" if bad else f"{n} bills consistent", bad)

    def check_bill_status(self):
        bad = []
        for b in self._live("bills"):
            st, due, total = b.get("status"), _f(b.get("balance_due")), _f(b.get("total_amount"))
            if st == "void" and abs(due) > TOL:
                bad.append(f"{b['invoice_no']}: void but balance due {due:,.2f}")
            elif st == "paid" and abs(due) > TOL:
                bad.append(f"{b['invoice_no']}: paid but balance due {due:,.2f}")
            elif st == "unpaid" and abs(due - total) > TOL:
                bad.append(f"{b['invoice_no']}: unpaid but balance due {due:,.2f} of {total:,.2f}")
            elif st == "partial" and not (TOL < due < total - TOL):
                bad.append(f"{b['invoice_no']}: partial but balance due {due:,.2f} of {total:,.2f}")
        return self._result("bill_status", "Bill status agrees with its balance due", "fail" if bad else "ok",
                            f"{len(bad)} inconsistent bills" if bad else "all statuses consistent", bad)

    def check_payments(self):
        invoices = {b["invoice_no"] for b in self._rows("bills") if b.get("invoice_no")}
        bad = []
        for p in self._live("payments"):
            allocs = p.get("allocations", [])
            if sum(_f(a.get("amount")) for a in allocs) > _f(p.get("amount")) + TOL:
                bad.append(f"{p.get('payment_id')}: allocated {sum(_f(a.get('amount')) for a in allocs):,.2f} of {_f(p.get('amount')):,.2f}")
            for a in allocs:
                if a.get("invoice_id") not in invoices:
                    bad.append(f"{p.get('payment_id')}: allocated to missing invoice {a.get('invoice_id')}")
        return self._result("payments", "Payments are fully backed by existing invoices", "fail" if bad else "ok",
                            f"{len(bad)} problems" if bad else f"{len(self._live('payments'))} payments consistent", bad)

    def check_invoice_numbers(self):
        nos = [b.get("invoice_no") for b in self._rows("bills") if b.get("invoice_no")]
        dup = [f"{n} appears {c} times" for n, c in Counter(nos).items() if c > 1]
        if dup:
            return self._result("invoice_numbers", "Invoice numbers are unique", "fail", f"{len(dup)} duplicated numbers", dup)
        odd = [n for n in nos if not INVOICE_RE.match(n)]
        gaps = []
        by_day: Dict[str, List[int]] = defaultdict(list)
        for n in nos:
            if INVOICE_RE.match(n):
                day, seq = n.split("-")
                by_day[day].append(int(seq))
        for day, seqs in by_day.items():
            missing = sorted(set(range(1, max(seqs) + 1)) - set(seqs))
            if missing:
                gaps.append(f"{day}: missing {', '.join(str(m) for m in missing[:8])}{'...' if len(missing) > 8 else ''}")
        status = "warn" if odd else "ok"
        msg = f"{len(nos)} numbers unique"
        if odd:
            msg += f"; {len(odd)} do not follow YYYYMMDD-NNNN"
        if gaps:
            msg += f"; {len(gaps)} day(s) have gaps in the sequence"
        return self._result("invoice_numbers", "Invoice numbers are unique and in sequence", status, msg,
                            [f"non-standard: {n}" for n in odd] + [f"gap {g}" for g in gaps])

    def check_ledger_coverage(self):
        def refs(source):
            return {j.get("reference") for j in self._rows("journal_entries") if j.get("source_type") == source}
        sales, receipts, purchases, supp, waste = refs("sale"), refs("receipt"), refs("purchase"), refs("supplier_payment"), refs("waste")
        gaps = []
        gaps += [f"bill {b['invoice_no']} has no sale entry" for b in self._live("bills")
                 if b.get("invoice_no") not in sales and _f(b.get("total_amount")) > 0]        # a zero-value bill has nothing to post
        gaps += [f"payment {p.get('payment_id')} has no receipt entry" for p in self._live("payments")
                 if p.get("party_type") == "customer" and p.get("payment_id") not in receipts and _f(p.get("amount")) > 0]
        gaps += [f"purchase bill {p.get('purchase_id')} has no entry" for p in self._live("purchase_bills") if p.get("purchase_id") not in purchases]
        gaps += [f"supplier payment {p.get('payment_id')} has no entry" for p in self._live("ap_payments") if p.get("payment_id") not in supp]
        gaps += [f"waste {w.get('waste_id')} has no entry" for w in self._live("waste_logs") if w.get("waste_id") not in waste and _f(w.get("amount")) > 0]
        return self._result("ledger_coverage", "Every transaction is posted to the ledger", "warn" if gaps else "ok",
                            (f"{len(gaps)} transactions are not in the ledger - run scripts/backfill_ledger.py" if gaps else "all transactions are journaled"), gaps)

    def check_void_reversals(self):
        reversed_sales = {j.get("reference") for j in self._rows("journal_entries") if j.get("source_type") == "sale_reversal"}
        sales = {j.get("reference") for j in self._rows("journal_entries") if j.get("source_type") == "sale"}
        bad = [f"{b['invoice_no']}: void but its sale entry was never reversed" for b in self._live("bills")
               if b.get("status") == "void" and b.get("invoice_no") in sales and b.get("invoice_no") not in reversed_sales]
        return self._result("void_reversals", "Voided bills are reversed in the ledger", "fail" if bad else "ok",
                            f"{len(bad)} voided bills still count as sales" if bad else "all voided bills reversed", bad)

    def check_references(self):
        cust_ids = {c.get("cust_id") for c in self._rows("customers")}
        invoices = {b.get("invoice_no") for b in self._rows("bills")}
        bad = []
        for b in self._live("bills"):
            if b.get("customer_id") not in cust_ids and b.get("customer_id") != "CASH":
                bad.append(f"bill {b['invoice_no']}: customer '{b.get('customer_id')}' not in the customer master")
        for o in self._live("orders"):
            for inv in o.get("linked_bill_ids", []) or []:
                if inv not in invoices:
                    bad.append(f"order {o.get('order_id')}: linked invoice {inv} does not exist")
            if o.get("status") == "billed" and not o.get("linked_bill_ids"):
                bad.append(f"order {o.get('order_id')}: billed but links no invoice")
        return self._result("references", "Bills and orders point at records that exist", "warn" if bad else "ok",
                            f"{len(bad)} dangling references" if bad else "all references resolve", bad)

    def check_stock(self):
        items = self._live("items")
        neg = [f"{i.get('item_id')} {i.get('name')}: stock {_f(i.get('stock')):g}" for i in items if _f(i.get("stock")) < -TOL]
        tracked = sum(1 for i in items if _f(i.get("stock")) > TOL)
        if neg:
            return self._result("stock", "No item has negative stock", "warn", f"{len(neg)} items below zero", neg)
        if items and tracked == 0:
            return self._result("stock", "No item has negative stock", "info",
                                f"Stock is not being tracked: all {len(items)} items are at 0 (goods receipts would start it)")
        return self._result("stock", "No item has negative stock", "ok", f"{tracked} items with stock, none negative")

    def check_supplier_balances(self):
        owed: Dict[str, float] = defaultdict(float)
        for p in self._live("purchase_bills"):
            owed[p.get("supplier_id")] += _f(p.get("balance_due"))
        bad = []
        for s in self._live("suppliers"):
            if abs(_f(s.get("current_balance")) - owed.get(s.get("supplier_id"), 0.0)) > TOL:
                bad.append(f"{s.get('supplier_id')} {s.get('name')}: balance {_f(s.get('current_balance')):,.2f}, open purchase bills {owed.get(s.get('supplier_id'), 0.0):,.2f}")
        return self._result("supplier_balances", "Supplier balance = open purchase bills", "warn" if bad else "ok",
                            f"{len(bad)} suppliers differ" if bad else "suppliers agree", bad)

    # ------------------------------------------------------------------ runner
    CHECKS: List[str] = [
        "check_journals_balanced", "check_balance_sheet", "check_receivables_vs_customers", "check_customer_balances",
        "check_bill_arithmetic", "check_bill_status", "check_payments", "check_invoice_numbers", "check_ledger_coverage",
        "check_void_reversals", "check_references", "check_stock", "check_supplier_balances",
    ]

    def run_all(self) -> Dict[str, Any]:
        self._cache.clear()
        results = []
        for name in self.CHECKS:
            fn: Callable[[], Dict[str, Any]] = getattr(self, name)
            try:
                results.append(fn())
            except Exception as exc:                       # a broken check must not hide the other results
                log.exception("Integrity check %s crashed", name)
                results.append(self._result(name, name, "fail", f"the check itself failed: {exc}"))
        summary = Counter(r["status"] for r in results)
        return {"run_at": datetime.now(), "checks": results,
                "summary": {k: summary.get(k, 0) for k in ("ok", "warn", "fail", "info")}}

    @staticmethod
    def format_report(report: Dict[str, Any], with_details: bool = True) -> str:
        icon = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", "info": "[INFO]"}
        s = report["summary"]
        out = [f"BillDesk integrity check - {report['run_at']:%d/%m/%Y %H:%M}",
               f"{s['ok']} ok, {s['warn']} warnings, {s['fail']} failures, {s['info']} notes", "=" * 78]
        for r in report["checks"]:
            out.append(f"{icon[r['status']]} {r['title']}\n        {r['summary']}")
            if with_details:
                out += [f"          - {d}" for d in r["details"][:25]]
                if len(r["details"]) > 25:
                    out.append(f"          ... {len(r['details']) - 25} more")
        return "\n".join(out)
