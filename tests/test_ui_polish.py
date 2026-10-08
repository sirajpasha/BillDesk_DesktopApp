"""Regression tests for D-17 (history cap notice) and D-18 (no hard-coded login, honest payment dialog)."""
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox

from app.models.common import CurrentUser
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.ui.billing import BillingFrame
from app.ui.history import BillHistoryFrame
from app.ui.login_window import LoginWindow


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def test_login_form_has_no_prefilled_credentials(fake_db, tk_root):
    lw = LoginWindow(tk_root, AuthService(fake_db))
    try:
        tk_root.update()
        assert lw.username_entry.get() == "" and lw.password_entry.get() == ""
    finally:
        lw.destroy()


def _bills(db, n):
    for i in range(n):
        db.collection("bills").insert_one({
            "invoice_no": f"20260101-{i:04d}", "invoice_date": "2026-01-01", "customer_id": "CASH", "customer_name": "c",
            "items": [], "total_amount": 1.0, "balance_due": 1.0, "status": "unpaid", "is_deleted": 0,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)})


def test_history_tells_the_user_when_it_is_truncated(fake_db, tk_root, monkeypatch):
    _bills(fake_db, 7)
    monkeypatch.setattr(BillHistoryFrame, "MAX_BILLS", 5)
    h = BillHistoryFrame(tk_root, fake_db, BillingService(fake_db), current_user=CurrentUser(user_id="U", username="a", roles=["Admin"]))
    h.refresh()
    assert len(h._all_bills) == 5 and "latest 5 bills" in h.showing_label.cget("text")
    monkeypatch.setattr(BillHistoryFrame, "MAX_BILLS", 50)
    h.refresh()
    assert len(h._all_bills) == 7 and "latest" not in h.showing_label.cget("text")
    h.destroy()


def test_payment_dialog_shows_real_outstanding_and_unpaid_bill_count(fake_db, tk_root, monkeypatch):
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda *a, **k: None)
    fake_db.collection("customers").update_one({"cust_id": "CUST001"}, {"$set": {"current_balance": 750.0}})
    for st in ("unpaid", "partial", "paid"):
        fake_db.collection("bills").insert_one({"invoice_no": f"B-{st}", "customer_id": "CUST001", "status": st, "is_deleted": 0, "total_amount": 1.0})
    fake_db.collection("items").insert_one({"item_id": "V1", "item_alias": "101", "name": "Avarai", "unit": "Kg", "standard_rate": 20.0, "status": "active", "is_deleted": 0})
    f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
    try:
        f.selected_customer = {"cust_id": "CUST001", "name": "Metro Retailers", "current_balance": 0.0}   # stale snapshot
        f.row_widgets[0]["code"].insert(0, "101"); f._on_code_entered(0)
        f._open_payment_modal()
        modal = [w for w in f.winfo_children() if isinstance(w, tk.Toplevel)][0]
        texts = [str(w.cget("text")) for w in _walk(modal) if isinstance(w, tk.Label)]
        assert any("OUTSTANDING" in t and "750.00" in t for t in texts)          # fresh from the DB, not the stale snapshot
        assert any("UNPAID BILLS" in t and t.endswith("2") for t in texts)
        assert not any(t.strip() in ("Manual", "[ Auto FIFO ]") for t in texts)
        assert not any(isinstance(w, tk.Checkbutton) for w in _walk(modal))
        modal.destroy()
    finally:
        f.destroy()
