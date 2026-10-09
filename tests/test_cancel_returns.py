"""Cancelling a return (credit note / debit note) made by mistake puts everything back."""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import pytest

from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.integrity_service import IntegrityService
from app.services.ledger_service import LedgerService
from app.services.procurement_service import ProcurementService
from app.services.purchase_returns_service import PurchaseReturnsService
from app.services.report_service import ReportService
from app.services.returns_service import ReturnsService
from tests.conftest import MockMongoDatabase

USER = CurrentUser(user_id="U", username="admin", roles=["Admin"])


@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    return shown


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


# ------------------------------------------------------------------ sales returns
def _prepare(db):
    db.collection("items").update_one({"item_id": "ITEM001"}, {"$set": {"stock": 100.0, "avg_cost": 15.0, "cost_qty": 100.0}})
    db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 0.0}})


def _sell(db, customer="CUST001", qty=10.0, rate=20.0, received=0.0):
    amount = round(qty * rate, 2)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=amount)
    bill = BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=customer, customer_name="Metro", items=[line],
                      total_amount=amount, balance_due=amount, created_by="t",
                      **({"amount_received": received, "payment_method": "Cash"} if received else {}))
    return BillingService(db).create_bill(bill)["invoice_no"]


def _bal(db, code):
    t = LedgerService(db).get_account_balances().get(code, {"debit": 0.0, "credit": 0.0})
    return round(t["debit"] - t["credit"], 2)


def _item(db):
    return db.collection("items").find_one({"item_id": "ITEM001"})


def _snapshot(db, inv, cid="CUST001"):
    b = db.collection("bills").find_one({"invoice_no": inv})
    c = db.collection("customers").find_one({"cust_id": cid}) or {}
    return {"cust": round(c.get("current_balance", 0.0), 2), "due": b.get("balance_due"), "status": b.get("status"), "stock": _item(db)["stock"],
            "cost_qty": _item(db).get("cost_qty"), "ar": _bal(db, "1200"), "sales": _bal(db, "4000"), "cogs": _bal(db, "5050"),
            "inv": _bal(db, "1300"), "cash": _bal(db, "1000")}


def test_cancelling_a_return_puts_everything_back(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    before = _snapshot(fake_db, inv)
    svc = ReturnsService(fake_db)
    ret = svc.create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    assert _snapshot(fake_db, inv) != before
    done = svc.cancel_return(ret["return_id"], user_id="t", reason="keyed by mistake")
    assert done["status"] == "cancelled" and done["cancelled_by"] == "t"
    assert _snapshot(fake_db, inv) == before                                     # balance, invoice, stock, cost, every ledger account
    assert LedgerService(fake_db).get_trial_balance()["is_balanced"]
    assert [l["returnable"] for l in svc.returnable_lines(inv)] == [10.0]        # the whole quantity can be returned again
    assert svc.returns_for_invoice(inv) == []
    assert ReportService(fake_db).customer_sales()["rows"][0]["returned"] == 0.0
    assert IntegrityService(fake_db).check_customer_balances()["status"] in ("ok", "info")


def test_a_cancelled_return_can_be_redone_and_the_invoice_voided_afterwards(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    svc = ReturnsService(fake_db)
    first = svc.create_return(inv, [{"item_id": "ITEM001", "qty": 10}])
    svc.cancel_return(first["return_id"])
    with pytest.raises(ValueError, match="already cancelled"):
        svc.cancel_return(first["return_id"])
    BillingService(fake_db).void_bill(inv)                                       # nothing is returned against it any more
    assert fake_db.collection("bills").find_one({"invoice_no": inv})["status"] == "void"


def test_cancelling_on_a_paid_invoice_a_cash_refund_and_a_spoiled_line(fake_db):
    _prepare(fake_db)
    paid = _sell(fake_db, received=200.0)
    before = _snapshot(fake_db, paid)
    r1 = ReturnsService(fake_db).create_return(paid, [{"item_id": "ITEM001", "qty": 5}])           # the credit stays on the account
    ReturnsService(fake_db).cancel_return(r1["return_id"])
    assert _snapshot(fake_db, paid) == before

    walk = _sell(fake_db, customer="CASH", received=200.0)
    snap = {k: v for k, v in _snapshot(fake_db, walk, "CASH").items() if k != "cust"}
    r2 = ReturnsService(fake_db).create_return(walk, [{"item_id": "ITEM001", "qty": 2}], refund_method="Cash")
    ReturnsService(fake_db).cancel_return(r2["return_id"])
    assert {k: v for k, v in _snapshot(fake_db, walk, "CASH").items() if k != "cust"} == snap

    spoiled = _sell(fake_db)
    stock0 = _item(fake_db)["stock"]
    r3 = ReturnsService(fake_db).create_return(spoiled, [{"item_id": "ITEM001", "qty": 3, "is_waste": True}])
    ReturnsService(fake_db).cancel_return(r3["return_id"])
    assert _item(fake_db)["stock"] == stock0                                     # spoiled goods were never restocked, so nothing comes off


def test_older_returns_and_unknown_ids_cannot_be_cancelled(fake_db):
    fake_db.collection("sales_returns").insert_one({"return_id": "RET-OLD", "original_invoice_no": "X", "customer_id": "CUST001",
                                                    "total_refund_amount": 60.0, "status": "completed", "items": []})
    with pytest.raises(ValueError, match="older BillDesk"):
        ReturnsService(fake_db).cancel_return("RET-OLD")
    with pytest.raises(ValueError, match="not found"):
        ReturnsService(fake_db).cancel_return("NOPE")


def test_bill_history_can_cancel_a_return_from_the_credit_notes_list(fake_db, tk_root, quiet):
    from app.ui.history import BillHistoryFrame
    _prepare(fake_db)
    inv = _sell(fake_db)
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    f = BillHistoryFrame(tk_root, fake_db, BillingService(fake_db), current_user=USER)
    try:
        f.refresh()
        f.tree.selection_set(inv)
        f._credit_notes_selected()
        dlg = f.credit_notes_dialog
        [b for b in _walk(dlg) if isinstance(b, tk.Button) and b.cget("text") == "Cancel this return"][0].invoke()
        assert quiet[-1][0] == "showinfo" and "cancelled" in quiet[-1][2]
        assert fake_db.collection("sales_returns").find_one({})["status"] == "cancelled"
        assert fake_db.collection("bills").find_one({"invoice_no": inv})["balance_due"] == 200.0
    finally:
        f.destroy()


# ------------------------------------------------------------------ purchase returns
@pytest.fixture
def db():
    d = MockMongoDatabase()
    d.collection("suppliers").insert_one({"supplier_id": "S1", "name": "Farm Co", "current_balance": 0.0, "status": "active", "is_deleted": 0,
                                          "tds_applicable": True, "tds_rate": 10.0, "tds_section": "194C"})
    d.collection("items").insert_one({"item_id": "I1", "item_alias": "I1", "name": "Tomato", "unit": "kg", "stock": 100.0, "avg_cost": 0.0,
                                      "cost_qty": 0.0, "status": "active", "is_deleted": 0})
    return d


_NO = iter(range(1, 1000))


def _buy(db, grn=None):
    items = [{"item_id": "I1", "name": "Tomato", "qty": 100.0, "unit": "kg", "rate": 10.0, "amount": 1000.0}]
    return ProcurementService(db).create_purchase_bill("S1", f"CB-{next(_NO)}", items, grn_id=grn, user_id="t")["purchase_id"]


def _supplier(db):
    return db.collection("suppliers").find_one({"supplier_id": "S1"})["current_balance"]


def test_cancelling_a_purchase_return_puts_everything_back(db):
    pid = _buy(db, grn="GRN-1")

    def snap():
        b = db.collection("purchase_bills").find_one({"purchase_id": pid})
        return (_supplier(db), b["balance_due"], b["status"], db.collection("items").find_one({"item_id": "I1"})["stock"],
                [_bal(db, c) for c in ("2100", "2200", "1300")])
    before = snap()
    svc = PurchaseReturnsService(db)
    ret = svc.create_return(pid, [{"item_id": "I1", "qty": 20}])
    assert snap() != before
    done = svc.cancel_return(ret["return_id"], user_id="t", reason="wrong bill")
    assert done["status"] == "cancelled" and snap() == before
    assert LedgerService(db).get_trial_balance()["is_balanced"]
    assert svc.returnable_lines(pid)[0]["returnable"] == 100.0
    with pytest.raises(ValueError, match="already cancelled"):
        svc.cancel_return(ret["return_id"])
    assert ReportService(db).daybook()["totals"]["bought"] == 900.0                # the daybook counts the bill only
    assert IntegrityService(db).check_supplier_balances()["status"] == "ok"


def test_cancelling_a_purchase_return_on_a_paid_bill_removes_the_credit(db):
    pid = _buy(db)
    db.collection("purchase_bills").update_one({"purchase_id": pid}, {"$set": {"balance_due": 0.0, "status": "paid"}})
    db.collection("suppliers").update_one({"supplier_id": "S1"}, {"$set": {"current_balance": 0.0}})
    ret = PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
    assert _supplier(db) == -90.0
    PurchaseReturnsService(db).cancel_return(ret["return_id"])
    assert _supplier(db) == 0.0 and db.collection("purchase_bills").find_one({"purchase_id": pid})["status"] == "paid"


def test_procurement_screen_cancels_a_debit_note(db, tk_root, quiet):
    from app.ui.procurement_view import ProcurementView
    pid = _buy(db)
    PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
    v = ProcurementView(tk_root, db, USER)
    try:
        v.returns_table.tree.selection_set(v.returns_table.tree.get_children()[0])
        v._cancel_selected_return()
        assert quiet[-1][0] == "showinfo" and db.collection("purchase_returns").find_one({})["status"] == "cancelled"
        assert "cancelled" in [v.returns_table.tree.item(i)["values"][-1] for i in v.returns_table.tree.get_children()]
    finally:
        v.destroy()


def _bal_db(db, code):
    return _bal(db, code)
