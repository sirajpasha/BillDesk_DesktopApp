"""`BillDesk.exe --selftest` (or `python main.py --selftest`): prove an installation works end to end, without a window.

It uses a throw-away database on a free local port in a temp folder - it never touches the real data - and exercises
the same code paths a day of billing does: start MongoDB as a replica set, first-run setup, login, a bill with a
counter payment (in a transaction), ledger postings, PDFs, backup + restore, integrity check.
Exit code 0 = everything worked. Used by build_windows.ps1 as the smoke test of every build.
"""
from __future__ import annotations

import logging
import shutil
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List

log = logging.getLogger("selftest")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_selftest() -> int:
    from app import paths
    from app.config.settings import Settings, settings
    from app.database.connection import MongoDatabase
    from app.database.local_mongod import ensure_local_mongod, find_mongod, stop_local_mongod

    tmp = Path(tempfile.mkdtemp(prefix="billdesk_selftest_"))
    settings.parked_bills_file = str(tmp / "parked.json")
    port = _free_port()
    url = f"mongodb://127.0.0.1:{port}"
    results: List[tuple] = []
    ctx: dict = {}

    def step(name: str, fn: Callable[[], str]) -> bool:
        t = time.monotonic()
        try:
            detail = fn() or ""
            results.append((name, True))
            print(f"[ OK ] {name}  {detail}  ({time.monotonic() - t:.1f}s)", flush=True)
            return True
        except Exception as exc:
            results.append((name, False))
            log.error("selftest step failed: %s", name, exc_info=True)
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            return False

    def files():
        need = ["app/assets/icon.png", "data/seed_data.json"]
        missing = [n for n in need if not paths.resource_path(n).exists()]
        assert not missing, f"missing shipped files: {missing}"
        assert find_mongod() is not None, "mongod.exe not found"
        return f"resources at {paths.app_root()}"

    def imports():
        import bcrypt, certifi, pymongo, reportlab, tkinter  # noqa: F401
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            import fitz  # noqa: F401
        return f"pymongo {pymongo.version}"

    def tk_ok():
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            return f"no display available ({exc}) - skipped"
        root.withdraw()
        root.destroy()
        return "Tk starts"

    def server():
        state = ensure_local_mongod(url, db_dir=tmp / "db", log_file=tmp / "mongod.log", replica_set="rs0")
        db = MongoDatabase(Settings(mongodb_url=url, db_name="billdesk_selftest"))
        db.connect()
        db.ensure_indexes()
        ctx["db"] = db
        assert db.supports_transactions, "replica set did not come up"
        return f"MongoDB {state} on port {port}, transactions available"

    def setup_and_login():
        from app import first_run
        from app.services.auth_service import AuthService
        db = ctx["db"]
        assert first_run.needs_first_run(db)
        creds = first_run.seed_first_run(db)
        user = AuthService(db).login(creds["username"], creds["password"])
        assert "admin" in user.roles
        db.collection("customers").insert_one({"cust_id": "C1", "name": "Self Test Customer", "status": "active", "is_deleted": 0,
                                               "current_balance": 0.0, "credit_limit": 0.0, "payment_terms_days": 30})
        db.collection("items").insert_one({"item_id": "I1", "item_alias": "101", "name": "Tomato", "unit": "kg", "status": "active",
                                           "is_deleted": 0, "stock": 100.0})
        return "first-run admin created, login works"

    def billing():
        from app.models.billing import BillCreate, BillItem
        from app.services.billing_service import BillingService
        from app.services.ledger_service import LedgerService
        db = ctx["db"]
        item = BillItem(item_id="I1", name="Tomato", qty=10, unit="kg", rate=20.0, amount=200.0)
        bill = BillingService(db).create_bill(BillCreate(
            invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="Self Test Customer", items=[item],
            total_amount=200.0, balance_due=200.0, created_by="selftest", amount_received=80.0))
        ctx["bill"] = bill
        assert db.collection("customers").find_one({"cust_id": "C1"})["current_balance"] == 120.0
        assert db.collection("items").find_one({"item_id": "I1"})["stock"] == 90.0
        assert LedgerService(db).get_trial_balance()["is_balanced"]
        return f"invoice {bill['invoice_no']} saved with payment, ledger balanced"

    def atomic():
        from app.models.billing import BillCreate, BillItem
        from app.services.billing_service import BillingService
        db = ctx["db"]
        svc = BillingService(db)
        before = db.collection("bills").count_documents({})
        svc.ledger.post_sale = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated crash"))
        item = BillItem(item_id="I1", name="Tomato", qty=1, unit="kg", rate=20.0, amount=20.0)
        try:
            svc.create_bill(BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="x", items=[item],
                                       total_amount=20.0, balance_due=20.0, created_by="selftest"))
        except RuntimeError:
            pass
        assert db.collection("bills").count_documents({}) == before, "a failed save left a bill behind"
        assert db.collection("items").find_one({"item_id": "I1"})["stock"] == 90.0, "a failed save changed stock"
        return "a failed save leaves no trace"

    def pdfs():
        from app.printing.invoice import generate_dc_pdf, generate_invoice_pdf
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        bill = ctx["bill"]
        out = tmp / "out"
        out.mkdir()
        inv = generate_invoice_pdf(str(out / "inv.pdf"), bill, company={"name": "Self Test Co"}, customer={"name": "Self Test Customer"})
        dc = generate_dc_pdf(str(out / "dc.pdf"), bill, company={"name": "Self Test Co"}, customer={"name": "Self Test Customer"})
        t_inv = "".join(p.get_text() for p in fitz.open(inv))
        t_dc = "".join(p.get_text() for p in fitz.open(dc))
        assert bill["invoice_no"] in t_inv and "Tomato" in t_inv
        assert "Tomato" in t_dc and "200.00" not in t_dc, "delivery challan must not show amounts"
        return "invoice and delivery challan PDFs generated"

    def backup_restore():
        from app.services.backup_service import BackupService
        db = ctx["db"]
        svc = BackupService(db, tmp / "backups")
        zip_path = svc.create_backup("selftest")
        other = MongoDatabase(Settings(mongodb_url=url, db_name="billdesk_selftest_restored"))
        other.connect()
        restored = svc.restore(zip_path, other)
        assert other.collection("bills").count_documents({}) == db.collection("bills").count_documents({})
        return f"backup verified and restored ({sum(restored.values())} documents)"

    def integrity():
        from app.services.integrity_service import IntegrityService
        rep = IntegrityService(ctx["db"]).run_all()
        assert rep["summary"]["fail"] == 0, [c for c in rep["checks"] if c["status"] == "fail"]
        return f"{rep['summary']['ok']} ok, {rep['summary']['warn']} warnings, 0 failures"

    try:
        for name, fn in [("shipped files present", files), ("libraries import", imports), ("window system", tk_ok),
                         ("start MongoDB (replica set)", server), ("first-run setup and login", setup_and_login),
                         ("bill + counter payment + ledger", billing), ("transaction rolls back on failure", atomic),
                         ("invoice and delivery challan PDFs", pdfs), ("backup and restore", backup_restore),
                         ("integrity check", integrity)]:
            if not step(name, fn) and name in ("shipped files present", "libraries import", "start MongoDB (replica set)"):
                break                                   # nothing later can work without these
    finally:
        try:
            stop_local_mongod(url)
            time.sleep(1.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in results if not ok]
    print("\nSELFTEST OK" if not failed else f"\nSELFTEST FAILED: {', '.join(failed)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run_selftest())
