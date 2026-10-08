from qa_gui_common import *
from datetime import datetime
import tkinter as tk

# ------------------------------------------------------------ LOGIN WINDOW
db0 = MongoDatabase(settings); db0.connect(); auth0 = AuthService(db0)
r0 = tk.Tk(); r0.withdraw()
from app.ui.login_window import LoginWindow
lw = LoginWindow(r0, auth0); pump(r0)
check("GUI-LOGIN-01", "login form pre-fills a username/password", bool(lw.username_entry.get()) or bool(lw.password_entry.get()),
      f"username prefilled={lw.username_entry.get()!r}, password chars prefilled={len(lw.password_entry.get())}")
lw.username_entry.delete(0, tk.END); lw.password_entry.delete(0, tk.END); clear_dialogs(); lw._login()
check("GUI-LOGIN-02", "blank credentials -> warning, no login", last_dialog() and last_dialog()[0]=="showwarning" and lw.current_user is None, last_dialog())
lw.username_entry.insert(0, "admin"); lw.password_entry.insert(0, "wrongpw"); clear_dialogs(); lw._login()
check("GUI-LOGIN-03", "wrong password -> 'Sign In Failed' error, window stays", last_dialog() and last_dialog()[0]=="showerror" and lw.current_user is None and lw.winfo_exists(), last_dialog())
lw.password_entry.delete(0, tk.END); lw.password_entry.insert(0, "admin123"); lw._login()
check("GUI-LOGIN-04", "correct password -> CurrentUser set and window closed", lw.current_user is not None and lw.current_user.username=="admin")
lw2 = LoginWindow(r0, auth0); pump(r0)
lw2.username_entry.delete(0, tk.END); lw2.username_entry.insert(0, "' || 1==1 || '"); lw2.password_entry.delete(0, tk.END); lw2.password_entry.insert(0, "x"); clear_dialogs(); lw2._login()
check("GUI-LOGIN-05", "injection-style username rejected", lw2.current_user is None, last_dialog())
lw2.username_entry.delete(0, tk.END); lw2.username_entry.insert(0, "{'$ne': ''}"); lw2._login()
check("GUI-LOGIN-06", "operator-string username rejected", lw2.current_user is None)
lw2.destroy(); r0.destroy(); db0.close()

# ------------------------------------------------------------ MAIN WINDOW (admin)
root, db, auth, billing, user, win = boot()
check("GUI-NAV-01", "MainWindow builds for admin", win is not None)
pages = ["Dashboard","New Bill","Bill History","Item Master","Customer Master","Supplier Master","Fixed Rates","New Order","Orders","Order Matrix",
         "Inventory","Waste Management","Procurement","Finance","Trial Balance","Profit & Loss","Balance Sheet","BRS","Accounts Receivables","Accounts Payables",
         "Administration","Handover & Settlement","User Management","Company Settings","System Audit Logs","Consolidated Billing","DB Connection"]
bad = []
for p in pages:
    try: win.show_page(p); pump(root, 3)
    except Exception as e: bad.append((p, repr(e)))
    if win.active_page != p: bad.append((p, f"active_page={win.active_page}"))
check("GUI-NAV-02", f"all {len(pages)} navigable pages open without exception", not bad, bad)
menus = win._build_menu_structure()
check("GUI-NAV-03", "admin sees File/Masters/Reports/Accounts/Settings menus", set(menus) >= {"File","Masters","Reports","Accounts","Settings"}, list(menus))
win.show_page("Dashboard"); shot(root, "admin_dashboard")
# F-key shortcuts
for key, expect in [("<F1>","Dashboard"),("<F4>","Customer Master"),("<F10>","Item Master"),("<Control-o>","Orders"),("<Control-p>","Procurement"),("<Control-d>","Finance")]:
    root.event_generate(key); pump(root, 3)
    check(f"GUI-KEY-{key.strip('<>')}", f"{key} navigates to {expect}", win.active_page == expect, win.active_page)
root.event_generate("<F2>"); pump(root,3); check("GUI-KEY-F2", "F2 opens New Bill", win.active_page=="New Bill", win.active_page)
root.event_generate("<F6>"); pump(root,3)
check("GUI-KEY-F6", "F6 from New Bill = Park Bill (empty bill -> no-op), stays on New Bill", win.active_page=="New Bill", win.active_page)
root.destroy(); db.close()

# ------------------------------------------------------------ RBAC: manager & user
# Policy (seeded role_permissions): manager = masters + finance, no settings; user = none of them.
POLICY = {"manager": {"menus_hidden": {"Settings"}, "menus_shown": {"Masters", "Accounts"}, "open": {"<F10>": "Item Master", "<F11>": "Customer Master", "<Control-d>": "Finance"}},
          "user": {"menus_hidden": {"Masters", "Accounts", "Settings"}, "menus_shown": set(), "open": {}}}
for uname, pw in [("manager", "manager123"), ("user", "user123")]:
    root, db, auth, billing, u, win = boot(uname, pw)
    pol = POLICY[uname]
    menus = win._build_menu_structure()
    check(f"GUI-RBAC-{uname}-01", f"{uname}: menus hidden {sorted(pol['menus_hidden'])} / shown {sorted(pol['menus_shown'])}", not (set(menus) & pol["menus_hidden"]) and pol["menus_shown"] <= set(menus), list(menus))
    reports = [m[1] for m in menus.get("Reports", [])]
    want_fin = uname == "manager"
    check(f"GUI-RBAC-{uname}-02", f"{uname}: Profit & Loss / Balance Sheet in Reports menu only if finance access ({want_fin})", ({"Profit & Loss", "Balance Sheet"} <= set(reports)) == want_fin, reports)
    for key, page in [("<F10>", "Item Master"), ("<F11>", "Customer Master"), ("<Control-d>", "Finance")]:
        win.show_page("Dashboard"); root.event_generate(key); pump(root, 3)
        allowed = key in pol["open"]
        check(f"GUI-RBAC-{uname}-{key.strip('<>')}", f"{uname}: {key} -> {page} is {'allowed' if allowed else 'blocked'}", (win.active_page == page) == allowed, f"active_page={win.active_page}")
    win.show_page("User Management")
    check(f"GUI-RBAC-{uname}-settings", f"{uname}: User Management blocked", win.active_page != "User Management", win.active_page)
    shot(root, f"{uname}_menu")
    root.destroy(); db.close()
finish()
