"""Regression tests for D-09 .. D-16: input handling, arithmetic integrity and workflow controls."""
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk

import pytest

from app.config.settings import settings
from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.repositories.accounting_repo import AccountingRepository
from app.services.admin_service import AdminService
from app.services.billing_service import BillingService
from app.services.inventory_service import InventoryService
from app.services.master_service import MasterService
from app.services.procurement_service import ProcurementService
from app.services.session_service import SessionService
from app.ui.billing import BillingFrame
from app.ui.order_form_view import OrderFormView


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


# ================================================================== D-11 arithmetic
def _bill(db, qty=10.0, rate=20.0, total=None, **kw):
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=qty * rate)
    t = qty * rate if total is None else total
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="CASH", customer_name="Cash",
                      items=[line], total_amount=t, balance_due=t, created_by="t", **kw)


def test_total_must_match_lines(fake_db):
    with pytest.raises(ValueError, match="does not match"):
        BillingService(fake_db).create_bill(_bill(fake_db, total=1.0))
    assert fake_db.collection("bills").count_documents({}) == 0


def test_line_amounts_are_recomputed_and_rounded_half_up(fake_db):
    saved = BillingService(fake_db).create_bill(_bill(fake_db, qty=12.5, rate=33.33))      # 416.625
    assert saved["items"][0]["amount"] == 416.63 and saved["total_amount"] == 416.63


def test_fees_are_part_of_the_total(fake_db):
    saved = BillingService(fake_db).create_bill(_bill(fake_db, total=210.0, commission_amt=5.0, mandi_fee_amt=5.0))
    assert saved["total_amount"] == 210.0
    with pytest.raises(ValueError, match="does not match"):
        BillingService(fake_db).create_bill(_bill(fake_db, total=200.0, commission_amt=5.0))


def test_selling_beyond_stock_is_flagged_but_allowed_by_default(fake_db):
    saved = BillingService(fake_db).create_bill(_bill(fake_db, qty=150.0, rate=1.0))
    assert saved["stock_warnings"][0]["available"] == 100.0 and saved["stock_warnings"][0]["required"] == 150.0


def test_selling_beyond_stock_can_be_blocked_by_setting(fake_db, monkeypatch):
    monkeypatch.setattr(settings, "allow_negative_stock", False)
    with pytest.raises(ValueError, match="Insufficient stock"):
        BillingService(fake_db).create_bill(_bill(fake_db, qty=150.0, rate=1.0))
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 100.0


# ================================================================== D-15 validations
def test_inventory_validations(fake_db):
    inv = InventoryService(fake_db)
    with pytest.raises(ValueError, match="reason"):
        inv.adjust_stock("ITEM001", 5.0, "  ")
    with pytest.raises(ValueError, match="rate cannot be negative"):
        inv.record_waste("ITEM001", 1.0, -5.0, "spoiled")
    with pytest.raises(ValueError, match="exceeds stock"):
        inv.record_waste("ITEM001", 1000.0, 5.0, "typo")
    assert inv.record_waste("ITEM001", 10.0, 5.0, "rotten")["amount"] == 50.0
    fake_db.collection("items").update_one({"item_id": "ITEM001"}, {"$set": {"stock": 0.0}})   # untracked stock
    assert inv.record_waste("ITEM001", 4.0, 5.0, "rotten")["amount"] == 20.0


def test_master_data_validations(fake_db):
    ms = MasterService(fake_db)
    with pytest.raises(ValueError, match="rate cannot be negative"):
        ms.save_item({"item_id": "N1", "name": "Neg", "standard_rate": -5}, is_new=True)
    with pytest.raises(ValueError, match="Credit limit"):
        ms.save_customer({"cust_id": "C9", "name": "x", "credit_limit": -1}, is_new=True)
    # editing a customer must not overwrite ledger-owned fields
    ms.save_customer({"cust_id": "CUST001", "name": "Metro Retailers", "current_balance": 0.0, "crate_balances": []})
    assert fake_db.collection("customers").find_one({"cust_id": "CUST001"})["current_balance"] == 10000.0
    with pytest.raises(ValueError, match="outstanding balance"):
        ms.delete_customer("CUST001")
    fake_db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 0.0}})
    assert ms.delete_customer("CUST001") is True


def test_user_creation_validations(fake_db):
    fake_db.collection("roles").insert_one({"name": "user"})
    ads = AdminService(fake_db)
    with pytest.raises(ValueError, match="at least 6"):
        ads.create_user("a", "1", ["user"])
    with pytest.raises(ValueError, match="Unknown role"):
        ads.create_user("b", "secret1", ["nonexistent"])
    with pytest.raises(ValueError, match="too long"):
        ads.create_user("c", "x" * 73, ["user"])
    assert ads.create_user("d", "secret1", ["user"])["username"] == "d"


@pytest.mark.parametrize("lines,msg", [
    ([], "at least two"),
    ([{"account_id": "1", "debit": -5.0, "credit": 0.0}, {"account_id": "2", "debit": 0.0, "credit": -5.0}], "negative"),
    ([{"account_id": "1", "debit": 5.0, "credit": 5.0}, {"account_id": "2", "debit": 0.0, "credit": 0.0}], "both"),
    ([{"account_id": "1", "debit": 0.0, "credit": 0.0}, {"account_id": "2", "debit": 0.0, "credit": 0.0}], "must have"),
])
def test_journal_line_validation(fake_db, lines, msg):
    with pytest.raises(ValueError, match=msg):
        AccountingRepository(fake_db).record_journal("R", "manual", lines)
    assert fake_db.collection("journal_entries").count_documents({}) == 0


# ================================================================== D-13 procurement
def _po(db, qty=100.0, rate=40.0):
    return ProcurementService(db).create_purchase_order("SUP001", [{"item_id": "ITEM001", "name": "Tomato", "qty": qty, "rate": rate}])


def test_grn_partial_then_complete_and_over_receipt_blocked(fake_db):
    ps = ProcurementService(fake_db)
    po = _po(fake_db)
    ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 60.0}])
    assert fake_db.collection("purchase_orders").find_one({"po_id": po["po_id"]})["status"] == "partially_received"
    with pytest.raises(ValueError, match="exceed the ordered"):
        ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 50.0}])
    ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 40.0}])
    assert fake_db.collection("purchase_orders").find_one({"po_id": po["po_id"]})["status"] == "received"
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 200.0
    with pytest.raises(ValueError, match="already received"):
        ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 1.0}])
    assert fake_db.collection("items").find_one({"item_id": "ITEM001"})["stock"] == 200.0


def test_grn_rejects_items_not_on_po_and_empty_receipts(fake_db):
    ps = ProcurementService(fake_db)
    po = _po(fake_db)
    with pytest.raises(ValueError, match="not on Purchase Order"):
        ps.record_grn(po["po_id"], [{"item_id": "OTHER", "name": "x", "qty": 1.0}])
    with pytest.raises(ValueError, match="Nothing received"):
        ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 0.0}])


def test_three_way_match_flags_quantity_and_rate_differences(fake_db):
    ps = ProcurementService(fake_db)
    po = _po(fake_db)
    grn = ps.record_grn(po["po_id"], [{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0}])
    ok = ps.create_purchase_bill("SUP001", "B1", [{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0, "rate": 40.0}], po["po_id"], grn["grn_id"])
    assert ok["match_status"] == "matched" and ok["match_issues"] == []
    bad = ps.create_purchase_bill("SUP001", "B2", [{"item_id": "ITEM001", "name": "Tomato", "qty": 1000.0, "rate": 55.0}], po["po_id"], grn["grn_id"])
    assert bad["match_status"] == "mismatch" and len(bad["match_issues"]) == 2
    assert ps.create_purchase_bill("SUP001", "B3", [{"item_id": "ITEM001", "name": "Tomato", "qty": 1.0, "rate": 1.0}])["match_status"] == "direct"


# ================================================================== D-14 cash drawer
def test_expected_cash_excludes_credit_sales_and_non_cash_receipts(fake_db):
    ss = SessionService(fake_db)
    with pytest.raises(ValueError, match="negative"):
        ss.open_session("U", "cashier", -1.0)
    s = ss.open_session("U", "cashier", 2000.0)
    now = datetime.now(timezone.utc)
    for pid, amt, method in (("P1", 3500.0, "Cash"), ("P2", 500.0, "Cash"), ("P3", 900.0, "UPI")):
        fake_db.collection("payments").insert_one({"payment_id": pid, "created_by": "cashier", "created_at": now, "amount": amt, "payment_method": method, "is_deleted": 0})
    fake_db.collection("bills").insert_one({"invoice_no": "X", "created_by": "cashier", "created_at": now, "total_amount": 1000.0, "status": "unpaid", "is_deleted": 0})
    assert ss.compute_expected_cash(s["session_id"]) == 6000.0


def test_cash_taken_through_billing_counts_in_the_drawer(fake_db):
    ss = SessionService(fake_db)
    s = ss.open_session("U", "t", 1000.0)
    BillingService(fake_db).create_bill(_bill(fake_db, qty=10.0, rate=35.0, amount_received=350.0))
    assert ss.compute_expected_cash(s["session_id"]) == 1350.0


# ================================================================== D-10 / D-16 / D-09 UI
@pytest.fixture
def billing_ui(fake_db, tk_root, monkeypatch):
    dialogs = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    fake_db.collection("items").insert_one({"item_id": "VEG1", "item_alias": "101", "name": "Avarai", "unit": "Kg", "standard_rate": 20.0, "status": "active", "is_deleted": 0, "stock": 50.0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    f.dialogs = dialogs
    yield f
    f.destroy()


def test_unknown_code_does_not_fill_a_random_item(billing_ui):
    row = billing_ui.row_widgets[3]
    row["code"].insert(0, "ZZZ999")
    billing_ui._on_code_entered(3)
    assert row["name"].get() == "" and row["code"].get() == "" and row.get("item_id") is None
    assert billing_ui.dialogs[-1][1] == "Item Not Found"


def test_negative_quantity_never_counts_and_blocks_the_save(billing_ui, fake_db):
    f = billing_ui
    for i, (code, qty) in enumerate([("101", "10"), ("101", "-5")]):
        f.suppress_duplicate_dialog = True
        r = f.row_widgets[i]
        r["code"].insert(0, code); f._on_code_entered(i)
        r["qty"].delete(0, tk.END); r["qty"].insert(0, qty); f._recalculate_row(i)
    assert f.row_widgets[1]["amount"].cget("text") == "₹0.00"
    assert f._update_grand_total() == 200.0
    f._open_payment_modal()
    modal = [w for w in f.winfo_children() if isinstance(w, tk.Toplevel)][0]
    [w for w in _walk(modal) if isinstance(w, tk.Button) and w.cget("text") == "Post Payment"][0].invoke()
    assert fake_db.collection("bills").count_documents({}) == 0
    assert f.dialogs[-1][1] == "Fix These Lines" and "Row 2" in f.dialogs[-1][2] and "greater than zero" in f.dialogs[-1][2]


@pytest.fixture
def order_ui(fake_db, tk_root, monkeypatch):
    dialogs = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    for n, (alias, name, unit) in enumerate([("101", "Apple", "Kg"), ("102", "Avarai", "Kg"), ("103", "Banana Leaves (NUNI)", "Nos")], 1):
        fake_db.collection("items").insert_one({"item_id": f"I{n}", "item_alias": alias, "name": name, "unit": unit, "standard_rate": 20.0, "status": "active", "is_deleted": 0})
    v = OrderFormView(tk_root, fake_db, CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    v.dialogs = dialogs
    yield v
    v.destroy()


@pytest.mark.parametrize("line,item,qty,unit", [
    ("101 5kg", "Apple", "5", "Kg"), ("102 50kg", "Avarai", "50", "Kg"), ("102 50", "Avarai", "50", "Kg"),
    ("Apple 25kg", "Apple", "25", "Kg"), ("avarai 4", "Avarai", "4", "Kg"), ("Apple x", "Apple", "1", "Kg"),
    ("3 kg Apple", "Apple", "3", "Kg"), ("banana leaves 2 nos", "Banana Leaves (NUNI)", "2", "Nos"),
])
def test_importer_matches_codes_and_names(order_ui, line, item, qty, unit):
    assert order_ui._parse_and_populate_lines(line) == 1
    r = order_ui.row_widgets[0]
    assert (r["item_var"].get(), r["qty_var"].get(), r["unit"].get()) == (item, qty, unit)


def test_importer_skips_unmatched_lines_instead_of_guessing_and_merges_repeats(order_ui):
    n = order_ui._parse_and_populate_lines("Mango 2 boxes\n5 kg\n101 5kg\napple 3\n999 4kg")
    assert n == 2                                     # Apple (merged 5 + 3), nothing else
    assert order_ui.import_skipped == ["Mango 2 boxes", "5 kg", "999 4kg"]
    r0 = order_ui.row_widgets[0]
    assert (r0["item_var"].get(), r0["qty_var"].get()) == ("Apple", "8")
    assert order_ui.row_widgets[1]["item_var"].get() == ""


def test_order_requires_a_customer_from_the_master(order_ui, fake_db):
    v = order_ui
    fake_db.collection("customers").docs.clear()
    fake_db.collection("customers").insert_one({"cust_id": "C1", "name": "Real Customer", "status": "active", "is_deleted": 0})
    v._parse_and_populate_lines("101 1kg")
    v.customer_var.set("Some Typed Walk-in")
    v._open_customer_search = lambda: None            # avoid opening the modal in the test
    v._save_order()
    assert fake_db.collection("orders").count_documents({}) == 0
    assert v.dialogs[-1][1] == "Unknown Customer"
    v.customer_var.set("real customer")                # exact (case-insensitive) master name is accepted
    v._save_order()
    assert fake_db.collection("orders").find_one({})["customer_id"] == "C1"


def test_leaving_the_code_field_keeps_a_rate_typed_by_the_cashier(billing_ui):
    f = billing_ui
    row = f.row_widgets[0]
    row["code"].insert(0, "101"); f._on_code_entered(0)
    row["rate"].delete(0, tk.END); row["rate"].insert(0, "50"); f._recalculate_row(0)
    row["qty"].delete(0, tk.END); row["qty"].insert(0, "7"); f._recalculate_row(0)
    f._on_code_entered(0, focus_next=False)            # what the <FocusOut> binding does
    f._on_code_entered(0)                              # ...and pressing Enter in the code box again
    assert row["rate"].get() == "50" and row["qty"].get() == "7"
    assert row["amount"].cget("text") == "₹350.00"
    row["code"].delete(0, tk.END); row["code"].insert(0, "Avarai"); f._on_code_entered(0)    # a *changed* code does re-resolve
    assert row["rate"].get() == "20.00"
