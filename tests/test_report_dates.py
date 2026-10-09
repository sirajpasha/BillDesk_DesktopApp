"""Report screens: a visible calendar on every date box, and Trial Balance / Profit & Loss / Balance Sheet with a period."""
import tkinter as tk
from datetime import date, datetime, timedelta, timezone
from tkinter import messagebox

import pytest

from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.ledger_service import LedgerService
from app.ui.financial_report_window import FinancialReportWindow, financial_year_start

USER = CurrentUser(user_id="U", username="admin", roles=["Admin"])


@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    return shown


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def _date_boxes(widget):
    return [w for w in _walk(widget) if isinstance(w, tk.Entry) and getattr(w, "_date_picker", None)]


def _noon(y, m, d):
    """Noon on that day, local wall-clock, stored the way the program stores journal dates (UTC)."""
    return datetime(y, m, d, 12, 0).astimezone(timezone.utc)


# ------------------------------------------------------------------ every date box on a report-type screen has its calendar button
def test_the_report_screens_show_a_calendar_button_beside_each_date_box(fake_db, tk_root, quiet):
    from app.ui.audit_view import AuditLogView
    from app.ui.consolidated_view import ConsolidatedReportFrame
    from app.ui.history import BillHistoryFrame
    from app.ui.orders_view import OrdersView
    from app.ui.reports_view import ReportsFrame
    from app.ui.statement_view import StatementWindow
    fake_db.collection("customers").insert_one({"cust_id": "C1", "name": "A", "current_balance": 0.0, "is_deleted": 0})
    screens = {
        "Reports (daybook, item-wise, customer-wise)": (ReportsFrame(tk_root, fake_db), 2),
        "Customer statement": (StatementWindow(tk_root, fake_db, "C1", "A"), 2),
        "Consolidated bills": (ConsolidatedReportFrame(tk_root, fake_db, BillingService(fake_db), current_user=USER), 2),
        "Bill history": (BillHistoryFrame(tk_root, fake_db, BillingService(fake_db)), 1),
        "Orders and matrix": (OrdersView(tk_root, fake_db, current_user=USER), 2),
        "Audit logs": (AuditLogView(tk_root, fake_db), 4),
    }
    try:
        for name, (screen, expected) in screens.items():
            boxes = _date_boxes(screen)
            assert len(boxes) == expected, f"{name}: {len(boxes)} date boxes"
            for b in boxes:
                btn = b._date_picker.button
                assert btn is not None and btn.cget("text") == "📅", f"{name}: no calendar button next to a date box"
                assert btn.master is b.master
                btn.invoke()                                            # the button opens the calendar
                assert b._date_picker.popup is not None, f"{name}: the button did not open the calendar"
                b._date_picker.popup.close()
    finally:
        for screen, _n in screens.values():
            screen.destroy()


# ------------------------------------------------------------------ the statements take a period
@pytest.fixture
def books(fake_db):
    """Sales of 100 in January, 250 in March, and 400 in April (all on account), each with a cost."""
    led = LedgerService(fake_db)
    for ref, (y, m, d), amount, cost in (("S1", (2026, 1, 10), 100.0, 60.0), ("S2", (2026, 3, 5), 250.0, 150.0), ("S3", (2026, 4, 2), 400.0, 240.0)):
        led.post_journal_entry(ref, "sale", [{"account_id": "1200", "debit": amount, "credit": 0.0}, {"account_id": "4000", "debit": 0.0, "credit": amount}],
                               "t", entry_date=_noon(y, m, d))
        led.post_journal_entry(ref, "cogs", [{"account_id": "5050", "debit": cost, "credit": 0.0}, {"account_id": "1300", "debit": 0.0, "credit": cost}],
                               "t", entry_date=_noon(y, m, d))
    return led


def test_the_ledger_filters_by_a_local_day_range(books):
    sales = lambda lo, hi: books.get_profit_and_loss(lo, hi)["total_sales"]            # noqa: E731
    assert sales(None, None) == 750.0
    assert sales(datetime(2026, 3, 1), datetime(2026, 3, 31, 23, 59, 59)) == 250.0
    assert sales(datetime(2026, 4, 2), datetime(2026, 4, 2, 23, 59, 59)) == 400.0        # a single day, including an entry made at midday
    assert sales(datetime(2026, 4, 3), None) == 0.0 and sales(None, datetime(2026, 1, 31)) == 100.0
    assert books.get_trial_balance(date_to=datetime(2026, 3, 31, 23, 59, 59))["total_debit"] == 350.0 + 210.0


def test_the_window_builds_each_statement_for_the_period_asked(books, fake_db, tk_root, quiet):
    from app.ui.finance_view import FinanceView
    fv = FinanceView(tk_root, fake_db, USER)
    try:
        win = fv._view_pl()
        assert isinstance(win, FinancialReportWindow) and win.mode == "range"
        assert win.from_picker is not None and win.to_picker is not None
        assert "All entries to date" in win.text and "750.00" in win.text
        win.from_picker.set(date(2026, 3, 1))
        win.to_picker.set(date(2026, 3, 31))
        win.show()
        assert "For the period 01/03/2026 to 31/03/2026" in win.text and "250.00" in win.text and "750.00" not in win.text
        assert fv.last_report[0] == "Profit & Loss" and fv.last_report[1] == win.text
        win.from_picker.set(date(2026, 3, 20))
        win.show()                                                              # To (31/03) is fine; now make To earlier than From
        win.to_picker.set(date(2026, 3, 1))
        win.show()
        assert quiet and quiet[-1][0] == "showwarning" and "cannot be before" in quiet[-1][2]
        win.destroy()

        tb = fv._view_trial_balance()
        assert tb.mode == "as_of" and tb.from_picker is None and tb.to_picker is not None
        tb.to_picker.set(date(2026, 1, 31))
        tb.show()
        assert "As of 31/01/2026" in tb.text and "100.00" in tb.text and "250.00" not in tb.text and "YES - ledger is balanced" in tb.text
        tb.destroy()

        bs = fv._view_balance_sheet()
        assert bs.mode == "as_of"
        bs.to_picker.set(date(2026, 3, 31))
        bs.show()
        assert "As of 31/03/2026" in bs.text and "YES - balance sheet balances" in bs.text
        bs.destroy()
    finally:
        fv.destroy()


def test_presets_fill_the_boxes_and_the_text_can_be_saved(books, fake_db, tk_root, quiet, monkeypatch, tmp_path):
    from app.ui.finance_view import FinanceView
    fv = FinanceView(tk_root, fake_db, USER)
    try:
        win = fv._view_pl()
        win._this_year()
        assert win.from_picker.value() == financial_year_start() and win.to_picker.value() == date.today()
        win._this_month()
        assert win.from_picker.value() == date.today().replace(day=1)
        win._all()
        assert win.from_ent.get() == "" and win.to_ent.get() == "" and "750.00" in win.text
        out = tmp_path / "pl.txt"
        monkeypatch.setattr("app.ui.financial_report_window.filedialog.asksaveasfilename", lambda **k: str(out))
        win.save_text()
        assert "PROFIT & LOSS STATEMENT" in out.read_text(encoding="utf-8")
        tb = fv._view_trial_balance()
        tb._last_month_end()
        assert tb.to_picker.value() == date.today().replace(day=1) - timedelta(days=1)
        tb._today()
        assert tb.to_picker.value() == date.today()
        for w in (win, tb):
            w.destroy()
    finally:
        fv.destroy()


def test_the_financial_year_starts_on_1_april():
    assert financial_year_start(date(2026, 10, 9)) == date(2026, 4, 1)
    assert financial_year_start(date(2026, 2, 3)) == date(2025, 4, 1)
    assert financial_year_start(date(2026, 4, 1)) == date(2026, 4, 1)


def test_the_statement_menu_entries_open_a_window_with_calendars(fake_db, tk_root, quiet):
    """Reports > Profit & Loss / Balance Sheet and Accounts > Trial Balance all go through the same windows."""
    from app.ui.finance_view import FinanceView
    fv = FinanceView(tk_root, fake_db, USER)
    try:
        for fn in (fv._view_trial_balance, fv._view_pl, fv._view_balance_sheet):
            w = fn()
            boxes = _date_boxes(w)
            assert boxes and all(b._date_picker.button is not None for b in boxes)
            w.destroy()
    finally:
        fv.destroy()
