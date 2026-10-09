"""Tier 4: purchase returns (debit notes), printable credit / debit notes, theme and empty states."""
import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import pytest

from app.services.integrity_service import IntegrityService
from app.services.ledger_service import LedgerService
from app.services.procurement_service import ProcurementService
from app.services.purchase_returns_service import PurchaseReturnsService
from app.services.report_service import ReportService
from app.printing.notes import generate_credit_note_pdf, generate_debit_note_pdf
from tests.conftest import MockMongoDatabase


@pytest.fixture
def db():
    d = MockMongoDatabase()
    d.collection("suppliers").insert_one({"supplier_id": "S1", "name": "Farm Co", "current_balance": 0.0, "status": "active", "is_deleted": 0,
                                          "tds_applicable": True, "tds_rate": 10.0, "tds_section": "194C"})
    d.collection("items").insert_one({"item_id": "I1", "item_alias": "I1", "name": "Tomato", "unit": "kg", "stock": 100.0, "avg_cost": 0.0,
                                      "cost_qty": 0.0, "status": "active", "is_deleted": 0})
    return d


def _buy(db, qty=100.0, rate=10.0, grn=None):
    items = [{"item_id": "I1", "name": "Tomato", "qty": qty, "unit": "kg", "rate": rate, "amount": qty * rate}]
    bill = ProcurementService(db).create_purchase_bill("S1", "VB-1", items, grn_id=grn, user_id="t")
    return bill["purchase_id"]


def _bal(db, code):
    t = LedgerService(db).get_account_balances().get(code, {"debit": 0.0, "credit": 0.0})
    return round(t["debit"] - t["credit"], 2)


def _supplier(db):
    return db.collection("suppliers").find_one({"supplier_id": "S1"})["current_balance"]


# ------------------------------------------------------------------ purchase returns
def test_return_reduces_the_payable_by_the_net_amount_and_tds_comes_back_proportionally(db):
    pid = _buy(db)                                        # 1000 gross, 100 TDS, 900 payable
    assert _supplier(db) == 900.0
    ret = PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 20}], reason="rotten", user_id="t")
    assert (ret["gross_amount"], ret["tds_amount"], ret["net_amount"]) == (200.0, 20.0, 180.0)
    assert ret["applied_to_bill"] == 180.0 and ret["credit_amount"] == 0.0
    bill = db.collection("purchase_bills").find_one({"purchase_id": pid})
    assert bill["balance_due"] == 720.0 and bill["status"] == "partial"
    assert _supplier(db) == 720.0
    assert _bal(db, "2100") == -720.0 and _bal(db, "2200") == -80.0 and _bal(db, "1300") == 800.0     # payables, TDS payable, inventory
    assert LedgerService(db).get_trial_balance()["is_balanced"]


def test_a_paid_bill_leaves_a_credit_with_the_supplier_and_integrity_agrees(db):
    pid = _buy(db)
    db.collection("purchase_bills").update_one({"purchase_id": pid}, {"$set": {"balance_due": 0.0, "status": "paid"}})
    db.collection("suppliers").update_one({"supplier_id": "S1"}, {"$set": {"current_balance": 0.0}})      # as if fully paid
    ret = PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
    assert ret["applied_to_bill"] == 0.0 and ret["credit_amount"] == 90.0 and _supplier(db) == -90.0
    assert IntegrityService(db).check_supplier_balances()["status"] == "ok"


def test_stock_comes_off_only_when_the_goods_were_received_into_stock(db):
    direct = _buy(db)
    PurchaseReturnsService(db).create_return(direct, [{"item_id": "I1", "qty": 5}])
    assert db.collection("items").find_one({"item_id": "I1"})["stock"] == 100.0           # direct bill: stock was never added
    received = _buy(db, grn="GRN-X")
    PurchaseReturnsService(db).create_return(received, [{"item_id": "I1", "qty": 5}])
    assert db.collection("items").find_one({"item_id": "I1"})["stock"] == 95.0


def test_cannot_return_more_than_bought(db):
    pid = _buy(db)
    svc = PurchaseReturnsService(db)
    svc.create_return(pid, [{"item_id": "I1", "qty": 60}])
    with pytest.raises(ValueError, match="only 40"):
        svc.create_return(pid, [{"item_id": "I1", "qty": 41}])
    with pytest.raises(ValueError, match="not on purchase bill"):
        svc.create_return(pid, [{"item_id": "ZZ", "qty": 1}])
    with pytest.raises(ValueError, match="at least one"):
        svc.create_return(pid, [])


def test_daybook_shows_the_purchase_return(db):
    pid = _buy(db)
    PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
    res = ReportService(db).daybook()
    assert [r["type"] for r in res["rows"]] == ["Purchase", "Purchase return"]
    assert res["totals"]["bought"] == 900.0 - 90.0


# ------------------------------------------------------------------ PDFs
def test_credit_note_pdf_is_a_real_pdf_for_credit_and_walk_in_returns(tmp_path):
    ret = {"return_id": "RET-1", "return_date": datetime.now(), "original_invoice_no": "20260101-0001", "customer_id": "C1",
           "customer_name": "Metro", "items": [{"item_id": "I", "name": "Tomato", "qty": 2, "unit": "kg", "rate": 20.0, "amount": 40.0, "is_waste": True}],
           "total_refund_amount": 40.0, "applied_to_bill": 25.0, "credit_amount": 15.0, "notes": "ripe"}
    p1 = generate_credit_note_pdf(str(tmp_path / "a.pdf"), ret, {"name": "SV"}, {"name": "Metro", "address": "Chennai"})
    p2 = generate_credit_note_pdf(str(tmp_path / "b.pdf"), {**ret, "customer_id": "CASH", "refund_method": "UPI"}, {"name": "SV"}, {})
    for p in (p1, p2):
        assert open(p, "rb").read(5) == b"%PDF-" and os.path.getsize(p) > 1500
    import fitz
    text = fitz.open(p1)[0].get_text()
    assert "CREDIT NOTE" in text and "RET-1" in text and "20260101-0001" in text and "Spoiled" in text and "held as credit" in text
    assert "Refunded by UPI" in fitz.open(p2)[0].get_text()


def test_debit_note_pdf_shows_tds_and_net(tmp_path):
    ret = {"return_id": "PRET-1", "return_date": datetime.now(), "purchase_id": "PUR-1", "supplier_bill_no": "VB-9", "supplier_name": "Farm Co",
           "items": [{"item_id": "I", "name": "Tomato", "qty": 20, "unit": "kg", "rate": 10.0, "amount": 200.0}],
           "gross_amount": 200.0, "tds_amount": 20.0, "net_amount": 180.0, "applied_to_bill": 180.0, "credit_amount": 0.0, "notes": ""}
    p = generate_debit_note_pdf(str(tmp_path / "d.pdf"), ret, {"name": "SV"}, {"name": "Farm Co"})
    import fitz
    text = fitz.open(p)[0].get_text()
    assert "DEBIT NOTE" in text and "PRET-1" in text and "TDS" in text and "180.00" in text and "VB-9" in text


# ------------------------------------------------------------------ screens
@pytest.fixture
def quiet(monkeypatch):
    shown = []
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: shown.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    return shown


def test_purchase_return_dialog_saves_and_does_not_open_the_pdf_when_declined(db, tk_root, quiet):
    from app.ui.return_dialog import PurchaseReturnDialog
    pid = _buy(db)
    dlg = PurchaseReturnDialog(tk_root, db, pid, "Farm Co", walk_in=False, user="t")
    try:
        dlg.rows[0]["qty"].set("10")
        dlg.update()
        assert "Debit note total" in dlg.total_lbl.cget("text") and "100.00" in dlg.total_lbl.cget("text")
        dlg.save()
        assert dlg.result["net_amount"] == 90.0 and quiet[-1][0] == "showinfo"
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_open_note_pdf_makes_the_file_and_previews_it(db, tk_root, monkeypatch, tmp_path, quiet):
    from app.ui import return_dialog
    from app import paths
    shown = []
    monkeypatch.setattr(paths, "output_dir", lambda: tmp_path)
    monkeypatch.setattr("app.ui.print_preview.show_print_preview", lambda parent, path, title="", default_filename="": shown.append((path, title)))
    pid = _buy(db)
    ret = PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
    path = return_dialog.open_note_pdf(tk_root, db, "purchase", ret)
    assert path and os.path.exists(path) and shown and "Debit Note" in shown[0][1]


def test_procurement_screen_has_the_returns_tab_and_empty_hints(db, tk_root, quiet):
    from app.models.common import CurrentUser
    from app.ui.procurement_view import ProcurementView
    v = ProcurementView(tk_root, db, CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    try:
        assert "Returns to Suppliers" in [v.notebook.tab(t, "text") for t in v.notebook.tabs()]
        v.update()
        assert v.po_table.empty_lbl.winfo_manager() == "place" and "No purchase orders" in v.po_table.empty_lbl.cget("text")
        pid = _buy(db)
        PurchaseReturnsService(db).create_return(pid, [{"item_id": "I1", "qty": 10}])
        v.refresh()
        assert len(v.returns_table.tree.get_children()) == 1
        assert v.bills_table.empty_lbl.winfo_manager() == ""
    finally:
        v.destroy()


def test_data_table_selection_follows_the_filtered_rows(tk_root):
    from app.ui.components.data_table import DataTable
    t = DataTable(tk_root, columns=[("a", "A", 80)])
    try:
        t.set_data([{"a": "apple"}, {"a": "banana"}, {"a": "cherry"}])
        t.search_var.set("ch")
        first = t.tree.get_children()[0]
        t.tree.selection_set(first)
        assert t.get_selected() == {"a": "cherry"}
    finally:
        t.destroy()


def test_theme_styles_apply_and_database_settings_leads_with_backups(db, tk_root):
    from tkinter import ttk
    from app.ui import theme
    from app.ui.database_settings import DatabaseSettingsFrame
    theme.apply_ttk_theme(ttk.Style(tk_root))
    assert str(ttk.Style(tk_root).lookup("Treeview", "rowheight")) == "26"
    f = DatabaseSettingsFrame(tk_root, db)
    try:
        titles = []
        for w in f.winfo_children():
            if isinstance(w, tk.Frame) and w.winfo_children():
                inner = w.winfo_children()[0]
                labels = [c.cget("text") for c in inner.winfo_children() if isinstance(c, tk.Label)]
                if labels:
                    titles.append(labels[0])
        assert "Backups" in titles and "Where your data is kept" in titles
        assert titles.index("Backups") < titles.index("Where your data is kept")
    finally:
        f.destroy()
