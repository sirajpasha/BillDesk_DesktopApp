"""UX audit, tier 1: one receivables truth, customer statement, order totals, paid/unpaid view, safe item and customer pickers."""
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import messagebox

import pytest

from app.models.common import CurrentUser
from tests.conftest import MockMongoDatabase
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.ui.billing import BillingFrame
from app.ui.history import BillHistoryFrame
from app.utils.currency import format_balance

NOW = datetime.now(timezone.utc)


@pytest.fixture
def db():
    return MockMongoDatabase()          # empty: the seeded fake_db already has customers and balances


def _cust(db, cid, name, balance):
    db.collection("customers").insert_one({"cust_id": cid, "name": name, "current_balance": balance, "status": "active", "is_deleted": 0})


def _bill(db, inv, cid, total, days_ago, status="unpaid"):
    when = NOW - timedelta(days=days_ago)
    db.collection("bills").insert_one({"invoice_no": inv, "customer_id": cid, "total_amount": total, "balance_due": total,
                                       "status": status, "is_deleted": 0, "invoice_date": when, "created_at": when})


# ------------------------------------------------------------------ receivables: one source of truth
def test_receivables_equal_the_sum_of_customer_balances_and_advances_are_separate(db):
    _cust(db, "C1", "Raja", 1000.0)
    _cust(db, "C2", "Metro", 500.0)
    _cust(db, "C3", "Ahava", -300.0)                  # we hold an advance: not a receivable
    _cust(db, "C4", "Zero", 0.0)
    res = PaymentService(db).get_ar_aging()
    assert res["summary"]["total"] == 1500.0 and res["summary"]["advances"] == 300.0
    assert {r["customer_name"] for r in res["customers"]} == {"Raja", "Metro"}
    assert sum(r["total"] for r in res["customers"]) == res["summary"]["total"]


def test_ageing_uses_newest_invoices_first_and_unexplained_balance_is_oldest(db):
    _cust(db, "C1", "Raja", 700.0)
    _bill(db, "I-NEW", "C1", 300.0, days_ago=5)       # newest 300 is 1-30 days
    _bill(db, "I-OLD", "C1", 200.0, days_ago=45)      # next 200 is 31-60 days
    _bill(db, "I-VOID", "C1", 9999.0, days_ago=1, status="void")      # ignored
    row = PaymentService(db).get_ar_aging()["customers"][0]
    assert (row["1_30"], row["31_60"], row["90_plus"], row["total"]) == (300.0, 200.0, 200.0, 700.0)


def test_a_customer_balance_smaller_than_the_bills_only_ages_what_is_owed(db):
    _cust(db, "C1", "Raja", 100.0)
    _bill(db, "I1", "C1", 400.0, days_ago=2)
    row = PaymentService(db).get_ar_aging()["customers"][0]
    assert row["1_30"] == 100.0 and row["total"] == 100.0


# ------------------------------------------------------------------ customer statement
def _payment(db, cid, amount, days_ago, pid):
    when = NOW - timedelta(days=days_ago)
    db.collection("payments").insert_one({"payment_id": pid, "party_id": cid, "party_type": "customer", "amount": amount,
                                          "payment_date": when, "payment_method": "Cash", "is_deleted": 0})


def test_statement_ends_on_the_customer_balance_with_a_brought_forward_line(db):
    _cust(db, "C1", "Raja", 1000.0)                    # 600 billed - 100 received = 500, so 500 predates the bills
    _bill(db, "I1", "C1", 400.0, 20)
    _bill(db, "I2", "C1", 200.0, 10)
    _payment(db, "C1", 100.0, 5, "PAY1")
    st = PaymentService(db).customer_statement("C1")
    assert st["opening"] == 500.0 and st["closing"] == 1000.0
    assert [(r["type"], r["ref"], r["balance"]) for r in st["rows"]] == [("Invoice", "I1", 900.0), ("Invoice", "I2", 1100.0), ("Receipt", "PAY1", 1000.0)]
    assert (st["total_debit"], st["total_credit"]) == (600.0, 100.0)


def test_statement_date_range_rolls_earlier_activity_into_the_opening_balance(db):
    _cust(db, "C1", "Raja", 600.0)
    _bill(db, "I1", "C1", 400.0, 20)
    _bill(db, "I2", "C1", 200.0, 3)
    st = PaymentService(db).customer_statement("C1", date_from=datetime.now() - timedelta(days=10))
    assert st["opening"] == 400.0 and [r["ref"] for r in st["rows"]] == ["I2"] and st["closing"] == 600.0


def test_receipts_the_system_never_recorded_show_as_one_adjustment_not_a_huge_advance(db):
    _cust(db, "C1", "Raja", 150.0)                          # bills total 400 but only 150 is owed: 250 was paid outside the system
    _bill(db, "I1", "C1", 400.0, 20)
    st = PaymentService(db).customer_statement("C1")
    assert st["opening"] == 0.0 and st["closing"] == 150.0
    assert [(r["type"], r["credit"]) for r in st["rows"]] == [("Invoice", 0.0), ("Adjustment", 250.0)]


def test_statement_skips_voided_bills_and_rejects_an_unknown_customer(db):
    _cust(db, "C1", "Raja", 100.0)
    _bill(db, "I1", "C1", 100.0, 3)
    _bill(db, "IV", "C1", 777.0, 2, status="void")
    st = PaymentService(db).customer_statement("C1")
    assert [r["ref"] for r in st["rows"]] == ["I1"] and st["closing"] == 100.0
    with pytest.raises(ValueError):
        PaymentService(db).customer_statement("NOPE")


def test_balance_wording():
    assert format_balance(1500) == "₹ 1,500.00 Dr" and format_balance(-250) == "₹ 250.00 Cr" and format_balance(0) == "₹ 0.00"


# ------------------------------------------------------------------ order totals are not capped by the list size
def test_order_stats_count_every_order_not_only_the_loaded_page(db):
    col = db.collection("orders")
    for n in range(250):
        col.insert_one({"order_id": f"O{n}", "status": "pending" if n < 40 else "billed", "is_deleted": 0, "order_date": datetime.now() - timedelta(days=n + 1)})
    col.insert_one({"order_id": "OT", "status": "pending", "is_deleted": 0, "order_date": datetime.now()})
    stats = OrderService(db).order_stats()
    assert stats == {"total": 251, "pending": 41, "today": 1}


# ------------------------------------------------------------------ bill status wording
def test_legacy_bills_are_labelled_legacy_not_active():
    assert [BillHistoryFrame.display_status(s) for s in ("paid", "UNPAID", "partial", "void", "active", None)] == \
           ["paid", "unpaid", "partial", "void", "legacy", "unpaid"]


# ------------------------------------------------------------------ billing screen
@pytest.fixture
def billing(fake_db, tk_root, monkeypatch):
    dialogs = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    items = fake_db.collection("items")
    for iid, alias, name in (("B1", "201", "Banana Raw"), ("B2", "202", "Banana Leaves (E)"), ("B3", "203", "Banana Flower"),
                             ("O1", "301", "Onion Big")):
        items.insert_one({"item_id": iid, "item_alias": alias, "name": name, "unit": "Kg", "standard_rate": 10.0, "status": "active", "is_deleted": 0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    f.dialogs = dialogs
    yield f
    f.destroy()


def _type_code(f, text):
    r = f.row_widgets[0]
    r["code"].delete(0, tk.END)
    r["code"].insert(0, text)
    f._on_code_entered(0)
    return r


def test_an_ambiguous_name_offers_a_choice_and_never_picks_the_first_match(billing, monkeypatch):
    offered = []

    def choose(code, candidates):
        offered.append([c["name"] for c in candidates])
        return candidates[1]
    monkeypatch.setattr(billing, "_choose_item", choose)
    r = _type_code(billing, "ban")
    assert offered == [["Banana Flower", "Banana Leaves (E)", "Banana Raw"]]            # alphabetical, all three offered
    assert r["name"].get() == "Banana Leaves (E)" and r["item_id"] == "B2"


def test_cancelling_the_choice_leaves_the_line_empty(billing, monkeypatch):
    monkeypatch.setattr(billing, "_choose_item", lambda code, cands: None)
    r = _type_code(billing, "ban")
    assert r["name"].get() == "" and not r.get("item_id") and billing.dialogs == []


def test_exact_code_and_single_match_need_no_choice(billing, monkeypatch):
    monkeypatch.setattr(billing, "_choose_item", lambda *a: pytest.fail("no choice expected"))
    assert _type_code(billing, "202")["name"].get() == "Banana Leaves (E)"            # exact alias wins over the name search
    billing._clear_row(0)
    assert _type_code(billing, "onion")["name"].get() == "Onion Big"                  # only one match


def test_item_list_is_driven_by_the_keyboard(billing, tk_root):
    chosen = {}
    items = list(billing.db.collection("items").find({"name": {"$regex": "^Banana"}}))
    items.sort(key=lambda i: i["name"])

    def run():
        dlg = [w for w in billing.winfo_children() if isinstance(w, tk.Toplevel)][0]
        lb = [w for w in dlg.winfo_children() if isinstance(w, tk.Listbox)][0]
        lb.selection_clear(0, tk.END)
        lb.selection_set(2)                                          # arrow down twice, in effect
        assert lb.bind("<Return>") and dlg.bind("<Escape>")           # the keys are wired (a withdrawn test root cannot receive real key events)
        dlg.choose_selected()
    billing.after(150, run)
    chosen["item"] = billing._choose_item("ban", items)
    assert chosen["item"]["name"] == "Banana Raw"


def test_customer_picker_works_without_the_mouse(billing, fake_db):
    for n, name in enumerate(("Alpha Stores", "Beta Traders")):
        fake_db.collection("customers").insert_one({"cust_id": f"K{n}", "name": name, "phone": "9", "status": "active", "is_deleted": 0})
    billing._open_customer_search()
    modal = [w for w in billing.winfo_children() if isinstance(w, tk.Toplevel)][0]
    modal.update()
    ent = [w for w in _walk(modal) if isinstance(w, tk.Entry)][0]
    assert ent.bind("<Down>") and ent.bind("<Up>") and ent.bind("<Return>") and modal.bind("<Escape>")
    ent.insert(0, "Traders")
    modal.refresh_list()                                               # typing filters the list down to one customer
    modal.pick_highlighted()                                           # Enter picks the highlighted one
    billing.update()
    assert billing.selected_customer and billing.selected_customer["name"] == "Beta Traders"
    assert not modal.winfo_exists()

    billing.selected_customer = None
    billing._open_customer_search()                                    # unfiltered: Cash first, Down moves to a real customer
    modal = [w for w in billing.winfo_children() if isinstance(w, tk.Toplevel)][0]
    modal.update()
    ent = [w for w in _walk(modal) if isinstance(w, tk.Entry)][0]
    modal.move_highlight(1)
    modal.pick_highlighted()
    billing.update()
    assert billing.selected_customer is not None


def test_payment_dialog_takes_focus_and_escape_closes_it(billing):
    r = _type_code(billing, "201")
    billing._update_grand_total()
    billing._open_payment_modal()
    billing.update()
    modal = [w for w in billing.winfo_children() if isinstance(w, tk.Toplevel)][0]
    assert modal.bind("<Escape>") and modal.amount_entry.bind("<Return>")
    modal.destroy()


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)
