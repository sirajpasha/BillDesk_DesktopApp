"""Regression tests for D-01 / D-02: payment taken at the billing counter must be recorded,
and the selected company must be stored on the bill."""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import pytest

from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.ui.billing import BillingFrame


def _bill(customer_id="CUST001", name="Metro Retailers", total=200.0, **kw):
    line = BillLine(item_id="ITEM001", name="Tomato", qty=10.0, unit="kg", rate=total / 10.0, amount=total)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=customer_id, customer_name=name,
                      items=[line], total_amount=total, balance_due=total, created_by="tester", **kw)


def _cust(db):
    return db.collection("customers").find_one({"cust_id": "CUST001"})


def test_full_counter_payment_marks_bill_paid_and_leaves_customer_balance_unchanged(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(amount_received=200.0, payment_method="UPI", payment_reference="UTR1"))
    stored = fake_db.collection("bills").find_one({"invoice_no": saved["invoice_no"]})
    assert stored["status"] == "paid" and stored["balance_due"] == 0
    assert _cust(fake_db)["current_balance"] == 10000.0            # +200 bill, -200 receipt
    pay = fake_db.collection("payments").find_one({"party_id": "CUST001"})
    assert pay["amount"] == 200.0 and pay["payment_method"] == "UPI" and pay["reference_no"] == "UTR1"
    assert pay["allocations"] == [{"invoice_id": saved["invoice_no"], "amount": 200.0}]
    assert fake_db.collection("ledger_transactions").count_documents({"type": "credit"}) == 1


def test_partial_counter_payment_leaves_partial_status_and_balance(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(total=500.0, amount_received=200.0))
    stored = fake_db.collection("bills").find_one({"invoice_no": saved["invoice_no"]})
    assert (stored["status"], stored["balance_due"]) == ("partial", 300.0)
    assert _cust(fake_db)["current_balance"] == 10300.0


def test_no_payment_keeps_bill_unpaid(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(amount_received=0.0))
    stored = fake_db.collection("bills").find_one({"invoice_no": saved["invoice_no"]})
    assert (stored["status"], stored["balance_due"]) == ("unpaid", 200.0)
    assert fake_db.collection("payments").count_documents({}) == 0
    assert _cust(fake_db)["current_balance"] == 10200.0


def test_walk_in_cash_sale_records_receipt(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(customer_id="CASH", name="Cash Customer", amount_received=200.0))
    stored = fake_db.collection("bills").find_one({"invoice_no": saved["invoice_no"]})
    assert (stored["status"], stored["balance_due"]) == ("paid", 0.0)
    assert fake_db.collection("payments").find_one({"party_id": "CASH"})["amount"] == 200.0


@pytest.mark.parametrize("received", [-1.0, 200.01, 5000.0])
def test_invalid_amount_received_is_rejected_without_side_effects(fake_db, received):
    svc = BillingService(fake_db)
    with pytest.raises(ValueError):
        svc.create_bill(_bill(amount_received=received))
    assert fake_db.collection("bills").count_documents({}) == 0
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 100.0
    assert _cust(fake_db)["current_balance"] == 10000.0


def test_company_id_is_stored_on_bill(fake_db):
    svc = BillingService(fake_db)
    saved = svc.create_bill(_bill(company_id="Company0002"))
    assert fake_db.collection("bills").find_one({"invoice_no": saved["invoice_no"]})["company_id"] == "Company0002"


# ------------------------------------------------------------------ through the real payment modal
@pytest.fixture
def frame(fake_db, tk_root, monkeypatch):
    calls = []
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda t=None, m=None, _n=name, **k: calls.append((_n, t, m)))
    fake_db.collection("items").insert_one({"item_id": "VEG1", "item_alias": "101", "name": "Avarai", "unit": "Kg",
                                            "standard_rate": 20.0, "status": "active", "is_deleted": 0, "stock": 50.0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U1", username="admin", roles=["Admin"]))
    f.calls = calls
    yield f
    f.destroy()


def _modal(frame, received, method="Cash"):
    row = frame.row_widgets[0]
    row["code"].insert(0, "101"); frame._on_code_entered(0)
    row["qty"].delete(0, tk.END); row["qty"].insert(0, "10"); frame._recalculate_row(0)   # 10 x 20 = 200
    frame._open_payment_modal()
    modal = [w for w in frame.winfo_children() if isinstance(w, tk.Toplevel)][0]
    amt = [w for w in _walk(modal) if isinstance(w, tk.Entry)][0]
    amt.delete(0, tk.END); amt.insert(0, received)
    from tkinter import ttk
    [w for w in _walk(modal) if isinstance(w, ttk.Combobox)][0].set(method)
    [w for w in _walk(modal) if isinstance(w, tk.Button) and w.cget("text") == "Post Payment"][0].invoke()
    return modal


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def test_modal_full_payment_is_recorded(frame, fake_db):
    _modal(frame, "200")
    bill = fake_db.collection("bills").find_one({})
    assert bill["status"] == "paid" and bill["balance_due"] == 0
    assert fake_db.collection("payments").count_documents({}) == 1


def test_modal_non_numeric_amount_is_rejected_and_nothing_saved(frame, fake_db):
    _modal(frame, "abc")
    assert fake_db.collection("bills").count_documents({}) == 0
    assert frame.calls[-1][0] == "showerror" and frame.calls[-1][1] == "Invalid Amount"


def test_modal_over_payment_is_rejected(frame, fake_db):
    _modal(frame, "5000")
    assert fake_db.collection("bills").count_documents({}) == 0
    assert frame.calls[-1][1] == "Invalid Amount"


def test_modal_credit_due_method_records_no_payment(frame, fake_db):
    _modal(frame, "200", method="Credit/Due")
    bill = fake_db.collection("bills").find_one({})
    assert bill["status"] == "unpaid" and fake_db.collection("payments").count_documents({}) == 0
