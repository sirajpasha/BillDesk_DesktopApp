import os
import sys

# Ensure Windows TCL/TK paths are reliably discovered
if not getattr(sys, "frozen", False):          # a packaged build carries its own Tcl/Tk
    tcl_candidate = os.path.join(sys.prefix, "tcl", "tcl8.6")
    tk_candidate = os.path.join(sys.prefix, "tcl", "tk8.6")
    if os.path.exists(tcl_candidate) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_candidate
    if os.path.exists(tk_candidate) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_candidate

import logging
import threading
import tkinter as tk
from tkinter import messagebox
import traceback

from app.logging_setup import setup_logging, install_tk_exception_handler, log_path
from app.database.local_mongod import ensure_local_mongod, stop_local_mongod, LocalMongoError
from app import first_run

from app.config.settings import settings
from app.database.connection import MongoDatabase
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


def _acquire_single_instance():
    """Two BillDesk windows on one database would fight over parked bills and invoice numbers. Windows only; the
    installer uses the same mutex name (AppMutex) to refuse upgrades while the app runs."""
    if sys.platform != "win32":
        return True
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "BillDeskDesktopNativeMutex")
    already = ctypes.windll.kernel32.GetLastError() == 183          # ERROR_ALREADY_EXISTS
    _acquire_single_instance.handle = handle                        # keep it alive for the life of the process
    return not already


def _start_background_backup(db) -> None:
    """One verified backup per 24 h, off the UI thread; failures are logged, never block billing."""
    if not settings.backup_enabled:
        return

    def run():
        try:
            from app.services.backup_service import BackupService
            BackupService(db).backup_if_due(settings.backup_max_age_hours)
        except Exception:
            logging.getLogger("backup").exception("Automatic backup failed")

    threading.Thread(target=run, name="auto-backup", daemon=True).start()


def main() -> int:
    setup_logging()
    log = logging.getLogger("main")
    if "--selftest" in sys.argv:
        from app.selftest import run_selftest
        return run_selftest()
    if os.environ.get("BILLDESK_ALLOW_MULTIPLE") != "1" and not _acquire_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("BillDesk", "BillDesk is already running on this computer.")
        root.destroy()
        return 0
    print("=" * 60)
    print("  BillDesk — Native Desktop Mandi POS & ERP")
    print("=" * 60)
    print(f"Connecting to MongoDB at {settings.mongodb_url} (db: {settings.db_name})...")

    try:
        mongo_state = ensure_local_mongod(settings.mongodb_url, replica_set=settings.mongo_replica_set)
        log.info("MongoDB: %s", mongo_state)
    except LocalMongoError as exc:
        log.exception("Could not start MongoDB")
        print(f"ERROR: {exc}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("MongoDB", f"{exc}\n\nLog: {log_path()}")
        root.destroy()
        return 1

    db = MongoDatabase(settings)

    def _shutdown():
        """Close the connection; stop the MongoDB server only if THIS run started it (never one that was already there)."""
        try:
            db.close()
        finally:
            if mongo_state == "started":
                stop_local_mongod(settings.mongodb_url)

    try:
        db.connect()
        db.ensure_indexes()
        print("MongoDB connection established successfully.")
        log.info("Connected to MongoDB %s / %s", settings.mongodb_url, settings.db_name)
    except Exception as exc:
        print(f"ERROR: Failed to connect to MongoDB: {exc}")
        log.exception("MongoDB connection failed")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("MongoDB Connection Error", f"Could not connect to MongoDB at {settings.mongodb_url}:\n\n{exc}")
        root.destroy()
        return 1

    root = tk.Tk()
    root.title("BillDesk Native")
    root.withdraw()
    install_tk_exception_handler(root)
    if first_run.needs_first_run(db):
        creds = first_run.seed_first_run(db)
        messagebox.showinfo(
            "Welcome to BillDesk",
            "This is a new installation. An administrator account was created:\n\n"
            f"    Username:  {creds['username']}\n    Password:  {creds['password']}\n\n"
            "Write the password down now - it is shown only once.\n"
            "(Forgot it later? python scripts/reset_password.py --user admin)")
    _start_background_backup(db)

    auth = AuthService(db)
    billing = BillingService(db)

    print("Opening Sign-In dialog...")
    login = LoginWindow(root, auth)
    root.wait_window(login)

    if not login.current_user:
        print("Sign-in cancelled. Exiting.")
        _shutdown()
        root.destroy()
        return 0

    print(f"User '{login.current_user.username}' signed in. Launching main workspace...")

    try:
        root.deiconify()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = min(1380, sw - 40)
        h = min(860, sh - 60)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.lift()
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
        root.focus_force()

        window = MainWindow(root, db, auth, billing, login.current_user)
        window.show()
    except Exception as exc:
        print(f"ERROR: Failed to initialize MainWindow: {exc}")
        log.exception("MainWindow failed to start")
        traceback.print_exc()
        messagebox.showerror("Application Error", f"Fatal error starting application:\n\n{exc}", parent=root)
        db.close()
        root.destroy()
        return 1

    def on_close():
        print("Closing application...")
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    print("Application event loop running.")
    try:
        root.mainloop()                 # ends however the window is closed (X button, File > Exit, ...)
    finally:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
