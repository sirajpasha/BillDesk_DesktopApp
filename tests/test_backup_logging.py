"""Backups (verified, scheduled, pruned, restorable) and application logging."""
import importlib
import logging
import logging.handlers
import sys
import threading
import zipfile
from datetime import datetime, timedelta
from tkinter import messagebox

import pytest
from bson import ObjectId

from app import logging_setup
from app.config.settings import settings
from app.services.backup_service import BackupError, BackupService
from conftest import MockMongoDatabase


@pytest.fixture
def stocked(fake_db):
    fake_db.collection("bills").insert_one({"_id": ObjectId(), "invoice_no": "20261001-0001", "total_amount": 99.5,
                                            "created_at": datetime(2026, 10, 1, 9, 30), "items": [{"name": "Tomato", "qty": 2}]})
    fake_db.collection("users").insert_one({"user_id": "U1", "username": "admin", "unicode": "தமிழ் ₹"})
    return fake_db


def test_backup_round_trip_preserves_every_document_exactly(stocked, tmp_path):
    path = BackupService(stocked, tmp_path).create_backup("manual")
    assert path.exists() and path.name.startswith("billdesk_") and path.name.endswith("_manual.zip")
    with zipfile.ZipFile(path) as z:
        assert {"manifest.json", "bills.jsonl", "users.jsonl", "items.jsonl", "customers.jsonl", "suppliers.jsonl"} <= set(z.namelist())
    target = MockMongoDatabase()
    restored = BackupService(stocked, tmp_path).restore(path, target)
    for name in ("bills", "users", "items", "customers", "suppliers"):
        assert target.collection(name).docs == stocked.collection(name).docs, name
    assert restored["bills"] == 1 and restored["users"] == 1


def test_restore_refuses_a_non_empty_target_unless_replace_is_explicit(stocked, tmp_path):
    svc = BackupService(stocked, tmp_path)
    path = svc.create_backup()
    with pytest.raises(BackupError, match="not empty"):
        svc.restore(path, stocked)
    stocked.collection("bills").insert_one({"invoice_no": "EXTRA"})
    svc.restore(path, stocked, replace=True)
    assert [b["invoice_no"] for b in stocked.collection("bills").docs] == ["20261001-0001"]


def test_verification_detects_a_short_archive(stocked, tmp_path):
    path = BackupService(stocked, tmp_path).create_backup()
    with pytest.raises(BackupError, match="verification failed"):
        BackupService._verify(path, {"bills": 2})


def test_failed_backup_leaves_no_partial_file(stocked, tmp_path, monkeypatch):
    monkeypatch.setattr(stocked.collection("bills"), "find", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    with pytest.raises(RuntimeError):
        BackupService(stocked, tmp_path).create_backup()
    assert list(tmp_path.iterdir()) == []


def test_corrupt_archive_is_refused_on_restore(tmp_path):
    bad = tmp_path / "billdesk_x_20260101_000000_auto.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        BackupService(MockMongoDatabase(), tmp_path).restore(bad, MockMongoDatabase())


def _touch(dir_, db, when, label="auto"):
    p = dir_ / f"billdesk_{db}_{when:%Y%m%d_%H%M%S}_{label}.zip"
    p.write_bytes(b"x")
    return p


def test_backup_is_taken_only_when_the_last_one_is_old_enough(stocked, tmp_path):
    svc = BackupService(stocked, tmp_path)
    assert svc.backup_if_due(24) is not None
    assert svc.backup_if_due(24) is None                                     # fresh backup exists
    for p in tmp_path.glob("*.zip"):
        p.rename(p.with_name(p.name.replace(f"{datetime.now():%Y%m%d}", "20200101")))
    assert svc.backup_if_due(24) is not None                                 # last one is years old


def test_retention_keeps_recent_daily_plus_one_per_month_and_never_touches_manual(stocked, tmp_path):
    db = stocked.settings.db_name
    now = datetime(2026, 10, 9, 12, 0)
    files = {d: _touch(tmp_path, db, now - timedelta(days=d)) for d in range(0, 120)}      # 120 daily backups
    manual = _touch(tmp_path, db, now - timedelta(days=200), "manual")
    other_db = _touch(tmp_path, "other_db", now - timedelta(days=300))
    BackupService(stocked, tmp_path, keep_daily=14, keep_monthly=4).prune()
    left = {p.name for p in tmp_path.glob("*.zip")}
    assert all(files[d].name in left for d in range(14))                       # newest 14 kept
    assert sum(1 for d in range(14, 120) if files[d].name in left) <= 4        # + at most one per month beyond them
    assert files[119].name not in left and files[60].name not in left and files[39].name in left and files[70].name in left   # newest of Aug 31 / Jul 31
    assert manual.name in left and other_db.name in left


def test_list_and_last_backup_are_per_database(stocked, tmp_path):
    db = stocked.settings.db_name
    _touch(tmp_path, db, datetime(2026, 1, 1))
    _touch(tmp_path, "someone_else", datetime(2026, 6, 1))
    svc = BackupService(stocked, tmp_path)
    assert len(svc.list_backups()) == 2 and svc.last_backup()["created"] == datetime(2026, 1, 1)


def test_background_backup_helper_runs_once_and_survives_errors(stocked, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_enabled", True)
    main = importlib.import_module("main")
    before = set(threading.enumerate())
    main._start_background_backup(stocked)
    for t in set(threading.enumerate()) - before:
        t.join(10)
    assert len(list(tmp_path.glob("*.zip"))) == 1
    monkeypatch.setattr(BackupService, "backup_if_due", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    main._start_background_backup(stocked)                                  # must not raise
    monkeypatch.setattr(settings, "backup_enabled", False)
    assert main._start_background_backup(stocked) is None


def test_database_settings_screen_backs_up_and_reports_the_last_backup(stocked, tk_root, tmp_path, monkeypatch):
    from app.ui.database_settings import DatabaseSettingsFrame
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda t=None, m=None, **k: shown.append((t, m)))
    f = DatabaseSettingsFrame(tk_root, stocked)
    try:
        assert "No backup has been taken yet" in f.backup_status.cget("text")
        f.backup_now()
        assert shown and shown[0][0] == "Backup complete" and len(list(tmp_path.glob("*_manual.zip"))) == 1
        assert "Last backup:" in f.backup_status.cget("text")
    finally:
        f.destroy()


# ------------------------------------------------------------------ logging
@pytest.fixture
def clean_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("BILLDESK_LOG_DIR", str(tmp_path / "logs"))
    root = logging.getLogger()
    saved = (list(root.handlers), root.level, sys.excepthook, threading.excepthook, logging_setup._configured)
    root.handlers = []
    logging_setup._configured = False
    yield tmp_path / "logs" / "billdesk.log"
    for h in root.handlers:
        h.close()
    root.handlers, root.level, sys.excepthook, threading.excepthook, logging_setup._configured = saved[0], saved[1], saved[2], saved[3], saved[4]


def test_logging_writes_to_a_rotating_file_and_is_idempotent(clean_logging):
    logging_setup.setup_logging(console=False)
    logging_setup.setup_logging(console=False)
    logging.getLogger("test").warning("hello from the test")
    for h in logging.getLogger().handlers:
        h.flush()
    text = clean_logging.read_text(encoding="utf-8")
    assert "hello from the test" in text and text.count("Logging started") == 1
    assert sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger().handlers) == 1


def test_uncaught_exceptions_are_written_to_the_log(clean_logging):
    logging_setup.setup_logging(console=False)
    try:
        raise ValueError("kaboom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    for h in logging.getLogger().handlers:
        h.flush()
    text = clean_logging.read_text(encoding="utf-8")
    assert "Uncaught exception" in text and "kaboom" in text and "Traceback" in text


def test_ui_callback_errors_are_logged_and_shown_once_not_flooded(clean_logging, tk_root, monkeypatch):
    logging_setup.setup_logging(console=False)
    dialogs = []
    monkeypatch.setattr(messagebox, "showerror", lambda t=None, m=None, **k: dialogs.append((t, m)))
    old = tk_root.report_callback_exception
    logging_setup.install_tk_exception_handler(tk_root)
    try:
        for i in range(3):
            tk_root.report_callback_exception(RuntimeError, RuntimeError(f"bad {i}"), None)
        assert len(dialogs) == 1 and "RuntimeError: bad 0" in dialogs[0][1] and "billdesk.log" in dialogs[0][1]
        for h in logging.getLogger().handlers:
            h.flush()
        assert clean_logging.read_text(encoding="utf-8").count("Unhandled error in UI callback") == 3
    finally:
        tk_root.report_callback_exception = old


def test_previously_silent_failures_now_leave_a_trace(clean_logging, fake_db, tk_root):
    """finance KPIs used to swallow every error with `except Exception: pass`."""
    logging_setup.setup_logging(console=False)
    from app.models.common import CurrentUser
    from app.ui.finance_view import FinanceView
    fv = FinanceView(tk_root, fake_db, current_user=CurrentUser(user_id="U", username="a", roles=["Admin"]))
    try:
        fv.pay_svc.get_ar_aging = lambda: (_ for _ in ()).throw(RuntimeError("aging exploded"))
        fv.load_home_kpis()
        for h in logging.getLogger().handlers:
            h.flush()
        assert "aging exploded" in clean_logging.read_text(encoding="utf-8")
    finally:
        fv.destroy()
