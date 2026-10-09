"""What can be typed into the forms: shared checks, service rules behind every form, and the forms' messages."""
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import messagebox, ttk

import pytest

from app.models.common import CurrentUser
from app.services.admin_service import AdminService
from app.services.banking_service import BankingService
from app.services.inventory_service import InventoryService
from app.services.master_service import MasterService
from app.services.payment_service import PaymentService
from app.services.procurement_service import ProcurementService
from app.services.session_service import SessionService
from app.utils import validation as V
from tests.conftest import MockMongoDatabase

NAN, INF = float("nan"), float("inf")
USER = CurrentUser(user_id="U", username="admin", roles=["Admin"])
NOW = datetime.now(timezone.utc)


# ------------------------------------------------------------------ the shared checks
@pytest.mark.parametrize("value,kwargs,ok", [
    ("12.5", {}, 12.5), ("1,250", {}, 1250.0), (7, {"minimum": 0}, 7.0), ("", {"required": False, "default": 3.0}, 3.0),
])
def test_number_accepts_real_numbers(value, kwargs, ok):
    assert V.number(value, "Rate", **kwargs) == ok


@pytest.mark.parametrize("value,kwargs,message", [
    ("abc", {}, "Rate must be a number."), ("nan", {}, "must be a number"), (INF, {}, "must be a number"), ("", {}, "Rate is required."),
    (-1, {"minimum": 0}, "Rate cannot be negative."), (0, {"greater_than": 0}, "must be greater than 0"),
    (5e9, {"maximum": 1e6}, "cannot be more than"), (-5, {"minimum": 1}, "cannot be less than 1"),
])
def test_number_rejects_what_is_not_usable(value, kwargs, message):
    with pytest.raises(ValueError, match=message):
        V.number(value, "Rate", **kwargs)


def test_phone_email_gstin_username_ifsc_account():
    assert V.phone("9380645132 , 9382179443") == "9380645132 , 9382179443" and V.phone("") == ""
    for bad in ("abc", "12345", "1234567890123456", "1,2,3,4"):
        with pytest.raises(ValueError):
            V.phone(bad)
    assert V.email(" a@b.com ") == "a@b.com"
    with pytest.raises(ValueError):
        V.email("a@b")
    assert V.gstin("33abcde1234f1z5") == "33ABCDE1234F1Z5" and V.gstin("") == ""
    with pytest.raises(ValueError, match="15"):
        V.gstin("123")
    assert V.username("ravi.k") == "ravi.k"
    for bad in ("", "ab", "has space", "-lead", "x" * 31):
        with pytest.raises(ValueError):
            V.username(bad)
    assert V.ifsc("sbin0001234") == "SBIN0001234"
    with pytest.raises(ValueError, match="IFSC"):
        V.ifsc("SBIN1001234")
    assert V.account_number("1234 5678 90") == "1234567890"
    with pytest.raises(ValueError):
        V.account_number("12ab")
    assert V.choice("upi", "Mode", ("Cash", "UPI")) == "UPI"
    with pytest.raises(ValueError, match="one of"):
        V.choice("Barter", "Mode", ("Cash", "UPI"))


# ------------------------------------------------------------------ masters
@pytest.fixture
def db():
    d = MockMongoDatabase()
    d.collection("items").insert_one({"item_id": "I1", "item_alias": "TOM", "name": "Tomato", "unit": "kg", "stock": 10.0, "status": "active", "is_deleted": 0})
    d.collection("customers").insert_one({"cust_id": "C1", "name": "Metro", "current_balance": 0.0, "status": "active", "is_deleted": 0})
    d.collection("suppliers").insert_one({"supplier_id": "S1", "name": "Farm", "current_balance": 0.0, "status": "active", "is_deleted": 0})
    d.collection("roles").insert_one({"name": "user"})
    return d


def _item(**kw):
    return {"item_id": "ITEM_X", "item_alias": "X", "name": "Xigua", "unit": "kg", "standard_rate": 10, "stock": 0, **kw}


@pytest.mark.parametrize("patch,message", [
    ({"name": ""}, "Item name is required"), ({"name": "tomato"}, "already exists"), ({"standard_rate": -1}, "rate cannot be negative"),
    ({"standard_rate": "abc"}, "must be a number"), ({"stock": -5}, "Stock quantity cannot be negative"), ({"stock": NAN}, "must be a number"),
    ({"item_alias": "has space"}, "cannot contain spaces"), ({"name": "x" * 81}, "too long"),
])
def test_item_form_rules(db, patch, message):
    with pytest.raises(ValueError, match=message):
        MasterService(db).save_item(_item(**patch), is_new=True)


def test_item_edit_may_keep_its_own_name_and_a_negative_stock_from_overselling(db):
    svc = MasterService(db)
    svc.save_item(_item(), is_new=True)
    svc.save_item(_item(standard_rate=12, stock=-3), is_new=False)             # editing must not be blocked by what selling did
    with pytest.raises(ValueError, match="already exists"):
        svc.save_item(_item(name="Tomato"), is_new=False)                        # but renaming onto another item is


def _cust(**kw):
    return {"cust_id": "C9", "name": "Zed Stores", **kw}


@pytest.mark.parametrize("patch,message", [
    ({"name": ""}, "Customer name is required"), ({"name": "metro"}, "already exists"), ({"phone": "12ab"}, "Phone may only"),
    ({"phone": "12345"}, "7 to 15 digits"), ({"email": "nope"}, "Email is not valid"), ({"gst_number": "123"}, "GSTIN must be 15"),
    ({"credit_limit": -1}, "Credit limit cannot be negative"), ({"credit_limit": "lots"}, "Credit limit must be a number"),
    ({"bill_to_phone": "x"}, "Bill-to phone"), ({"current_balance": INF}, "Opening balance must be a number"),
])
def test_customer_form_rules(db, patch, message):
    with pytest.raises(ValueError, match=message):
        MasterService(db).save_customer(_cust(**patch), is_new=True)


def test_customer_values_are_cleaned_and_a_legacy_name_can_be_edited_without_a_clash_check(db):
    svc = MasterService(db)
    saved = svc.save_customer(_cust(gst_number="33abcde1234f1z5", phone="9380645132", name="  Zed   Stores "), is_new=True)
    assert saved["name"] == "Zed Stores" and saved["gst_number"] == "33ABCDE1234F1Z5"
    db.collection("customers").insert_one({"cust_id": "C10", "name": "Zed Stores", "status": "active", "is_deleted": 0})     # an older duplicate
    svc.save_customer({"cust_id": "C10", "name": "Zed Stores", "phone": "9380645132"}, is_new=False)                      # unchanged name: fine
    with pytest.raises(ValueError, match="already exists"):
        svc.save_customer({"cust_id": "C10", "name": "Metro"}, is_new=False)


@pytest.mark.parametrize("patch,message", [
    ({"name": ""}, "Supplier name is required"), ({"phone": "abc"}, "Phone may only"), ({"gst_number": "12"}, "GSTIN must be 15"),
    ({"tds_rate": 150}, "cannot be more than 100"), ({"tds_rate": -1}, "TDS rate cannot be negative"), ({"name": "farm"}, "already exists"),
])
def test_supplier_form_rules(db, patch, message):
    with pytest.raises(ValueError, match=message):
        MasterService(db).save_supplier({"supplier_id": "S9", "name": "New Farm", **patch}, is_new=True)


@pytest.mark.parametrize("args,message", [
    (("C1", "I1", NAN), "Fixed rate must be a number"), (("C1", "I1", 0), "greater than 0"), (("NOPE", "I1", 5), "not in the customer master"),
    (("C1", "NOPE", 5), "not in the item master"),
])
def test_fixed_price_rules(db, args, message):
    with pytest.raises(ValueError, match=message):
        MasterService(db).save_fixed_price(*args, NOW, NOW + timedelta(days=3))


def test_fixed_price_accepts_the_item_code_too(db):
    assert MasterService(db).save_fixed_price("C1", "TOM", 12.5, NOW, NOW + timedelta(days=3))


# ------------------------------------------------------------------ users and the drawer
@pytest.mark.parametrize("args,kw,message", [
    (("", "secret1", ["user"]), {}, "Username is required"), (("ab", "secret1", ["user"]), {}, "3 to 30 characters"),
    (("bob smith", "secret1", ["user"]), {}, "3 to 30 characters"), (("bobby", "secret1", []), {}, "Choose a role"),
    (("bobby1", "bobby1", ["user"]), {}, "cannot be the same as the username"), (("bobby", "secret1", ["user"]), {"email": "x"}, "Email is not valid"),
    (("bobby", "secret1", ["user"]), {"phone": "x"}, "Phone may only"), (("bobby", "", ["user"]), {}, "Password is required"),
])
def test_user_form_rules(db, args, kw, message):
    with pytest.raises(ValueError, match=message):
        AdminService(db).create_user(*args, **kw)


def test_usernames_clash_regardless_of_case(db):
    ads = AdminService(db)
    ads.create_user("Ravi", "secret1", ["user"])
    with pytest.raises(ValueError, match="already exists"):
        ads.create_user("RAVI", "secret1", ["user"])


def test_drawer_amounts_must_be_real_money(db):
    s = SessionService(db)
    for bad in (NAN, INF, -1, "abc", 5e9):
        with pytest.raises(ValueError):
            s.open_session("U1", "u", bad)
    assert s.open_session("U1", "u", "1,000")["opening_cash"] == 1000.0


# ------------------------------------------------------------------ stock
def test_a_nan_adjustment_no_longer_poisons_the_stock(db):
    inv = InventoryService(db)
    for bad in (NAN, INF, "x", 5e9):
        with pytest.raises(ValueError):
            inv.adjust_stock("I1", bad, "count")
    assert db.collection("items").find_one({"item_id": "I1"})["stock"] == 10.0
    assert inv.adjust_stock("TOM", 5, "found")["new_stock"] == 15.0                 # the item code works as well as the id


@pytest.mark.parametrize("qty,rate,message", [(NAN, 1, "Waste quantity must be a number"), (0, 1, "greater than 0"), (1, -1, "Waste rate cannot be negative"),
                                              (1, NAN, "Waste rate must be a number"), (999, 1, "exceeds stock")])
def test_waste_rules(db, qty, rate, message):
    with pytest.raises(ValueError, match=message):
        InventoryService(db).record_waste("I1", qty, rate, "rotten")


# ------------------------------------------------------------------ purchases and payments
def _line(**kw):
    return {"item_id": "I1", "name": "Tomato", "qty": 5, "rate": 10, "unit": "kg", **kw}


@pytest.mark.parametrize("bill_no,items,message", [
    ("", [_line()], "Vendor invoice number is required"), ("B1", [], "at least one item"), ("B1", [_line(qty=0)], "quantity must be greater than 0"),
    ("B1", [_line(qty=-2)], "quantity must be greater than 0"), ("B1", [_line(rate=-5)], "rate must be greater than 0"),
    ("B1", [_line(rate=NAN)], "rate must be a number"), ("B1", [_line(qty="x")], "quantity must be a number"),
    ("B1", [_line(item_id="ZZ")], "not in the item master"),
])
def test_vendor_bill_rules(db, bill_no, items, message):
    with pytest.raises(ValueError, match=message):
        ProcurementService(db).create_purchase_bill("S1", bill_no, items)


def test_the_same_vendor_invoice_cannot_be_entered_twice_and_a_code_is_resolved(db):
    svc = ProcurementService(db)
    bill = svc.create_purchase_bill("S1", "INV-77", [_line(item_id="TOM")])
    assert bill["items"][0]["item_id"] == "I1" and bill["total_amount"] == 50.0
    with pytest.raises(ValueError, match="already recorded as"):
        svc.create_purchase_bill("S1", "inv-77", [_line()])
    assert svc.create_purchase_bill("S1", "INV-78", [_line()])


@pytest.mark.parametrize("amount,method,message", [(NAN, "Cash", "must be a number"), (INF, "Cash", "must be a number"), (0, "Cash", "greater than 0"),
                                                   (5, "Barter", "one of"), ("x", "Cash", "must be a number")])
def test_customer_receipt_rules(db, amount, method, message):
    with pytest.raises(ValueError, match=message):
        PaymentService(db).record_customer_payment("C1", amount, method)


def test_payment_mode_is_normalised_and_supplier_payments_are_checked_the_same_way(db):
    p = PaymentService(db).record_customer_payment("C1", 5, "upi")
    assert p["payment_method"] == "UPI"
    bill = ProcurementService(db).create_purchase_bill("S1", "INV-1", [_line()])
    with pytest.raises(ValueError, match="one of"):
        PaymentService(db).record_supplier_payment(bill["purchase_id"], "S1", 5, "Barter")
    with pytest.raises(ValueError, match="exceeds"):
        PaymentService(db).record_supplier_payment(bill["purchase_id"], "S1", 9999, "NEFT")


@pytest.mark.parametrize("data,message", [
    ({"bank_name": "", "account_number": "123456"}, "Bank name is required"), ({"bank_name": "SBI", "account_number": ""}, "Account number is required"),
    ({"bank_name": "SBI", "account_number": "12ab"}, "6 to 20 digits"), ({"bank_name": "SBI", "account_number": "123456", "ifsc": "BAD"}, "IFSC must be"),
    ({"bank_name": "SBI", "account_number": "123456", "account_type": "Piggy"}, "one of"),
    ({"bank_name": "SBI", "account_number": "123456", "current_balance": NAN}, "must be a number"),
])
def test_bank_account_rules(db, data, message):
    with pytest.raises(ValueError, match=message):
        BankingService(db).save_bank_account(dict(data))


def test_a_bank_account_number_is_registered_once(db):
    svc = BankingService(db)
    svc.save_bank_account({"bank_name": "SBI", "account_number": "1234 5678", "ifsc": "sbin0001234", "current_balance": "1,000"})
    with pytest.raises(ValueError, match="already registered"):
        svc.save_bank_account({"bank_name": "SBI again", "account_number": "12345678"})


# ------------------------------------------------------------------ the forms show these as messages, not Python errors
@pytest.fixture
def shown(monkeypatch):
    log = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: log.append((_n, t, m)))
    return log


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def _dialog(view):
    return [w for w in view.winfo_children() if isinstance(w, tk.Toplevel)][-1]


def test_stock_adjustment_form_says_what_is_wrong(db, tk_root, shown):
    from app.ui.inventory_view import InventoryView
    v = InventoryView(tk_root, db, USER)
    try:
        v._adjustment_dialog()
        dlg = _dialog(v)
        entries = [w for w in _walk(dlg) if isinstance(w, ttk.Entry)]
        entries[0].insert(0, "I1")
        entries[1].insert(0, "ten")
        entries[2].insert(0, "count")
        [b for b in _walk(dlg) if isinstance(b, ttk.Button) and "Commit" in b.cget("text")][0].invoke()
        assert shown[-1][0] == "showerror" and shown[-1][2] == "Adjustment quantity must be a number."
        dlg.destroy()
    finally:
        v.destroy()


def test_bank_form_has_an_ifsc_box_account_type_list_and_reports_a_bad_ifsc(db, tk_root, shown):
    from app.ui.finance_view import FinanceView
    v = FinanceView(tk_root, db, USER)
    try:
        v._add_bank_dialog()
        dlg = _dialog(v)
        boxes = [w for w in _walk(dlg) if isinstance(w, (tk.Entry, ttk.Combobox))]
        assert any(isinstance(b, ttk.Combobox) and "Savings" in b.cget("values") for b in boxes)
        name, number, ifsc = boxes[0], boxes[1], boxes[2]
        name.insert(0, "SBI")
        number.insert(0, "123456789")
        ifsc.insert(0, "WRONG")
        [b for b in _walk(dlg) if isinstance(b, tk.Button) and b.cget("text") == "Save Bank"][0].invoke()
        assert "IFSC must be" in shown[-1][2]
        dlg.destroy()
    finally:
        v.destroy()


def test_receipt_form_offers_the_payment_modes_as_a_list(db, tk_root, shown):
    from app.ui.finance_view import FinanceView
    v = FinanceView(tk_root, db, USER)
    try:
        v._record_payment_dialog()
        dlg = _dialog(v)
        combos = [w for w in _walk(dlg) if isinstance(w, ttk.Combobox)]
        assert combos and "UPI" in combos[0].cget("values") and "Credit/Due" not in combos[0].cget("values")
        dlg.destroy()
    finally:
        v.destroy()


def test_journal_form_catches_an_unbalanced_entry_before_posting(db, tk_root, shown):
    from app.ui.finance_view import FinanceView
    v = FinanceView(tk_root, db, USER)
    try:
        v._post_journal_dialog()
        dlg = _dialog(v)
        e = [w for w in _walk(dlg) if isinstance(w, tk.Entry)]
        ref, dr_acc, dr_amt, cr_acc, cr_amt = e[0], e[1], e[2], e[3], e[4]
        ref.insert(0, "ADJ-1")
        dr_amt.insert(0, "100")
        cr_amt.insert(0, "90")
        [b for b in _walk(dlg) if isinstance(b, tk.Button) and b.cget("text") == "Post Entry"][0].invoke()
        assert "does not balance" in shown[-1][2]
        dr_acc.delete(0, tk.END)
        dr_acc.insert(0, "4000")
        cr_amt.delete(0, tk.END)
        cr_amt.insert(0, "100")
        [b for b in _walk(dlg) if isinstance(b, tk.Button) and b.cget("text") == "Post Entry"][0].invoke()
        assert "must be different" in shown[-1][2]
        dlg.destroy()
    finally:
        v.destroy()


def test_new_user_form_chooses_the_role_from_a_list_and_checks_the_username(db, tk_root, shown):
    from app.ui.admin_view import AdminView
    v = AdminView(tk_root, db, USER)
    try:
        v._add_user_dialog()
        dlg = _dialog(v)
        combo = [w for w in _walk(dlg) if isinstance(w, ttk.Combobox)][0]
        assert "user" in combo.cget("values") and str(combo.cget("state")) == "readonly"
        [w for w in _walk(dlg) if isinstance(w, ttk.Entry)][0].insert(0, "no")
        [b for b in _walk(dlg) if isinstance(b, ttk.Button) and b.cget("text") == "Create User"][0].invoke()
        assert "3 to 30 characters" in shown[-1][2]
        dlg.destroy()
    finally:
        v.destroy()


# ------------------------------------------------------------------ bills and orders: checked before anything is written
def _bill(db, **kw):
    from app.models.billing import BillCreate, BillLine
    qty, rate = kw.pop("qty", 2.0), kw.pop("rate", 10.0)
    base = dict(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="Metro", created_by="t",
                items=[BillLine(item_id="I1", name="Tomato", qty=qty, unit="kg", rate=rate, amount=qty * rate)], total_amount=qty * rate, balance_due=qty * rate)
    base.update(kw)
    return __import__("app.models.billing", fromlist=["BillCreate"]).BillCreate(**base)


@pytest.mark.parametrize("patch,message", [
    ({"qty": NAN}, "must be numbers"), ({"qty": 1e9}, "unreasonably large"), ({"crates_issued": -3}, "Crates issued cannot be negative"),
    ({"crates_returned": NAN}, "Crates returned must be a number"), ({"invoice_date": "2099-01-01"}, "cannot be in the future"),
    ({"invoice_date": "garbage"}, "not a valid date"), ({"commission_amt": -9}, "Commission cannot be negative"),
])
def test_bill_is_refused_before_anything_is_written(db, patch, message):
    from app.services.billing_service import BillingService
    with pytest.raises(ValueError, match=message):
        BillingService(db).create_bill(_bill(db, **patch))
    assert db.collection("bills").count_documents({}) == 0 and db.collection("journal_entries").count_documents({}) == 0


def _order(**kw):
    from app.models.order import OrderCreate, OrderItem
    qty, rate = kw.pop("qty", 2.0), kw.pop("rate", 10.0)
    return OrderCreate(customer_id=kw.pop("cust", "C1"), customer_name="Metro", company_id="Company0001", created_by="t",
                       items=[OrderItem(item_id="I1", name="Tomato", qty=qty, unit="kg", rate=rate, amount=qty * rate)], **kw)


@pytest.mark.parametrize("patch,message", [
    ({"qty": NAN}, "must be numbers"), ({"rate": -3}, "rate cannot be negative"), ({"crates_issued": -2}, "Crates out cannot be negative"),
    ({"cust": "NOPE"}, "customer master"), ({"qty": 1e9}, "unreasonably large"),
])
def test_order_rules(db, patch, message):
    from app.services.order_service import OrderService
    with pytest.raises(ValueError, match=message):
        OrderService(db).create_order(_order(**patch))
    assert OrderService(db).create_order(_order())["order_id"]


def test_the_order_form_no_longer_turns_unreadable_crate_counts_into_zero():
    from app.ui.order_form_view import OrderFormView
    assert OrderFormView._crate_count("", "Crates out") == 0 and OrderFormView._crate_count(" 7 ", "Crates out") == 7
    for bad, msg in (("abc", "must be a number"), ("-2", "cannot be negative"), ("2.5", "whole number")):
        with pytest.raises(ValueError, match=msg):
            OrderFormView._crate_count(bad, "Crates out")
