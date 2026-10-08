"""Parked bills must survive closing / crashing the app."""
import json
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import pytest
from bson import ObjectId

from app.config.settings import settings
from app.models.common import CurrentUser
from app.services.billing_service import BillingService
from app.services.parked_store import ParkedBillStore
from app.ui.billing import BillingFrame


def _parked(total=120.0, customer=None):
    return {"customer": customer, "company": "SV", "total": total, "parked_at": "08/10/2026 22:14", "parked_by": "admin",
            "lines": [{"code": "101", "item_id": "VEG1", "name": "Avarai", "qty": "6", "unit": "Kg", "rate": "20.00"}]}


def test_parked_bills_survive_a_restart(fake_db):
    cust = {"_id": ObjectId(), "cust_id": "CUST001", "name": "Metro", "since": datetime(2026, 1, 1)}   # pymongo returns naive UTC datetimes
    BillingService(fake_db).park_bill(_parked(customer=cust))
    BillingService(fake_db).park_bill(_parked(total=50.0))
    after = BillingService(fake_db)                                     # "restart": a brand-new service instance
    bills = after.get_parked_bills()
    assert [b["total"] for b in bills] == [120.0, 50.0]
    assert bills[0]["customer"]["_id"] == cust["_id"] and bills[0]["customer"]["since"] == cust["since"]   # ObjectId / datetime intact
    assert bills[0]["lines"][0]["name"] == "Avarai"


def test_recall_removes_the_bill_for_good(fake_db):
    svc = BillingService(fake_db)
    svc.park_bill(_parked(1.0)); svc.park_bill(_parked(2.0))
    assert svc.recall_parked_bill(0)["total"] == 1.0
    assert [b["total"] for b in BillingService(fake_db).get_parked_bills()] == [2.0]
    assert svc.recall_parked_bill(5) is None


def test_corrupt_file_is_quarantined_not_overwritten_and_not_fatal(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{ this is not json", encoding="utf-8")
    store = ParkedBillStore(str(path))
    assert store.all() == []
    assert (tmp_path / "p.corrupt").read_text(encoding="utf-8") == "{ this is not json"
    store.add(_parked())
    assert json.loads(path.read_text(encoding="utf-8"))                 # usable again


def test_a_failed_write_is_reported_and_the_bill_is_not_counted_as_parked(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, so a folder cannot be created below me")
    store = ParkedBillStore(str(blocker / "sub" / "p.json"))
    with pytest.raises(OSError):
        store.add(_parked())
    assert store.all() == []


def test_the_write_is_atomic_no_temp_file_left_behind(tmp_path):
    store = ParkedBillStore(str(tmp_path / "p.json"))
    store.add(_parked()); store.discard(0)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["p.json"]


# ------------------------------------------------------------------ through the billing screen
@pytest.fixture
def screens(fake_db, tk_root, monkeypatch):
    dialogs, answers = [], {"yes": True}
    for n in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, n, lambda t=None, m=None, _n=n, **k: dialogs.append((_n, t, m)))
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: answers["yes"])
    fake_db.collection("items").insert_one({"item_id": "VEG1", "item_alias": "101", "name": "Avarai", "unit": "Kg",
                                            "standard_rate": 20.0, "status": "active", "is_deleted": 0})
    made = []

    def build():
        f = BillingFrame(tk_root, fake_db, BillingService(fake_db), CurrentUser(user_id="U", username="admin", roles=["Admin"]))
        f.dialogs, f.answers = dialogs, answers
        made.append(f)
        return f
    yield build
    for f in made:
        f.destroy()


def _enter(f, qty="6"):
    r = f.row_widgets[0]
    r["code"].insert(0, "101"); f._on_code_entered(0)
    r["qty"].delete(0, tk.END); r["qty"].insert(0, qty); f._recalculate_row(0)


def _recall_first(f):
    f._open_parked_modal()
    modal = [w for w in f.winfo_children() if isinstance(w, tk.Toplevel)][0]
    modal.update()                                   # Tk drops mouse events for windows that are not mapped yet
    card = [w for w in _walk(modal) if isinstance(w, tk.Label) and "Total:" in str(w.cget("text"))][0]
    card.master.event_generate("<Button-1>")
    f.update()
    return modal


def _walk(w):
    for c in w.winfo_children():
        yield c
        yield from _walk(c)


def test_screen_shows_bills_parked_before_the_restart_and_recalls_them(screens):
    first = screens()
    _enter(first)
    first.park_bill()
    assert first.parked_list_btn.cget("text") == "📥 Parked (1) (F7)" and first.row_widgets[0]["code"].get() == ""
    second = screens()                                                    # app restarted: new frame, new service
    assert second.parked_list_btn.cget("text") == "📥 Parked (1) (F7)"
    _recall_first(second)
    assert (second.row_widgets[0]["name"].get(), second.row_widgets[0]["qty"].get()) == ("Avarai", "6")
    assert second.parked_list_btn.cget("text") == "📥 Parked (0) (F7)"
    assert screens().parked_list_btn.cget("text") == "📥 Parked (0) (F7)"   # and it is gone for good


def test_recall_asks_before_replacing_a_bill_in_progress(screens):
    f = screens()
    _enter(f); f.park_bill()
    _enter(f, qty="9")                                                    # new bill in progress
    f.answers["yes"] = False
    _recall_first(f)
    assert f.row_widgets[0]["qty"].get() == "9" and len(f.billing.get_parked_bills()) == 1      # untouched
    f.answers["yes"] = True
    _recall_first(f)
    assert f.row_widgets[0]["qty"].get() == "6" and len(f.billing.get_parked_bills()) == 0


def test_a_failure_while_loading_a_recalled_bill_does_not_lose_it(screens, monkeypatch):
    f = screens()
    _enter(f); f.park_bill()
    errors = []
    f.winfo_toplevel().report_callback_exception = lambda *exc: errors.append(exc)      # Tk swallows callback errors
    monkeypatch.setattr(f, "_load_parked_bill", lambda pb: (_ for _ in ()).throw(RuntimeError("boom")))
    _recall_first(f)
    assert errors and "boom" in str(errors[0][1])
    assert len(f.billing.get_parked_bills()) == 1
    assert len(BillingService(f.db).get_parked_bills()) == 1               # still on disk
