"""UX audit, tier 2: dashboard that answers questions, item hint, history layout, unique shortcuts."""
import tkinter as tk
from datetime import datetime, timedelta

import pytest

from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.ui.billing import BillingFrame
from app.ui.dashboard import DashboardFrame
from app.ui.history import BillHistoryFrame
from tests.conftest import MockMongoDatabase


@pytest.fixture
def db():
    return MockMongoDatabase()


def _bill(db, inv, total, when, cust="C1"):
    db.collection("bills").insert_one({"invoice_no": inv, "customer_id": cust, "total_amount": total, "status": "unpaid",
                                       "is_deleted": 0, "invoice_date": when, "created_at": when})


def _dash(db, tk_root):
    f = DashboardFrame(tk_root, db, BillingService(db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    f.refresh()
    return f


def test_todays_sales_card_counts_todays_bills(db, tk_root):
    """Regression: the card compared a datetime with a "YYYY-MM-DD" string, so it always showed 0."""
    now = datetime.now()
    _bill(db, "T1", 500.0, now)
    _bill(db, "T2", 250.0, now)
    _bill(db, "Y1", 100.0, now - timedelta(days=1))
    f = _dash(db, tk_root)
    try:
        assert f.card_widgets["sales_today"][0].cget("text").endswith("750.00") and f.card_widgets["sales_today"][1].cget("text") == "2 bills"
        assert f.card_widgets["sales_yesterday"][1].cget("text") == "1 bills"
    finally:
        f.destroy()


def test_dashboard_leads_with_what_needs_attention(db, tk_root):
    db.collection("customers").insert_one({"cust_id": "C1", "name": "Raja", "current_balance": 900.0, "status": "active", "is_deleted": 0})
    db.collection("customers").insert_one({"cust_id": "C2", "name": "Metro", "current_balance": 100.0, "status": "active", "is_deleted": 0})
    _bill(db, "OLD", 900.0, datetime.now() - timedelta(days=50))
    _bill(db, "NEW", 100.0, datetime.now(), cust="C2")
    db.collection("orders").insert_one({"order_id": "O1", "status": "pending", "is_deleted": 0, "order_date": datetime.now()})
    db.collection("payments").insert_one({"payment_id": "P1", "party_id": "C1", "party_type": "customer", "amount": 300.0,
                                          "payment_date": datetime.now(), "is_deleted": 0})
    f = _dash(db, tk_root)
    try:
        v = {k: (a.cget("text"), b.cget("text")) for k, (a, b) in f.insight_vals.items()}
        assert v["receivable"][0].endswith("1,000.00") and v["receivable"][1].startswith("2 customers")
        assert v["overdue"][0].endswith("900.00")
        assert v["collected"] == ("₹ 300.00", "1 receipts") and v["pending"][0] == "1"
        owed = [w.cget("text") for line in f.top_owing_box.winfo_children() for w in line.winfo_children()]
        assert owed[0] == "Raja"
        assert max(val for _d, val in f._trend_data) == 100.0       # only NEW falls inside the 14-day trend
    finally:
        f.destroy()


def test_menu_shortcuts_are_not_assigned_twice(tk_root, seeded_mock_db):
    from app.services.auth_service import AuthService
    from app.ui.main_window import MainWindow
    auth = AuthService(seeded_mock_db)
    user = auth.login("admin", "admin123")
    win = MainWindow(tk_root, seeded_mock_db, auth, BillingService(seeded_mock_db), user)
    keys = [k for items in win.menus_config.values() for (_l, _p, k) in items if k and k.startswith("F")]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"shortcuts used twice in the menus: {dupes}"


def test_history_action_bar_is_packed_before_the_table(fake_db, tk_root):
    """Pack gives space in order: the buttons must come first or a short window clips them."""
    f = BillHistoryFrame(tk_root, fake_db, BillingService(fake_db))
    try:
        card = [w for w in f.winfo_children() if isinstance(w, tk.Frame) and any(c is f.tree.master for c in w.winfo_children())][0]
        slaves = card.pack_slaves()
        strip = f.btn_prev_inv.master
        assert slaves.index(strip) < slaves.index(f.tree.master)
    finally:
        f.destroy()


def test_item_hint_names_stock_and_rate_source(fake_db, tk_root):
    fake_db.collection("items").insert_one({"item_id": "H1", "item_alias": "H1", "name": "Hint Item", "unit": "Kg", "stock": 40,
                                            "standard_rate": 12.0, "status": "active", "is_deleted": 0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    try:
        r = f.row_widgets[0]
        r["code"].insert(0, "H1")
        f._on_code_entered(0)
        text = f.hint_lbl.cget("text")
        assert "Hint Item" in text and "Stock 40 Kg" in text and "item rate" in text
    finally:
        f.destroy()
