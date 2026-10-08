import os, sys, json, time
sys.path.insert(0, os.getcwd())
import tkinter as tk
from tkinter import messagebox, ttk

tcl = os.path.join(sys.prefix, "tcl", "tcl8.6"); tk_ = os.path.join(sys.prefix, "tcl", "tk8.6")
if os.path.exists(tcl) and "TCL_LIBRARY" not in os.environ: os.environ["TCL_LIBRARY"] = tcl
if os.path.exists(tk_) and "TK_LIBRARY" not in os.environ: os.environ["TK_LIBRARY"] = tk_

os.environ.setdefault("PARKED_BILLS_FILE", os.path.join(os.environ.get("QA_SCRATCH", "."), "parked_bills_qa.json"))   # never the real %APPDATA% file
from app.config.settings import settings
assert "qa" in settings.db_name, "refusing to run against non-QA DB"
from app.database.connection import MongoDatabase
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService

SCRATCH = os.environ["QA_SCRATCH"]
RESULTS = []
DIALOGS = []          # every messagebox call is captured here
ANSWER = {"yesno": True}

def check(tc, desc, cond, evidence=""):
    RESULTS.append((tc, desc, bool(cond), str(evidence)))
    print(("PASS" if cond else "FAIL"), tc, "-", desc, "|", str(evidence)[:300])

def _rec(kind):
    def f(title=None, message=None, **kw):
        DIALOGS.append((kind, title, message))
        if kind in ("askyesno", "askokcancel", "askretrycancel"): return ANSWER["yesno"]
        return "ok"
    return f
for k in ["showinfo","showwarning","showerror","askyesno","askokcancel","askretrycancel"]:
    setattr(messagebox, k, _rec(k))

def last_dialog(): return DIALOGS[-1] if DIALOGS else None
def clear_dialogs(): DIALOGS.clear()

def boot(username="admin", password="admin123"):
    db = MongoDatabase(settings); db.connect()
    auth = AuthService(db); billing = BillingService(db)
    user = auth.login(username, password)
    root = tk.Tk(); root.title("BillDesk QA")
    w, h = 1380, 860
    root.geometry(f"{w}x{h}+20+20"); root.update()
    from app.ui.main_window import MainWindow
    win = MainWindow(root, db, auth, billing, user)
    win.show(); root.attributes("-topmost", True); root.update()
    return root, db, auth, billing, user, win

def pump(root, n=5, delay=0.02):
    for _ in range(n):
        root.update_idletasks(); root.update(); time.sleep(delay)

def shot(root, name):
    """Capture ONLY the application window region."""
    from PIL import ImageGrab
    root.lift(); root.attributes("-topmost", True); pump(root, 8)
    x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
    im = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    p = os.path.join(SCRATCH, "shots", name + ".png"); os.makedirs(os.path.dirname(p), exist_ok=True)
    im.save(p); return p

def toplevels(widget):
    return [w for w in widget.winfo_children() if isinstance(w, tk.Toplevel)]

def walk(widget):
    for c in widget.winfo_children():
        yield c
        yield from walk(c)

def find_button(container, text):
    for w in walk(container):
        try:
            if isinstance(w, (tk.Button, ttk.Button)) and text.lower() in str(w.cget("text")).lower(): return w
        except tk.TclError: pass
    return None

def labels_text(container):
    out = []
    for w in walk(container):
        if isinstance(w, (tk.Label, ttk.Label)):
            try: out.append(str(w.cget("text")))
            except tk.TclError: pass
    return out

def finish(root=None):
    fails = [r for r in RESULTS if not r[2]]
    print(f"\nTOTAL {len(RESULTS)} PASS {len(RESULTS)-len(fails)} FAIL {len(fails)}")
    out = os.environ.get("QA_OUT")
    if out: json.dump(RESULTS, open(out, "w"), indent=1)
    if root is not None:
        try: root.destroy()
        except Exception: pass

def key(root, widget, seq):
    widget.focus_force(); pump(root, 2)
    widget.event_generate(seq); pump(root, 3)
