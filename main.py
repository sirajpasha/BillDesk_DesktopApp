import os
import sys

# Ensure Windows TCL/TK paths are reliably discovered
tcl_candidate = os.path.join(sys.prefix, "tcl", "tcl8.6")
tk_candidate = os.path.join(sys.prefix, "tcl", "tk8.6")
if os.path.exists(tcl_candidate) and "TCL_LIBRARY" not in os.environ:
    os.environ["TCL_LIBRARY"] = tcl_candidate
if os.path.exists(tk_candidate) and "TK_LIBRARY" not in os.environ:
    os.environ["TK_LIBRARY"] = tk_candidate

import tkinter as tk
from tkinter import messagebox
import traceback

from app.config.settings import settings
from app.database.connection import MongoDatabase
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


def main() -> int:
    print("=" * 60)
    print("  BillDesk — Native Desktop Mandi POS & ERP")
    print("=" * 60)
    print(f"Connecting to MongoDB at {settings.mongodb_url} (db: {settings.db_name})...")

    db = MongoDatabase(settings)
    try:
        db.connect()
        db.ensure_indexes()
        print("MongoDB connection established successfully.")
    except Exception as exc:
        print(f"ERROR: Failed to connect to MongoDB: {exc}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("MongoDB Connection Error", f"Could not connect to MongoDB at {settings.mongodb_url}:\n\n{exc}")
        root.destroy()
        return 1

    root = tk.Tk()
    root.title("BillDesk Native")
    root.withdraw()

    auth = AuthService(db)
    billing = BillingService(db)

    print("Opening Sign-In dialog...")
    login = LoginWindow(root, auth)
    root.wait_window(login)

    if not login.current_user:
        print("Sign-in cancelled. Exiting.")
        db.close()
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
        traceback.print_exc()
        messagebox.showerror("Application Error", f"Fatal error starting application:\n\n{exc}", parent=root)
        db.close()
        root.destroy()
        return 1

    def on_close():
        print("Closing application...")
        db.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    print("Application event loop running.")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
