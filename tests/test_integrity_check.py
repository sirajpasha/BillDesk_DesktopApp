"""Integrity checks: healthy books pass; every kind of corruption is caught; the screen shows it."""
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import pytest

from app.models.billing import BillCreate, BillLine
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.inventory_service import InventoryService
from app.services.integrity_service import IntegrityService
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.procurement_service import ProcurementService
from app.ui.integrity_view import IntegrityView


def _bill(customer="CUST001", qty=10.0, rate=20.0, **kw):
    amt = round(qty * rate, 2)
    line = BillLine(item_id="ITEM001", name="Tomato", qty=qty, unit="kg", rate=rate, amount=amt)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=customer, customer_name="x",
                      items=[line], total_amount=amt, balance_due=amt, created_by="t", **kw)


@pytest.fixture
def books(fake_db):
    """A realistic month of activity through the real services."""
    bs, pay = BillingService(fake_db), PaymentService(fake_db)
    # the fixture customer starts with an opening balance of 10,000 that was never journaled -> zero it for a clean slate
    fake_db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 0.0}})
    ProcurementService(fake_db).create_purchase_bill("SUP001", "B1", [{"item_id": "ITEM001", "name": "Tomato", "qty": 100.0, "rate": 15.0}])
    a = bs.create_bill(_bill(qty=10, rate=30))
    bs.create_bill(_bill(qty=4, rate=30, amount_received=50.0))
    bs.create_bill(_bill(customer="CASH", qty=2, rate=30, amount_received=60.0))
    pay.record_customer_payment("CUST001", 100.0, invoice_no=a["invoice_no"])
    c = bs.create_bill(_bill(qty=1, rate=30))
    bs.void_bill(c["invoice_no"])
    InventoryService(fake_db).record_waste("ITEM001", 2.0, 15.0, "rotten")
    return fake_db


def _by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_healthy_books_have_no_failures_or_warnings(books):
    rep = IntegrityService(books).run_all()
    bad = [(c["id"], c["status"], c["summary"], c["details"][:3]) for c in rep["checks"] if c["status"] in ("warn", "fail")]
    assert bad == []
    assert rep["summary"]["fail"] == 0 and rep["summary"]["ok"] >= 10


def test_an_empty_database_is_reported_as_notes_not_errors(fake_db):
    for name in ("customers", "items", "suppliers"):
        fake_db.collection(name).docs.clear()
    rep = IntegrityService(fake_db).run_all()
    assert rep["summary"]["fail"] == 0 and rep["summary"]["warn"] == 0


def test_tampered_bill_total_is_a_failure(books):
    books.collection("bills").update_one({"invoice_no": books.collection("bills").docs[0]["invoice_no"]}, {"$set": {"total_amount": 1.0}})
    c = _by_id(IntegrityService(books).run_all())["bill_arithmetic"]
    assert c["status"] == "fail" and "lines + charges" in c["details"][0]


def test_status_and_balance_disagreement_is_a_failure(books):
    books.collection("bills").update_one({"status": "paid"}, {"$set": {"balance_due": 5.0}})
    books.collection("bills").update_one({"status": "void"}, {"$set": {"balance_due": 7.0}})
    c = _by_id(IntegrityService(books).run_all())["bill_status"]
    assert c["status"] == "fail" and c["count"] == 2


def test_duplicate_invoice_numbers_are_a_failure(books):
    books.collection("bills").insert_one(dict(books.collection("bills").docs[0], _id="dup"))
    c = _by_id(IntegrityService(books).run_all())["invoice_numbers"]
    assert c["status"] == "fail" and "2 times" in c["details"][0]


def test_gaps_in_the_invoice_sequence_are_noticed(books):
    books.collection("bills").delete_one({"invoice_no": books.collection("bills").docs[1]["invoice_no"]})
    c = _by_id(IntegrityService(books).run_all())["invoice_numbers"]
    assert any(d.startswith("gap ") for d in c["details"])


def test_overallocated_payment_and_missing_invoice_are_failures(books):
    p = books.collection("payments").docs[0]
    books.collection("payments").update_one({"payment_id": p["payment_id"]}, {"$set": {"allocations": [{"invoice_id": "NOPE", "amount": 9999.0}]}})
    c = _by_id(IntegrityService(books).run_all())["payments"]
    assert c["status"] == "fail" and any("missing invoice NOPE" in d for d in c["details"]) and any("allocated" in d for d in c["details"])


def test_an_unbalanced_journal_is_a_failure(books):
    books.collection("journal_entries").insert_one({"entry_id": "BAD", "reference": "X", "source_type": "manual", "state": "posted", "date": datetime.now(),
                                                    "lines": [{"account_id": "1000", "debit": 100.0, "credit": 0.0}, {"account_id": "4000", "debit": 0.0, "credit": 90.0}]})
    rep = _by_id(IntegrityService(books).run_all())
    assert rep["ledger_balanced"]["status"] == "fail" and "BAD" in rep["ledger_balanced"]["details"][0]
    assert rep["balance_sheet"]["status"] == "fail"


def test_transactions_missing_from_the_ledger_are_flagged_for_backfill(books):
    books.collection("journal_entries").docs[:] = [j for j in books.collection("journal_entries").docs if j["source_type"] != "sale"]
    c = _by_id(IntegrityService(books).run_all())["ledger_coverage"]
    assert c["status"] == "warn" and "backfill_ledger.py" in c["summary"] and any("has no sale entry" in d for d in c["details"])


def test_customer_balance_drift_is_flagged_and_ledger_difference_explained(books):
    books.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 12345.0}})
    rep = _by_id(IntegrityService(books).run_all())
    assert rep["customer_balances"]["status"] == "warn" and "CUST001" in rep["customer_balances"]["details"][0]
    assert rep["ar_vs_customers"]["status"] == "warn" and "difference" in rep["ar_vs_customers"]["summary"]


def test_void_without_reversal_is_a_failure(books):
    books.collection("journal_entries").docs[:] = [j for j in books.collection("journal_entries").docs if j["source_type"] != "sale_reversal"]
    c = _by_id(IntegrityService(books).run_all())["void_reversals"]
    assert c["status"] == "fail" and "never reversed" in c["details"][0]


def test_dangling_references_negative_stock_and_supplier_drift_are_warnings(books):
    books.collection("bills").update_one({"customer_id": "CUST001"}, {"$set": {"customer_id": "GHOST"}})
    books.collection("orders").insert_one({"order_id": "ORD-1", "status": "billed", "linked_bill_ids": [], "is_deleted": 0})
    books.collection("items").update_one({"item_id": "ITEM001"}, {"$set": {"stock": -4.0}})
    books.collection("suppliers").update_one({"supplier_id": "SUP001"}, {"$set": {"current_balance": 1.0}})
    rep = _by_id(IntegrityService(books).run_all())
    assert rep["references"]["status"] == "warn" and any("GHOST" in d for d in rep["references"]["details"]) and any("ORD-1" in d for d in rep["references"]["details"])
    assert rep["stock"]["status"] == "warn" and "ITEM001" in rep["stock"]["details"][0]
    assert rep["supplier_balances"]["status"] == "warn"


def test_a_crashing_check_is_reported_without_hiding_the_others(books, monkeypatch):
    monkeypatch.setattr(IntegrityService, "check_stock", lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = IntegrityService(books).run_all()
    crashed = _by_id(rep)["check_stock"]
    assert crashed["status"] == "fail" and "boom" in crashed["summary"] and len(rep["checks"]) == len(IntegrityService.CHECKS)


def test_checks_never_write(books):
    def snapshot():          # (the in-memory mock creates empty collections lazily on read; ignore those)
        return {n: [dict(d) for d in c.docs] for n, c in books._collections.items() if c.docs}
    before = snapshot()
    IntegrityService(books).run_all()
    assert snapshot() == before


def test_report_text_lists_status_and_findings(books):
    books.collection("bills").update_one({"status": "paid"}, {"$set": {"balance_due": 5.0}})
    text = IntegrityService.format_report(IntegrityService(books).run_all())
    assert "[FAIL] Bill status agrees with its balance due" in text and "paid but balance due 5.00" in text


# ------------------------------------------------------------------ the screen
def test_integrity_screen_runs_shows_rows_details_and_saves_the_report(books, tk_root, tmp_path, monkeypatch):
    books.collection("bills").update_one({"status": "paid"}, {"$set": {"balance_due": 5.0}})
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda t=None, m=None, **k: shown.append(m))
    out = tmp_path / "r.txt"
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: str(out))
    v = IntegrityView(tk_root, books, current_user=CurrentUser(user_id="U", username="a", roles=["Admin"]))
    try:
        v.run()
        ids = v.tree.get_children()
        assert len(ids) == len(IntegrityService.CHECKS)
        assert v.tree.item("bill_status", "values")[0] == "FAIL" and "1 failures" in v.summary_lbl.cget("text")
        v.tree.selection_set("bill_status")
        v.update()
        assert "paid but balance due 5.00" in v.details.get("1.0", "end")
        v.save_report()
        assert "[FAIL] Bill status" in out.read_text(encoding="utf-8") and shown
    finally:
        v.destroy()


def test_integrity_page_is_in_the_accounts_menu_and_needs_finance_access(fake_db, tk_root, monkeypatch):
    from app.services.auth_service import AuthService
    from app.ui.main_window import MainWindow
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    auth = AuthService(fake_db)
    admin = CurrentUser(user_id="A", username="admin", roles=["Admin"])
    win = MainWindow(tk_root, fake_db, auth, BillingService(fake_db), admin)
    assert ("Integrity Check", "Integrity Check", "") in win.menus_config["Accounts"]
    win.show_page("Integrity Check")
    assert win.active_page == "Integrity Check"
    clerk = CurrentUser(user_id="U", username="u", roles=["user"])
    win2 = MainWindow(tk_root, fake_db, auth, BillingService(fake_db), clerk)
    win2.show_page("Integrity Check")
    assert win2.active_page != "Integrity Check"


def test_window_icon_is_a_real_png_that_tk_can_load(tk_root):
    """icon.png used to be a JPEG with a .png name: Tk silently refused it and the app never got its window icon."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "app" / "assets" / "icon.png"
    assert p.read_bytes()[:4] == b"\x89PNG"
    tk.PhotoImage(master=tk_root, file=str(p))             # raises TclError if the format is not recognised
