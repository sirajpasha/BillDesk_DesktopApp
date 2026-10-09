"""Every menu entry: where it goes, which tab it lands on, whether its key label is true, who may see it; and the audit-log screen."""
import re
import tkinter as tk
import types
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

import pytest

from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"Logout", "Exit"}                       # these end the session / the program

# the tab each page must land on ("" = the page has no tabs)
EXPECTED_TAB = {
    "New Bill": "", "New Order": "", "Orders": "Orders & Shipments", "Procurement": "Vendor Purchase Bills",
    "Item Master": "Item Master", "Customer Master": "Customer Master", "Supplier Master": "Supplier Master",
    "Inventory": "Live Stock Overview", "Waste Management": "Produce Waste Logs",
    "Bill History": "", "Daybook": "", "Item-wise Sales": "", "Customer-wise Sales": "", "Consolidated Billing": "",
    "Order Matrix": "Order Consolidation Matrix", "Fixed Rates": "Fixed Pricing", "Dashboard": "",
    "Finance": "Accounting Home", "Trial Balance": "General Ledger", "Profit & Loss": "General Ledger", "Balance Sheet": "General Ledger",
    "BRS": "Banking & BRS", "Handover & Settlement": "Cashier Drawer & Z-Report", "Integrity Check": "",
    "Accounts Receivables": "Accounts Receivable (AR)", "Accounts Payables": "Accounts Payable (AP)",
    "User Management": "Users & Access", "Company Settings": "", "DB Connection": "", "System Audit Logs": "Bill changes", "Help": "",
}


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


@pytest.fixture
def window(seeded_mock_db, tk_root, monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    auth = AuthService(seeded_mock_db)
    win = MainWindow(tk_root, seeded_mock_db, auth, BillingService(seeded_mock_db), auth.login("admin", "admin123"))
    win.shown = shown
    yield win
    for child in list(tk_root.winfo_children()):          # Windows allows only so many menus per process: give them back
        try:
            child.destroy()
        except tk.TclError:
            pass
    try:
        tk_root.config(menu="")
    except tk.TclError:
        pass


def _entries(win):
    for menu, items in win.menus_config.items():
        for it in items:
            yield menu, it


# ------------------------------------------------------------------ every entry works
def test_every_menu_entry_opens_its_screen_on_the_right_tab(window):
    seen = []
    for menu, (label, target, key) in _entries(window):
        if label == "---" or label in SKIP:
            continue
        window.shown.clear()
        window.show_page("Dashboard")
        window.show_page(target)
        expected_page = "Help" if target.startswith("Help:") else target
        assert window.active_page == expected_page, f"{menu} > {label} went to {window.active_page!r}"
        frame = window.frames[expected_page]
        assert frame.winfo_manager() == "pack", f"{menu} > {label}: the screen is not showing"
        others = [f for f in set(window.frames.values()) if f is not frame]
        assert all(f.winfo_manager() == "" for f in others), f"{menu} > {label}: two screens are showing at once"
        assert not window.shown, f"{menu} > {label} raised a message: {window.shown}"
        nb = next((w for w in _walk(frame) if isinstance(w, ttk.Notebook)), None)
        tab = nb.tab(nb.select(), "text") if nb is not None and nb.select() else ""
        assert tab == EXPECTED_TAB[expected_page], f"{menu} > {label} opened tab {tab!r}, expected {EXPECTED_TAB[expected_page]!r}"
        if expected_page in ("Daybook", "Item-wise Sales", "Customer-wise Sales"):
            assert window.reports_view.report_var.get() == expected_page
        seen.append(target)
        for t in [w for w in _walk(window.root) if isinstance(w, tk.Toplevel)]:      # the statements open a window by themselves
            t.destroy()
    assert len(seen) >= 30


def test_separators_are_not_clickable_entries(window):
    for _menu, (label, target, _key) in _entries(window):
        if label == "---":
            assert target == ""
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert 'item[0] == "---"' in src                         # drawn as a separator, not as a "---" button


def test_the_menu_widgets_match_the_menu_structure(window):
    bars = [w for w in _walk(window.root) if isinstance(w, tk.Menubutton)]
    assert [b.cget("text") for b in bars] == list(window.menus_config)
    for b in bars:
        menu = b.nametowidget(b.cget("menu"))
        labels = [menu.entrycget(i, "label").strip().split("    ")[0] for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        wanted = [lab for lab, _t, _k in window.menus_config[b.cget("text")] if lab != "---"]
        assert labels == wanted, b.cget("text")
        types_ = [menu.type(i) for i in range(menu.index("end") + 1)]
        assert types_.count("separator") == sum(1 for it in window.menus_config[b.cget("text")] if it[0] == "---")


def test_unknown_page_names_do_nothing_instead_of_opening_the_first_match(window):
    window.show_page("Dashboard")
    for bad in ("", "  ", "Bill", "Master", "nonsense"):
        window.show_page(bad)
        assert window.active_page == "Dashboard", bad
    window.show_page("bill history")                          # the same name in another case is fine
    assert window.active_page == "Bill History"


# ------------------------------------------------------------------ the key labels in the menus are true
def test_every_key_shown_in_a_menu_is_bound_and_goes_where_the_label_says(window):
    for _menu, (label, target, key) in _entries(window):
        if not key or key.startswith("Alt+") or label in SKIP:
            continue
        seq = window.key_sequence(key)
        assert seq in window.key_actions, f"{label}: {key} is shown in the menu but no key is bound to it"
        assert window.root.bind_all(seq), f"{label}: {key} is not bound in Tk"
        if target.startswith("Help:") or target in ("New Bill",):
            continue
        window.show_page("Dashboard")
        window.key_actions[seq]()
        assert window.active_page == target, f"{label}: pressing {key} went to {window.active_page!r}, not {target!r}"
        for t in [w for w in _walk(window.root) if isinstance(w, tk.Toplevel)]:
            t.destroy()
    window.show_page("Dashboard")
    window.key_actions["<F2>"]()
    assert window.active_page == "New Bill"
    window.key_actions["<F9>"]()
    assert window.active_page == "Help"


def test_function_keys_in_the_menus_are_unique(window):
    keys = [k for _m, (label, _t, k) in _entries(window) if k and label not in SKIP]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]


def test_dashboard_buttons_and_help_topics_only_point_at_real_screens(window):
    src = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    pages = set(window.frames) | {"Logout", "Exit"}
    named = set()
    for path in (ROOT / "app" / "ui").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        named |= set(re.findall(r'show_page\("([^"]+)"\)', text)) | set(re.findall(r'on_navigate\("([^"]+)"\)', text))
        named |= set(re.findall(r'\("[A-Za-z ]+", "[A-Za-z ]+", "([A-Za-z ]+)", "#', text))
    dead = sorted(p for p in named if p not in pages and not p.startswith("Help:"))
    assert not dead, f"show_page / on_navigate target screens that do not exist: {dead}"
    for tid in re.findall(r'"Help:([a-z-]+)"', src):
        assert window.help_view.svc.get(tid), f"the Help menu points at topic {tid!r} which does not exist"


# ------------------------------------------------------------------ who sees what
def _stub_for(db, username, password):
    auth = AuthService(db)
    stub = types.SimpleNamespace(auth=auth, current_user=auth.login(username, password))
    for name in ("has_access", "can_open"):
        setattr(stub, name, types.MethodType(getattr(MainWindow, name), stub))
    stub.PERMISSION_GROUPS, stub.PAGE_GROUPS = MainWindow.PERMISSION_GROUPS, MainWindow.PAGE_GROUPS
    return stub


@pytest.mark.parametrize("user,password", [("admin", "admin123"), ("manager", "manager123"), ("user", "user123")])
def test_a_menu_never_offers_a_screen_its_user_would_be_refused(seeded_mock_db, user, password):
    stub = _stub_for(seeded_mock_db, user, password)
    menus = MainWindow._build_menu_structure(stub)
    for menu, items in menus.items():
        for label, target, _key in items:
            if label == "---" or label in SKIP or target.startswith("Help"):
                continue
            assert stub.can_open(target), f"{user}: {menu} > {label} would answer 'Access Denied'"
    assert "Help" in menus and "File" in menus


def test_roles_see_the_menus_they_should(seeded_mock_db):
    def names(user, pw):
        m = MainWindow._build_menu_structure(_stub_for(seeded_mock_db, user, pw))
        return set(m), {t for items in m.values() for _l, t, _k in items}
    admin_menus, admin_pages = names("admin", "admin123")
    mgr_menus, mgr_pages = names("manager", "manager123")
    user_menus, user_pages = names("user", "user123")
    assert {"File", "Masters", "Reports", "Accounts", "Settings", "Help"} <= admin_menus
    assert "Settings" not in mgr_menus and {"Masters", "Accounts"} <= mgr_menus
    assert not {"Masters", "Accounts", "Settings"} & user_menus
    for sensitive in ("Inventory", "Waste Management", "Daybook", "Item-wise Sales", "Customer-wise Sales", "Item Master", "Finance", "System Audit Logs"):
        assert sensitive not in user_pages, f"a cashier is offered {sensitive}"
    assert {"Inventory", "Daybook", "Item-wise Sales"} <= mgr_pages and "System Audit Logs" not in mgr_pages and {"System Audit Logs", "User Management"} <= admin_pages
    assert {"New Bill", "Orders", "Bill History", "Help"} <= user_pages


# ------------------------------------------------------------------ System Audit Logs
@pytest.fixture
def trail(fake_db):
    now = datetime.now()
    b = fake_db.collection("bill_audits")
    for i, (action, who) in enumerate((("CREATE", "asha"), ("VOID", "ravi"), ("RETURN", "asha"))):
        b.insert_one({"audit_id": f"BA{i}", "invoice_no": f"2026-{i}", "action": action, "changed_by": who, "changed_at": now - timedelta(days=i * 10),
                      "field_changed": "status" if action == "VOID" else None, "old_value": "unpaid" if action == "VOID" else None, "new_value": "void" if action == "VOID" else None})
    a = fake_db.collection("user_activity_audits")
    a.insert_one({"audit_id": "A1", "username": "asha", "timestamp": now, "action": "login", "details": {"method": "password", "client": "native"}})
    a.insert_one({"audit_id": "A2", "username": "ravi", "timestamp": now - timedelta(days=40), "action": "login", "details": {"method": "password"}})
    return fake_db


def test_the_audit_service_lists_newest_first_and_filters(trail):
    svc = AuditService(trail)
    rows = svc.bill_changes()
    assert [r["action"] for r in rows] == ["CREATE", "VOID", "RETURN"] and rows[1]["new"] == "void" and rows[1]["user"] == "ravi"
    assert [r["action"] for r in svc.bill_changes(action="VOID")] == ["VOID"]
    assert [r["user"] for r in svc.bill_changes(query="ASHA")] == ["asha", "asha"]
    assert len(svc.bill_changes(date_from=datetime.now() - timedelta(days=15))) == 2
    assert len(svc.bill_changes(date_to=datetime.now() - timedelta(days=15))) == 1
    assert svc.bill_actions() == ["CREATE", "RETURN", "VOID"]
    act = svc.user_activity()
    assert [r["user"] for r in act] == ["asha", "ravi"] and "method: password" in act[0]["details"]
    assert len(svc.user_activity(date_from=datetime.now() - timedelta(days=30))) == 1


def test_the_audit_screen_shows_both_lists_and_checks_its_dates(trail, tk_root, monkeypatch, tmp_path):
    from app.ui.audit_view import AuditLogView
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    v = AuditLogView(tk_root, trail)
    try:
        assert len(v.bills.table.tree.get_children()) == 3 and len(v.activity.table.tree.get_children()) == 2
        assert "3 entries" in v.bills.count.cget("text")
        v.bills.action_var.set("VOID")
        v.bills.load()
        assert len(v.bills.table.tree.get_children()) == 1 and "1 entry" in v.bills.count.cget("text")
        v.bills.action_var.set("All")
        v.bills.from_ent.insert(0, "20/02/2026")
        v.bills.to_ent.insert(0, "01/02/2026")
        v.bills.load()
        assert shown and shown[-1][0] == "showwarning" and "cannot be before" in shown[-1][2]
        v.bills.from_ent.delete(0, tk.END)
        v.bills.to_ent.delete(0, tk.END)
        out = tmp_path / "audit.csv"
        monkeypatch.setattr("app.ui.audit_view.filedialog.asksaveasfilename", lambda **k: str(out))
        v.bills.load()
        v.bills.export()
        text = out.read_text(encoding="utf-8-sig")
        assert text.splitlines()[0].startswith("When,User,Invoice,Action") and "VOID" in text
    finally:
        v.destroy()


def test_a_real_bill_and_a_void_leave_their_trace_in_the_audit_log(fake_db):
    from app.models.billing import BillCreate, BillLine
    svc = BillingService(fake_db)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=1.0, unit="kg", rate=20.0, amount=20.0)
    inv = svc.create_bill(BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="CUST001", customer_name="x", items=[line],
                                     total_amount=20.0, balance_due=20.0, created_by="asha"))["invoice_no"]
    svc.void_bill(inv, user_id="ravi")
    rows = AuditService(fake_db).bill_changes(query=inv)
    assert {r["action"] for r in rows} >= {"CREATE", "VOID"} and {r["user"] for r in rows} >= {"asha", "ravi"}
