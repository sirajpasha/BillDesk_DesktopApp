"""Every date box in the application: calendar drop-down, validation messages, and the forms that use them."""
import re
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox

import pytest

from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.ui.components.calendar_popup import CalendarPopup, attach_date_picker

USER = CurrentUser(user_id="U", username="admin", roles=["Admin"])
UI = Path(__file__).resolve().parent.parent / "app" / "ui"


@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    return shown


# ------------------------------------------------------------------ the shared box
def _box(tk_root, text="", **kw):
    e = tk.Entry(tk_root)
    e.insert(0, text)
    return e, attach_date_picker(e, "%d/%m/%Y", **kw)


def test_messages_say_what_is_wrong_in_plain_words(tk_root):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")
    e, p = _box(tk_root, "", allow_blank=False, label="The bill date")
    assert p.error() == "The bill date is required."
    e.insert(0, "31/02/2026")
    assert "not a valid date" in p.error() and "DD/MM/YYYY" in p.error()
    e.delete(0, tk.END)
    e.insert(0, tomorrow)
    assert p.error() is None
    e2, p2 = _box(tk_root, tomorrow, allow_future=False, label="The bill date")
    assert p2.error() == "The bill date cannot be in the future."
    e3, p3 = _box(tk_root, "01/01/2026")
    e4, p4 = _box(tk_root, "31/12/2025", not_before=p3.value, label="The To date")
    assert p4.error() == "The To date cannot be before 01/01/2026."
    for w in (e, e2, e3, e4):
        w.destroy()


def test_a_search_box_may_hold_part_of_a_date_and_an_optional_box_may_be_empty(tk_root):
    e, p = _box(tk_root, "09/2026", partial_ok=True)
    assert p.error() is None
    e2, p2 = _box(tk_root, "09/2026")
    assert p2.error() is not None
    e3, p3 = _box(tk_root, "")
    assert p3.error() is None and p3.value() is None
    for w in (e, e2, e3):
        w.destroy()


def test_invalid_text_turns_red_and_recovers(tk_root):
    e, p = _box(tk_root, "nonsense")
    normal = p._normal_fg
    p.flag()
    assert e.cget("fg") == "#dc2626"
    p.set(date(2026, 3, 1))
    assert e.get() == "01/03/2026" and e.cget("fg") == normal
    e.destroy()


def test_days_that_are_not_allowed_are_greyed_and_cannot_be_picked(tk_root):
    got = []
    e, p = _box(tk_root, date.today().strftime("%d/%m/%Y"), allow_future=False, on_selected=got.append)
    p.open()
    pop: CalendarPopup = p.popup
    pop._pick(date.today() + timedelta(days=2))
    assert got == [] and p.popup is not None and p.popup.winfo_exists()          # still open, nothing chosen
    pop._pick(date.today())
    assert got == [date.today()]
    e.destroy()


def test_the_to_box_cannot_pick_a_day_before_the_from_box(tk_root):
    f, pf = _box(tk_root, "10/03/2026")
    t, pt = _box(tk_root, "12/03/2026", not_before=pf.value)
    assert pt.allowed(date(2026, 3, 12)) and not pt.allowed(date(2026, 3, 9))
    for w in (f, t):
        w.destroy()


def test_enter_on_an_empty_optional_box_means_no_date_and_tells_the_form(tk_root):
    got = []
    e, p = _box(tk_root, "", on_selected=got.append)
    p._typed()
    assert got == [None]
    e.destroy()


# ------------------------------------------------------------------ every date box in the source has the calendar
def test_every_date_entry_in_the_screens_has_a_calendar_attached():
    """Source audit: an Entry named like a date box must be passed to attach_date_picker (or be the read-only payment date)."""
    problems = []
    for path in sorted(UI.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:self\.)?(\w*date\w*)\s*=\s*tk\.Entry\(", src):
            name = m.group(1)
            if name == "pay_date_ent":
                assert 'state="readonly"' in src                       # shown, not typed
                continue
            if not re.search(rf"attach_date_picker\((?:self\.)?{name}\b", src):
                problems.append(f"{path.name}: {name}")
    assert not problems, f"date boxes without the calendar: {problems}"


# ------------------------------------------------------------------ the forms
def test_new_order_dates_are_validated_and_the_cursor_follows(fake_db, tk_root, quiet):
    from app.ui.order_form_view import OrderFormView
    f = OrderFormView(tk_root, fake_db, current_user=USER)
    try:
        moved = []
        f.delivery_ent.focus_set = lambda: moved.append("delivery")
        f.focus_first_empty_row = lambda: moved.append("rows") or 0
        f.date_picker.on_selected(date.today())
        f.delivery_picker.on_selected(date.today())
        f.update()
        f.after(150)
        f.update()
        assert moved == ["delivery", "rows"]
        f.selected_customer = {"cust_id": "CUST001", "name": "Metro"}
        f.customer_var.set("Metro")
        r = f.row_widgets[0]
        r["code_var"].set("TOM"); r["item_var"].set("Tomato"); r["qty_var"].set("2"); r["rate_var"].set("10")
        f.date_var.set("45 - 13 - 2026")
        f._save_order()
        assert quiet[-1][0] == "showwarning" and "order date is not a valid date" in quiet[-1][2]
        f.date_var.set((date.today() + timedelta(days=2)).strftime("%d - %m - %Y"))
        f._save_order()
        assert "order date cannot be in the future" in quiet[-1][2]
        f.date_var.set(date.today().strftime("%d - %m - %Y"))
        f.delivery_var.set((date.today() - timedelta(days=1)).strftime("%d - %m - %Y"))
        f._save_order()
        assert "delivery date cannot be before" in quiet[-1][2]
        f.delivery_var.set("")
        f._save_order()
        assert "delivery date is required" in quiet[-1][2]
    finally:
        f.destroy()


def test_the_matrix_can_be_limited_to_one_delivery_date(fake_db):
    col = fake_db.collection("orders")
    for oid, days in (("O1", 1), ("O2", 1), ("O3", 3)):
        col.insert_one({"order_id": oid, "status": "pending", "is_deleted": 0, "customer_name": f"C{oid}", "order_date": datetime.now(),
                        "delivery_date": datetime.now() + timedelta(days=days),
                        "items": [{"item_id": "ITEM001", "name": "Tomato", "qty": 5.0, "unit": "kg"}]})
    svc = OrderService(fake_db)
    both = svc.get_order_matrix()
    assert sorted(both["customers"]) == ["CO1", "CO2", "CO3"]
    day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    one = svc.get_order_matrix(day)
    assert sorted(one["customers"]) == ["CO1", "CO2"] and one["rows"][0]["total_demand"] == 10.0


def test_the_matrix_screen_starts_with_all_orders_and_filters_when_a_date_is_picked(fake_db, tk_root, quiet):
    from app.ui.orders_view import OrdersView
    fake_db.collection("orders").insert_one({"order_id": "O9", "status": "pending", "is_deleted": 0, "customer_name": "Zed", "order_date": datetime.now(),
                                             "delivery_date": datetime.now() + timedelta(days=5),
                                             "items": [{"item_id": "ITEM001", "name": "Tomato", "qty": 4.0, "unit": "kg"}]})
    v = OrdersView(tk_root, fake_db, current_user=USER)
    try:
        assert v.matrix_date_var.get() == ""
        v.load_matrix()
        assert v.kpi_mat_custs.cget("text") != "0"
        v.matrix_date_var.set((date.today() + timedelta(days=9)).strftime("%d/%m/%Y"))
        v.load_matrix()
        assert v.kpi_mat_custs.cget("text") == "0" and "No pending orders" in " ".join(
            w.cget("text") for w in v.matrix_tree_frame.winfo_children() if isinstance(w, tk.Label))
        v.matrix_date_var.set("garbage")
        v.load_matrix()
        assert quiet[-1][0] == "showwarning"
    finally:
        v.destroy()


def test_consolidated_dates_default_to_this_month_and_are_checked(fake_db, tk_root, quiet):
    from app.ui.consolidated_view import ConsolidatedReportFrame
    f = ConsolidatedReportFrame(tk_root, fake_db, BillingService(fake_db), current_user=USER)
    try:
        assert f.from_date_var.get() == datetime.now().replace(day=1).strftime("%d-%m-%Y")
        assert f.to_date_var.get() == datetime.now().strftime("%d-%m-%Y")       # no longer fixed dates from August / October 2026
        f.selected_entity = {"name": "Metro", "cust_id": "CUST001"}
        f.from_date_var.set("20-09-2026")
        f.to_date_var.set("01-09-2026")
        f._generate_report()
        assert quiet[-1][0] == "showwarning" and "To date cannot be before 20-09-2026" in quiet[-1][2]
        f.from_date_var.set("")
        f._generate_report()
        assert "From date is required" in quiet[-1][2]
    finally:
        f.destroy()


def test_reports_and_statement_check_their_dates(fake_db, tk_root, quiet):
    from app.ui.reports_view import ReportsFrame
    from app.ui.statement_view import StatementWindow
    fake_db.collection("customers").insert_one({"cust_id": "C1", "name": "A", "current_balance": 0.0, "is_deleted": 0})
    r = ReportsFrame(tk_root, fake_db)
    s = StatementWindow(tk_root, fake_db, "C1", "A")
    try:
        r.from_var.set("15/02/2026")
        r.to_var.set("01/02/2026")
        r.refresh()
        assert quiet[-1][0] == "showwarning" and "cannot be before" in quiet[-1][2]
        r.from_var.set("2026-02-01")                                   # the old format is still understood
        r.to_var.set("2026-02-28")
        n = len(quiet)
        r.refresh()
        assert len(quiet) == n
        s.from_var.set("31/31/2026")
        s.refresh()
        assert "not a valid date" in quiet[-1][2]
        s.from_var.set("")
        s.to_var.set("")
        n = len(quiet)
        s.refresh()
        assert len(quiet) == n                                         # both optional
    finally:
        r.destroy()
        s.destroy()


def test_fixed_price_dates_are_checked_and_saved(fake_db, tk_root, quiet):
    from app.ui.masters_view import MastersView
    v = MastersView(tk_root, fake_db)
    try:
        v._add_fixed_price_dialog()
        dlg = [w for w in v.winfo_children() if isinstance(w, tk.Toplevel)][0]
        entries = [w for w in _walk(dlg) if isinstance(w, tk.Entry)]
        s_ent, e_ent = entries[-2], entries[-1]
        assert hasattr(s_ent, "_date_picker") and hasattr(e_ent, "_date_picker")
        assert s_ent.get() == date.today().strftime("%d/%m/%Y")
        assert e_ent._date_picker.value() == date.today() + timedelta(days=30)
        e_ent.delete(0, tk.END)
        e_ent.insert(0, "01/01/2020")
        assert "cannot be before" in e_ent._date_picker.error()
    finally:
        for w in list(v.winfo_children()):
            if isinstance(w, tk.Toplevel):
                w.destroy()
        v.destroy()


def test_bill_history_date_filter_has_the_calendar_and_accepts_partial_text(fake_db, tk_root):
    from app.ui.history import BillHistoryFrame
    f = BillHistoryFrame(tk_root, fake_db, BillingService(fake_db))
    try:
        p = f.date_ent._date_picker
        f.date_var.set("09/2026")
        assert p.error() is None
        f.date_var.set("")
        p.set(date(2026, 9, 11))
        assert f.date_var.get() == "11/09/2026"
    finally:
        f.destroy()


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def test_the_drop_down_opens_under_its_box_not_in_the_screen_corner(tk_root):
    """Regression: setting -topmost after the position reset the pop-up to (0, 0)."""
    top = tk.Toplevel(tk_root)
    top.geometry("700x300+150+120")
    e = tk.Entry(top)
    e.place(x=420, y=60)
    top.update()
    try:
        p = attach_date_picker(e, "%d/%m/%Y")
        p.open()
        top.update()
        pop = p.popup
        assert (pop.winfo_x(), pop.winfo_y()) == (e.winfo_rootx(), e.winfo_rooty() + e.winfo_height() + 2)
        pop.close()
    finally:
        top.destroy()


def test_switching_screens_closes_a_calendar_left_open(tk_root):
    top = tk.Toplevel(tk_root)
    top.geometry("500x200+100+100")
    page = tk.Frame(top)
    page.pack()
    e = tk.Entry(page)
    e.pack()
    top.update()
    try:
        p = attach_date_picker(e, "%d/%m/%Y")
        p.open()
        top.update()
        assert p.popup is not None
        page.pack_forget()                                   # what show_page does to the screen being left
        top.update()
        assert p.popup is None
    finally:
        top.destroy()
