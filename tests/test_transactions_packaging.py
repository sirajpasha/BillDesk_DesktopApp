"""Transactions (real replica set), local MongoDB management, first run, packaging consistency, self-test."""
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app import first_run, paths
from app.config.settings import Settings, settings
from app.database import connection as conn
from app.database.connection import MongoDatabase, transactional
from app.database.local_mongod import (ensure_local_mongod, find_mongod, parse_local_url, stop_local_mongod, LocalMongoError)
from app.models.billing import BillCreate, BillItem
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService

ROOT = Path(__file__).resolve().parent.parent
needs_mongod = pytest.mark.skipif(find_mongod() is None, reason="no mongod.exe available")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ @transactional / paths / URL parsing (no server)
def test_transactional_wraps_the_call_and_nested_calls_share_one_transaction():
    log = []

    class Db:
        @contextlib.contextmanager
        def transaction(self):
            log.append("begin")
            try:
                yield
            finally:
                log.append("end")

    class Svc:
        db = Db()

        @transactional
        def outer(self):
            log.append("outer")
            return self.inner() + 1

        @transactional
        def inner(self):
            log.append("inner")
            return 41

    assert Svc().outer() == 42
    assert log == ["begin", "outer", "begin", "inner", "end", "end"]    # (re-entrancy is MongoDatabase.transaction's job, below)


def test_transactional_tolerates_a_database_without_transaction_support():
    class Svc:
        db = object()

        @transactional
        def work(self):
            return "done"
    assert Svc().work() == "done"


@pytest.mark.parametrize("url,expected", [
    ("mongodb://127.0.0.1:27018", ("127.0.0.1", 27018)), ("mongodb://localhost:27019/?x=1", ("127.0.0.1", 27019)),
    ("mongodb://127.0.0.1", ("127.0.0.1", 27017)), ("mongodb://db.example.com:27017", None),
    ("mongodb+srv://u:p@cluster0.mongodb.net/", None), ("mongodb://10.0.0.5:27018", None),
])
def test_only_local_urls_are_ever_managed(url, expected):
    assert parse_local_url(url) == expected


def test_remote_urls_are_never_touched():
    assert ensure_local_mongod("mongodb+srv://u:p@cluster0.mongodb.net/") == "remote"
    assert stop_local_mongod("mongodb://db.example.com:27017") is False


def test_paths_for_source_and_packaged_builds(monkeypatch, tmp_path):
    assert paths.resource_path("app/assets/icon.png").exists() and paths.app_root() == ROOT
    monkeypatch.setenv("BILLDESK_DATA_DIR", str(tmp_path / "data"))
    assert paths.user_data_dir() == tmp_path / "data" and paths.env_file() == tmp_path / "data" / ".env"
    assert paths.output_dir().parts[-2:] == ("Docs", "Output")                  # source checkout
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    assert paths.output_dir() == tmp_path / "data" / "output"                  # installed build: never under Program Files
    assert paths.app_root() == tmp_path / "bundle"


def test_logs_go_to_the_data_folder(monkeypatch, tmp_path):
    from app import logging_setup
    monkeypatch.delenv("BILLDESK_LOG_DIR", raising=False)
    monkeypatch.setenv("BILLDESK_DATA_DIR", str(tmp_path))
    assert logging_setup.log_dir() == tmp_path / "logs"


def test_replica_set_is_off_by_default():
    assert settings.mongo_replica_set == ""


# ------------------------------------------------------------------ first run / passwords
def test_first_run_creates_one_admin_with_a_random_password(fake_db):
    for name in ("users", "roles", "companies", "role_permissions"):
        fake_db.collection(name).docs.clear()
    assert first_run.needs_first_run(fake_db)
    a = first_run.seed_first_run(fake_db)
    assert a["username"] == "admin" and len(a["password"]) == 10 and a["password"] != "admin123"
    assert [u["username"] for u in fake_db.collection("users").docs] == ["admin"]
    assert fake_db.collection("role_permissions").find_one({"role": "manager"})["menus"]
    user = AuthService(fake_db).login("admin", a["password"])                  # the shown password works, the old default does not
    assert "admin" in user.roles
    with pytest.raises(ValueError):
        AuthService(fake_db).login("admin", "admin123")
    assert fake_db.collection("companies").count_documents({}) >= 1 and fake_db.collection("roles").count_documents({}) >= 3
    assert not first_run.needs_first_run(fake_db)
    with pytest.raises(RuntimeError, match="already has users"):
        first_run.seed_first_run(fake_db)


def test_generated_passwords_are_unpredictable_and_unambiguous():
    pws = {first_run.generate_password() for _ in range(200)}
    assert len(pws) == 200 and not any(set(p) & set("0O1lI") for p in pws)


def test_password_reset(fake_db):
    fake_db.collection("users").insert_one({"user_id": "U1", "username": "bob", "roles": ["user"], "status": "active", "is_deleted": 0, "password_hash": ""})
    ads = AdminService(fake_db)
    ads.set_password("bob", "brandnew1")
    assert AuthService(fake_db).login("bob", "brandnew1").username == "bob"
    for bad, msg in (("123", "at least 6"), ("x" * 73, "too long")):
        with pytest.raises(ValueError, match=msg):
            ads.set_password("bob", bad)
    with pytest.raises(ValueError, match="not found"):
        ads.set_password("nobody", "whatever1")


def test_first_run_is_wired_into_main(monkeypatch):
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "first_run.needs_first_run(db)" in src and "ensure_local_mongod(" in src and "--selftest" in src
    assert "_shutdown()" in src and 'mongo_state == "started"' in src


def test_single_instance_guard():
    if sys.platform != "win32":
        pytest.skip("Windows mutex")
    import importlib
    main = importlib.import_module("main")
    assert main._acquire_single_instance() is True
    assert main._acquire_single_instance() is False                             # a second window/process is refused


# ------------------------------------------------------------------ packaging consistency (cheap, runs everywhere)
def test_packaging_files_agree_with_each_other():
    spec = (ROOT / "BillDesk.spec").read_text(encoding="utf-8")
    iss = (ROOT / "installer" / "BillDesk.iss").read_text(encoding="utf-8")
    ps1 = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    assert 'name="BillDesk"' in spec and "app/assets/icon.ico" in spec and (ROOT / "app" / "assets" / "icon.ico").exists()
    assert r'{#DistDir}\BillDesk\*' in iss and "BillDesk.exe" in iss and "OutputBaseFilename=BillDesk-Setup" in iss
    assert "AppMutex=BillDeskDesktopNativeMutex" in iss and "BillDeskDesktopNativeMutex" in (ROOT / "main.py").read_text(encoding="utf-8")
    assert "--selftest" in ps1 and "BillDesk.spec" in ps1 and "dist\\BillDesk\\BillDesk.exe" in ps1
    assert "mongod.exe" in spec and "seed_data.json" in spec
    assert "*.spec" not in (ROOT / ".gitignore").read_text(encoding="utf-8").split()


def test_requirements_list_everything_the_app_imports():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ("pymongo", "pydantic", "python-dotenv", "bcrypt", "reportlab", "certifi", "pymupdf", "pillow"):   # pillow: print preview
        assert pkg in req, pkg


# ------------------------------------------------------------------ real MongoDB (skipped when no mongod.exe is available)
@pytest.fixture(scope="module")
def replica_set_server():
    port = _free_port()
    url = f"mongodb://127.0.0.1:{port}"
    tmp = Path(tempfile.mkdtemp(prefix="bd_tx_"))
    state = ensure_local_mongod(url, db_dir=tmp / "db", log_file=tmp / "m.log", replica_set="rs0")
    assert state == "started"
    yield url
    stop_local_mongod(url)
    import shutil, time
    time.sleep(1)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def rs_db(replica_set_server):
    db = MongoDatabase(Settings(mongodb_url=replica_set_server, db_name="bd_tx_test"))
    db.connect()
    for c in db.list_collection_names():
        db.db[c].drop()
    for c in ("bills", "stock_transactions", "bill_audits", "journal_entries", "payments", "ledger_transactions"):
        db.db.create_collection(c)
    db.db.customers.insert_one({"cust_id": "C1", "name": "Cust", "status": "active", "is_deleted": 0, "current_balance": 0.0, "credit_limit": 0.0, "payment_terms_days": 30})
    db.db.items.insert_one({"item_id": "I1", "item_alias": "101", "name": "Apple", "unit": "kg", "status": "active", "is_deleted": 0, "stock": 100.0})
    yield db
    db.close()


def _bill(qty=5, received=None):
    it = BillItem(item_id="I1", name="Apple", qty=qty, unit="kg", rate=20.0, amount=qty * 20.0)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="Cust", items=[it],
                      total_amount=qty * 20.0, balance_due=qty * 20.0, created_by="t", amount_received=received)


@needs_mongod
def test_the_helper_starts_a_replica_set_and_the_connection_supports_transactions(rs_db, replica_set_server):
    assert rs_db.supports_transactions
    assert ensure_local_mongod(replica_set_server, replica_set="rs0") == "running"


@needs_mongod
def test_a_failure_in_the_middle_of_saving_a_bill_leaves_no_trace(rs_db):
    svc = BillingService(rs_db)
    svc.ledger.post_sale = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash while posting"))
    with pytest.raises(RuntimeError):
        svc.create_bill(_bill(received=10.0))
    d = rs_db.db
    assert d.bills.count_documents({}) == 0 and d.stock_transactions.count_documents({}) == 0 and d.bill_audits.count_documents({}) == 0
    assert d.items.find_one({"item_id": "I1"})["stock"] == 100.0 and d.customers.find_one({"cust_id": "C1"})["current_balance"] == 0.0
    assert conn._active_session.get() is None


@needs_mongod
def test_a_successful_bill_commits_everything_and_is_visible(rs_db):
    BillingService(rs_db).create_bill(_bill(qty=10, received=60.0))
    d = rs_db.db
    assert d.bills.count_documents({}) == 1 and d.payments.count_documents({}) == 1 and d.journal_entries.count_documents({}) >= 2
    assert d.items.find_one({"item_id": "I1"})["stock"] == 90.0 and d.customers.find_one({"cust_id": "C1"})["current_balance"] == 140.0


@needs_mongod
def test_nested_transaction_blocks_join_the_outer_one_and_roll_back_together(rs_db):
    with pytest.raises(RuntimeError):
        with rs_db.transaction():
            rs_db.collection("bills").insert_one({"invoice_no": "N-1"})
            with rs_db.transaction():                       # joins, does not start a second transaction
                rs_db.collection("bills").insert_one({"invoice_no": "N-2"})
            raise RuntimeError("outer failure after the inner block finished")
    assert rs_db.db.bills.count_documents({}) == 0


@needs_mongod
def test_standalone_servers_still_work_without_atomicity():
    port = _free_port()
    url = f"mongodb://127.0.0.1:{port}"
    tmp = Path(tempfile.mkdtemp(prefix="bd_sa_"))
    try:
        assert ensure_local_mongod(url, db_dir=tmp / "db", log_file=tmp / "m.log") == "started"
        db = MongoDatabase(Settings(mongodb_url=url, db_name="bd_sa_test"))
        db.connect()
        assert db.supports_transactions is False
        with db.transaction() as s:
            assert s is None
            db.collection("t").insert_one({"x": 1})
        assert db.db.t.count_documents({}) == 1
        db.close()
    finally:
        stop_local_mongod(url)
        import shutil, time
        time.sleep(1)
        shutil.rmtree(tmp, ignore_errors=True)


@needs_mongod
def test_a_missing_server_without_mongod_reports_a_clear_error(monkeypatch):
    monkeypatch.setattr("app.database.local_mongod.find_mongod", lambda: None)
    with pytest.raises(LocalMongoError, match="no mongod.exe was found"):
        ensure_local_mongod(f"mongodb://127.0.0.1:{_free_port()}")


@needs_mongod
def test_the_built_in_selftest_passes_from_source():
    """The same self-test build_windows.ps1 runs against the packaged exe."""
    env = dict(os.environ, MONGODB_URL="mongodb://127.0.0.1:1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "main.py"), "--selftest"], capture_output=True, text=True, timeout=240, env=env, cwd=ROOT)
    assert r.returncode == 0 and "SELFTEST OK" in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
    assert "[FAIL]" not in r.stdout


@needs_mongod
def test_existing_standalone_data_survives_conversion_to_a_replica_set():
    """The production migration path: today's data directory was written by a standalone server."""
    import shutil, time
    port = _free_port()
    url = f"mongodb://127.0.0.1:{port}"
    tmp = Path(tempfile.mkdtemp(prefix="bd_conv_"))
    try:
        assert ensure_local_mongod(url, db_dir=tmp / "db", log_file=tmp / "m.log") == "started"            # standalone, like today
        old = MongoDatabase(Settings(mongodb_url=url, db_name="bd_conv"))
        old.connect()
        assert not old.supports_transactions
        old.db.bills.insert_many([{"invoice_no": f"20260101-{i:04d}", "total_amount": float(i)} for i in range(1, 51)])
        old.db.bills.create_index("invoice_no", unique=True)
        old.close()
        stop_local_mongod(url)
        time.sleep(2)

        assert ensure_local_mongod(url, db_dir=tmp / "db", log_file=tmp / "m.log", replica_set="rs0") == "started"   # same files, now a replica set
        new = MongoDatabase(Settings(mongodb_url=url, db_name="bd_conv"))
        new.connect()
        assert new.supports_transactions
        assert new.db.bills.count_documents({}) == 50 and "invoice_no_1" in {i["name"] for i in new.db.bills.list_indexes()}
        with pytest.raises(RuntimeError):
            with new.transaction():
                new.collection("bills").insert_one({"invoice_no": "T-1"})
                raise RuntimeError("rollback")
        assert new.db.bills.count_documents({}) == 50
        new.close()
    finally:
        stop_local_mongod(url)
        time.sleep(1)
        shutil.rmtree(tmp, ignore_errors=True)
