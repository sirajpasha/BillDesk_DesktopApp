"""Commission / mandi fee on orders: configurable rates (default 0 %), included in the total, carried to the bill."""
from datetime import datetime, timedelta
from tkinter import messagebox

import pytest

from app.config.settings import settings
from app.models.common import CurrentUser
from app.models.order import OrderCreate, OrderItem
from app.services.ledger_service import LedgerService
from app.services.order_service import OrderService
from app.ui.order_form_view import OrderFormView


@pytest.fixture
def form(fake_db, tk_root, monkeypatch):
    dialogs = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    fake_db.collection("items").insert_one({"item_id": "I1", "item_alias": "101", "name": "Apple", "unit": "Kg",
                                            "standard_rate": 20.0, "status": "active", "is_deleted": 0})
    v = OrderFormView(tk_root, fake_db, CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    v.dialogs = dialogs
    yield v
    v.destroy()


def _fill(v, qty="10"):
    v._parse_and_populate_lines(f"101 {qty}kg")                      # 10 x 20 = 200


def test_default_rates_are_zero_so_nothing_is_charged(form, fake_db):
    assert settings.commission_rate == 0 and settings.mandi_fee_rate == 0
    _fill(form)
    assert "₹200.00" in form.total_amount_lbl.cget("text")
    assert form.comm_lbl.cget("text") == "Comm: ₹ 0.00" and form.mandi_fee_lbl.cget("text") == "Mandi Fee: ₹ 0.00"


def test_configured_commission_is_shown_and_included_in_the_total(form, monkeypatch):
    monkeypatch.setattr(settings, "commission_rate", 5.0)
    _fill(form)
    assert "₹210.00" in form.total_amount_lbl.cget("text")
    assert form.comm_lbl.cget("text") == "Comm: ₹ 10.00 (5%)"
    assert form.mandi_fee_lbl.cget("text") == "Mandi Fee: ₹ 0.00"


def _save(form, fake_db):
    form.selected_customer = fake_db.collection("customers").find_one({"cust_id": "CUST001"})
    form.customer_var.set("Metro Retailers")
    today = datetime.now()
    form.date_var.set(today.strftime("%d - %m - %Y"))
    form.delivery_var.set((today + timedelta(days=1)).strftime("%d - %m - %Y"))
    form._save_order()
    return fake_db.collection("orders").find_one({})


def test_saved_order_total_includes_commission_and_mandi(form, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "commission_rate", 5.0)
    monkeypatch.setattr(settings, "mandi_fee_rate", 1.0)
    _fill(form)
    o = _save(form, fake_db)
    assert (o["commission_amt"], o["mandi_fee_amt"], o["total_amount"]) == (10.0, 2.0, 212.0)


def test_saved_order_with_default_rates_has_no_charges(form, fake_db):
    _fill(form)
    o = _save(form, fake_db)
    assert (o["commission_amt"], o["mandi_fee_amt"], o["total_amount"]) == (0.0, 0.0, 200.0)


def _order(db, commission=0.0, mandi=0.0):
    return OrderService(db).create_order(OrderCreate(
        customer_id="CUST001", customer_name="Metro Retailers", created_by="t", commission_amt=commission, mandi_fee_amt=mandi,
        items=[OrderItem(item_id="ITEM001", name="Tomato", qty=10.0, unit="kg", rate=20.0, amount=200.0)]))


def test_service_total_includes_the_charges_it_is_given(fake_db):
    assert _order(fake_db, 10.0, 2.0)["total_amount"] == 212.0


def test_conversion_carries_charges_to_the_bill_and_books_fee_income(fake_db):
    svc = OrderService(fake_db)
    o = _order(fake_db, commission=10.0, mandi=2.0)
    res = svc.convert_to_bill(o["order_id"], "admin")
    bill = fake_db.collection("bills").find_one({"invoice_no": res["invoice_no"]})
    assert (bill["commission_amt"], bill["mandi_fee_amt"], bill["total_amount"]) == (10.0, 2.0, 212.0)
    assert fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"] == 10212.0
    bal = LedgerService(fake_db).get_account_balances()
    assert bal["4100"]["credit"] == 12.0 and bal["4000"]["credit"] == 200.0 and bal["1200"]["debit"] == 212.0
    assert LedgerService(fake_db).get_trial_balance()["is_balanced"]


def test_orders_saved_before_charges_counted_convert_without_them(fake_db):
    """Old orders stored a commission figure but their total excluded it - customers must not suddenly be charged."""
    svc = OrderService(fake_db)
    o = _order(fake_db)
    fake_db.collection("orders").update_one({"order_id": o["order_id"]}, {"$set": {"commission_amt": 10.0, "mandi_fee_amt": 2.0}})
    res = svc.convert_to_bill(o["order_id"])
    bill = fake_db.collection("bills").find_one({"invoice_no": res["invoice_no"]})
    assert (bill["commission_amt"], bill["mandi_fee_amt"], bill["total_amount"]) == (0.0, 0.0, 200.0)
