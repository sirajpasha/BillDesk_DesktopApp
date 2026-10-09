"""Tier 3: sales returns (credit notes) and the daybook / item-wise / customer-wise reports."""
from datetime import datetime, timedelta
from tkinter import messagebox

import pytest

from app.models.billing import BillCreate, BillLine
from app.services.billing_service import BillingService
from app.services.integrity_service import IntegrityService
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.report_service import ReportService
from app.services.returns_service import ReturnsService
from app.ui.reports_view import ReportsFrame, REPORTS
from app.ui.return_dialog import ReturnDialog


def _prepare(db):
    db.collection("items").update_one({"item_id": "ITEM001"}, {"$set": {"stock": 100.0, "avg_cost": 15.0, "cost_qty": 100.0}})
    db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 0.0}})      # the seed carries an opening balance


def _sell(db, customer="CUST001", qty=10.0, rate=20.0, received=0.0):
    amount = round(qty * rate, 2)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=amount)
    bill = BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=customer, customer_name="Metro",
                      items=[line], total_amount=amount, balance_due=amount, created_by="t",
                      **({"amount_received": received, "payment_method": "Cash"} if received else {}))
    return BillingService(db).create_bill(bill)["invoice_no"]


def _bal(db, code):
    t = LedgerService(db).get_account_balances().get(code, {"debit": 0.0, "credit": 0.0})
    return round(t["debit"] - t["credit"], 2)


def _item(db):
    return db.collection("items").find_one({"item_id": "ITEM001"})


def _cust_balance(db, cid="CUST001"):
    return db.collection("customers").find_one({"cust_id": cid}).get("current_balance", 0.0)


# ------------------------------------------------------------------ returns
def test_partial_return_credits_the_invoice_restocks_and_posts_a_balanced_entry(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    before_bal, stock0 = _cust_balance(fake_db), _item(fake_db)["stock"]
    ret = ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 4}], reason="too ripe", user_id="t")
    assert ret["total_refund_amount"] == 80.0 and ret["applied_to_bill"] == 80.0 and ret["credit_amount"] == 0.0
    bill = fake_db.collection("bills").find_one({"invoice_no": inv})
    assert bill["balance_due"] == 120.0 and bill["status"] == "partial"
    assert round(_cust_balance(fake_db) - before_bal, 2) == -80.0
    assert _item(fake_db)["stock"] == stock0 + 4 and _item(fake_db)["cost_qty"] == 100.0 - 10.0 + 4
    assert _bal(fake_db, "4000") == -120.0 and _bal(fake_db, "1200") == 120.0          # sale 200 less return 80
    assert _bal(fake_db, "5050") == 90.0 and _bal(fake_db, "1300") >= -90.0              # cost 150 less 60 put back
    assert LedgerService(fake_db).get_trial_balance()["is_balanced"]


def test_cannot_return_more_than_was_billed_in_total(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    svc = ReturnsService(fake_db)
    svc.create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    with pytest.raises(ValueError, match="only 6"):
        svc.create_return(inv, [{"item_id": "ITEM001", "qty": 7}])
    with pytest.raises(ValueError, match="not on invoice"):
        svc.create_return(inv, [{"item_id": "NOPE", "qty": 1}])
    with pytest.raises(ValueError, match="at least one"):
        svc.create_return(inv, [{"item_id": "ITEM001", "qty": 0}])
    assert [l["returnable"] for l in svc.returnable_lines(inv)] == [6.0]


def test_return_on_a_paid_invoice_leaves_credit_on_the_account_and_integrity_agrees(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db, received=200.0)                       # counter payment settles it
    ret = ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 5}])
    assert ret["applied_to_bill"] == 0.0 and ret["credit_amount"] == 100.0
    assert round(_cust_balance(fake_db), 2) == -100.0
    check = IntegrityService(fake_db).check_customer_balances()
    assert check["status"] in ("ok", "info"), check


def test_spoiled_goods_are_credited_but_not_put_back_on_the_shelf(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    stock0, cogs0 = _item(fake_db)["stock"], _bal(fake_db, "5050")
    ret = ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 3, "is_waste": True}])
    assert ret["restock_cost"] == 0.0 and _item(fake_db)["stock"] == stock0 and _bal(fake_db, "5050") == cogs0
    assert _bal(fake_db, "4000") == -140.0                       # still credited: 200 - 60


def test_walk_in_return_is_refunded_from_the_cash_drawer(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db, customer="CASH", received=200.0)
    cash0 = _bal(fake_db, "1000")
    ret = ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 2}], refund_method="Cash")
    assert ret["refund_method"] == "Cash" and _bal(fake_db, "1000") == cash0 - 40.0
    assert LedgerService(fake_db).get_trial_balance()["is_balanced"]


def test_an_invoice_with_returns_cannot_be_voided_and_a_void_invoice_cannot_be_returned(fake_db):
    _prepare(fake_db)
    inv, other = _sell(fake_db), _sell(fake_db)
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 1}])
    with pytest.raises(ValueError, match="returned"):
        BillingService(fake_db).void_bill(inv)
    BillingService(fake_db).void_bill(other)
    with pytest.raises(ValueError, match="void"):
        ReturnsService(fake_db).create_return(other, [{"item_id": "ITEM001", "qty": 1}])


def test_statement_shows_the_return_and_still_ends_on_the_balance(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    st = PaymentService(fake_db).customer_statement("CUST001")
    assert "Return" in [r["type"] for r in st["rows"]]
    assert st["closing"] == round(_cust_balance(fake_db), 2)


# ------------------------------------------------------------------ reports
def test_item_and_customer_reports_are_net_of_returns(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    _sell(fake_db, qty=5.0)
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    svc = ReportService(fake_db)
    item = svc.item_sales()["rows"][0]
    assert (item["qty"], item["returned_qty"], item["net_qty"], item["net_amount"], item["bills"]) == (15.0, 4.0, 11.0, 220.0, 2)
    assert item["avg_rate"] == 20.0
    cust = svc.customer_sales()["rows"][0]
    assert (cust["bills"], cust["billed"], cust["returned"], cust["net"]) == (2, 300.0, 80.0, 220.0)


def test_reports_respect_the_date_range(fake_db):
    _prepare(fake_db)
    _sell(fake_db)
    old = _sell(fake_db, qty=1.0)
    fake_db.collection("bills").update_one({"invoice_no": old}, {"$set": {"invoice_date": datetime.now() - timedelta(days=40)}})
    svc = ReportService(fake_db)
    assert svc.customer_sales(datetime.now() - timedelta(days=5), datetime.now())["rows"][0]["bills"] == 1
    assert svc.customer_sales()["rows"][0]["bills"] == 2


def test_daybook_lists_money_events_and_totals(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db, received=50.0)
    PaymentService(fake_db).record_customer_payment("CUST001", 30.0, "Cash", user_id="t")
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 1}])
    res = ReportService(fake_db).daybook()
    types = [r["type"] for r in res["rows"]]
    assert types[0] == "Sale" and "Return" in types and types.count("Receipt") >= 1
    t = res["totals"]
    assert t["billed"] == 200.0 - 20.0 and t["money_in"] >= 30.0 and t["money_out"] == 0.0     # a credit customer's return is not cash out
    assert t["net_money"] == round(t["money_in"] - t["money_out"], 2)


# ------------------------------------------------------------------ screens
@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    return shown


def test_reports_screen_shows_each_report(fake_db, tk_root, quiet):
    _prepare(fake_db)
    inv = _sell(fake_db)
    ReturnsService(fake_db).create_return(inv, [{"item_id": "ITEM001", "qty": 4}])
    f = ReportsFrame(tk_root, fake_db)
    try:
        for name in REPORTS:
            f.show_report(name)
            assert f.tree.get_children(), name
            assert f.summary.cget("text")
        f.show_report("Item-wise Sales")
        assert f.tree.item(f.tree.get_children()[0])["values"][0] == "Tomato"
        f.from_var.set("not a date")
        f.refresh()
        assert quiet and quiet[-1][0] == "showwarning"
    finally:
        f.destroy()


def test_return_dialog_saves_a_return_and_shows_the_credit(fake_db, tk_root, quiet):
    _prepare(fake_db)
    inv = _sell(fake_db)
    dlg = ReturnDialog(tk_root, fake_db, inv, "Metro", walk_in=False, user="t")
    try:
        row = dlg.rows[0]
        row["qty"].set("2.5")
        dlg.update()
        assert "50.00" in dlg.total_lbl.cget("text") and "50.00" in row["credit"].cget("text")
        dlg.reason.insert(0, "damaged")
        dlg.save()
        assert dlg.result and dlg.result["total_refund_amount"] == 50.0 and dlg.result["notes"] == "damaged"
        assert quiet[-1][0] == "showinfo"
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_return_dialog_reports_a_bad_quantity_without_closing(fake_db, tk_root, quiet):
    _prepare(fake_db)
    inv = _sell(fake_db)
    dlg = ReturnDialog(tk_root, fake_db, inv, "Metro", walk_in=False)
    try:
        dlg.rows[0]["qty"].set("99")
        dlg.save()
        assert dlg.result is None and quiet[-1][0] == "showerror" and "only 10" in quiet[-1][2] and dlg.winfo_exists()
    finally:
        dlg.destroy()


def test_item_report_labels_a_code_by_its_usual_name(fake_db):
    """Older bills reuse a code under other typed names; the row carries the name most bills use."""
    _prepare(fake_db)
    for n in range(3):
        _sell(fake_db, qty=1.0)
    odd = _sell(fake_db, qty=1.0)
    bill = fake_db.collection("bills").find_one({"invoice_no": odd})
    fake_db.collection("bills").update_one({"invoice_no": odd}, {"$set": {"items": [{**bill["items"][0], "name": "Typo Name"}]}})
    rows = ReportService(fake_db).item_sales()["rows"]
    assert len(rows) == 1 and rows[0]["name"] == "Tomato" and rows[0]["bills"] == 4


def test_return_on_an_older_bill_that_stores_the_item_code_restocks_the_right_item(fake_db):
    _prepare(fake_db)
    inv = _sell(fake_db)
    bill = fake_db.collection("bills").find_one({"invoice_no": inv})
    fake_db.collection("bills").update_one({"invoice_no": inv}, {"$set": {"items": [{**bill["items"][0], "item_id": "TOM"}]}})     # TOM is Tomato's alias
    stock0 = _item(fake_db)["stock"]
    ReturnsService(fake_db).create_return(inv, [{"item_id": "TOM", "qty": 2}])
    assert _item(fake_db)["stock"] == stock0 + 2


def test_older_returns_and_bills_use_different_item_keys_but_count_as_the_same_item(fake_db):
    """The older web app stored the item code on bills and the item id on returns; both must land on one item."""
    _prepare(fake_db)
    inv = _sell(fake_db)
    bill = fake_db.collection("bills").find_one({"invoice_no": inv})
    fake_db.collection("bills").update_one({"invoice_no": inv}, {"$set": {"items": [{**bill["items"][0], "item_id": "TOM"}]}})     # code
    fake_db.collection("sales_returns").insert_one({"return_id": "RET-OLD", "return_date": datetime.now(), "original_invoice_no": " " + inv,
        "customer_id": "CUST001", "customer_name": "Metro", "total_refund_amount": 60.0, "status": "completed",
        "items": [{"item_id": "ITEM001", "name": "Tomato", "qty": 3.0, "unit": "kg", "rate": 20.0, "amount": 60.0}]})                  # id, no is_deleted
    line = ReturnsService(fake_db).returnable_lines(inv)[0]
    assert (line["returned"], line["returnable"]) == (3.0, 7.0)
    rows = ReportService(fake_db).item_sales()["rows"]
    assert len(rows) == 1 and rows[0]["returned_qty"] == 3.0 and rows[0]["net_qty"] == 7.0
    with pytest.raises(ValueError, match="returned"):
        BillingService(fake_db).void_bill(inv)
