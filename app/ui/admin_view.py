import tkinter as tk
from tkinter import ttk, messagebox
from app.ui.components.data_table import DataTable
from app.services.admin_service import AdminService
from app.services.master_service import MasterService
from app.services.session_service import SessionService
from app.utils.currency import format_inr
from app.utils.formatters import format_date

class AdminView(ttk.Frame):
    """System Administration: Users, Roles, Company Profile, and Cashier Drawer Sessions."""
    def __init__(self, parent, db, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.current_user = current_user
        self.admin_svc = AdminService(db)
        self.master_svc = MasterService(db)
        self.session_svc = SessionService(db)

        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(header, text="System Administration & Cash Sessions", font=("Segoe UI", 16, "bold")).pack(side="left")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=6)

        # Tab 1: Cashier Sessions
        self.session_tab = ttk.Frame(notebook)
        notebook.add(self.session_tab, text="Cashier Drawer & Z-Report")
        self._build_session_tab()

        # Tab 2: Users Management
        self.users_tab = ttk.Frame(notebook)
        notebook.add(self.users_tab, text="Users & Access")
        self._build_users_tab()

        # Tab 3: Company Settings
        self.company_tab = ttk.Frame(notebook)
        notebook.add(self.company_tab, text="Company Profile & Mandi Defaults")
        self._build_company_tab()

        self.refresh()

    def refresh(self):
        self.load_session()
        self.load_users()
        self.load_company()

    # ---------------- CASHIER SESSIONS TAB ----------------
    def _build_session_tab(self):
        self.session_card = ttk.LabelFrame(self.session_tab, text="Active Drawer Session", padding=14)
        self.session_card.pack(fill="x", padx=10, pady=10)

        self.session_status_lbl = ttk.Label(self.session_card, text="Status: Checking...", font=("Segoe UI", 11, "bold"))
        self.session_status_lbl.pack(anchor="w", pady=4)

        self.session_info_lbl = ttk.Label(self.session_card, text="", font=("Segoe UI", 10))
        self.session_info_lbl.pack(anchor="w", pady=4)

        btn_row = ttk.Frame(self.session_card)
        btn_row.pack(fill="x", pady=(10, 0))
        self.open_sess_btn = ttk.Button(btn_row, text="Open Drawer Session", command=self._open_session_dialog)
        self.open_sess_btn.pack(side="left", padx=4)
        self.close_sess_btn = ttk.Button(btn_row, text="Close Session & Generate Z-Report", command=self._close_session_dialog)
        self.close_sess_btn.pack(side="left", padx=4)
        ttk.Button(btn_row, text="Refresh Status", command=self.load_session).pack(side="left", padx=4)

    def load_session(self):
        sess = self.session_svc.get_active_session(self.current_user.user_id)
        if sess:
            expected = self.session_svc.compute_expected_cash(sess["session_id"])
            self.active_session_id = sess["session_id"]
            self.session_status_lbl.config(text="Status: SESSION OPEN", foreground="#27ae60")
            self.session_info_lbl.config(
                text=f"Session ID: {sess['session_id']}  |  Opened: {format_date(sess['start_time'])}\n"
                     f"Opening Drawer Cash: {format_inr(sess['opening_cash'])}\n"
                     f"Current Expected Cash (Drawer + Sales + Receipts): {format_inr(expected)}"
            )
            self.open_sess_btn.config(state="disabled")
            self.close_sess_btn.config(state="normal")
        else:
            self.active_session_id = None
            self.session_status_lbl.config(text="Status: NO ACTIVE SESSION (DRAWER CLOSED)", foreground="#7f8c8d")
            self.session_info_lbl.config(text="Open a drawer session to track cash payments and reconciliations.")
            self.open_sess_btn.config(state="normal")
            self.close_sess_btn.config(state="disabled")

    def _open_session_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Open Cashier Drawer")
        dlg.geometry("380x180")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Opening Float / Cash in Drawer (₹):").pack(padx=12, pady=(16, 6))
        cash_ent = ttk.Entry(dlg, width=20, font=("Segoe UI", 11))
        cash_ent.insert(0, "1000.0")
        cash_ent.pack(padx=12, pady=6)

        def on_open():
            try:
                val = float(cash_ent.get().strip())
                self.session_svc.open_session(
                    user_id=self.current_user.user_id,
                    username=self.current_user.username,
                    opening_cash=val
                )
                messagebox.showinfo("Session Opened", f"Drawer opened with {format_inr(val)} float.")
                dlg.destroy()
                self.load_session()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ttk.Button(dlg, text="Start Session", command=on_open).pack(pady=12)

    def _close_session_dialog(self):
        if not getattr(self, "active_session_id", None):
            return

        dlg = tk.Toplevel(self)
        dlg.title("Close Cashier Session & Z-Report")
        dlg.geometry("400x220")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Counted Actual Cash in Drawer (₹):").pack(padx=12, pady=(16, 6))
        count_ent = ttk.Entry(dlg, width=20, font=("Segoe UI", 11))
        count_ent.pack(padx=12, pady=6)

        ttk.Label(dlg, text="Closing Notes / Variance Reason:").pack(padx=12, pady=(8, 4))
        notes_ent = ttk.Entry(dlg, width=30)
        notes_ent.pack(padx=12, pady=4)

        def on_close():
            try:
                counted = float(count_ent.get().strip())
                notes = notes_ent.get().strip()
                res = self.session_svc.close_session(self.active_session_id, counted, notes)
                diff = res["difference"]
                var_str = "BALANCED" if abs(diff) < 0.01 else (f"SHORT by {format_inr(abs(diff))}" if diff < 0 else f"EXCESS by {format_inr(diff)}")
                z_rep = (
                    f"=== CASHIER Z-REPORT ===\n\n"
                    f"Cashier: {res['username']}\n"
                    f"Opening Cash:   {format_inr(res['opening_cash'])}\n"
                    f"Expected Cash:  {format_inr(res['expected_cash'])}\n"
                    f"Actual Counted: {format_inr(res['actual_cash'])}\n"
                    f"---------------------------------\n"
                    f"Variance Result: {var_str}\n"
                )
                messagebox.showinfo("Z-Report", z_rep)
                dlg.destroy()
                self.load_session()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ttk.Button(dlg, text="Close Drawer & Generate Report", command=on_close).pack(pady=12)

    # ---------------- USERS TAB ----------------
    def _build_users_tab(self):
        bar = ttk.Frame(self.users_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="+ Add Operator User", command=self._add_user_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh Users", command=self.load_users).pack(side="left", padx=4)

        cols = [
            ("user_id", "User ID", 110),
            ("username", "Login Username", 180),
            ("roles", "Assigned Roles", 200),
            ("email", "Email", 180),
            ("phone", "Phone", 130),
            ("status", "Status", 90),
        ]
        self.users_table = DataTable(self.users_tab, columns=cols)
        self.users_table.pack(fill="both", expand=True)

    def load_users(self):
        users = self.admin_svc.get_users()
        formatted = []
        for u in users:
            d = dict(u)
            d["roles"] = ", ".join(d.get("roles", []))
            formatted.append(d)
        self.users_table.set_data(formatted)

    def _add_user_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add New Application User")
        dlg.geometry("400x320")
        dlg.transient(self)
        dlg.grab_set()

        entries = {}
        fields = [
            ("Username *", "username", ""),
            ("Password *", "password", ""),
            ("Role (Admin / Manager / User / Accountant)", "role", "User"),
            ("Email", "email", ""),
            ("Phone", "phone", ""),
        ]

        for idx, (label, key, val) in enumerate(fields):
            ttk.Label(dlg, text=label).grid(row=idx, column=0, padx=12, pady=6, sticky="w")
            ent = ttk.Entry(dlg, width=24, show="*" if key == "password" else "")
            ent.insert(0, val)
            ent.grid(row=idx, column=1, padx=12, pady=6, sticky="ew")
            entries[key] = ent

        def on_save():
            try:
                uname = entries["username"].get().strip()
                pword = entries["password"].get().strip()
                role = entries["role"].get().strip()
                email = entries["email"].get().strip()
                phone = entries["phone"].get().strip()
                self.admin_svc.create_user(uname, pword, roles=[role], email=email, phone=phone)
                messagebox.showinfo("Success", f"User '{uname}' created successfully!")
                self.load_users()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        btn_box = ttk.Frame(dlg)
        btn_box.grid(row=len(fields), column=0, columnspan=2, pady=16)
        ttk.Button(btn_box, text="Create User", command=on_save).pack(side="left", padx=8)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)

    # ---------------- COMPANY TAB ----------------
    def _build_company_tab(self):
        frame = ttk.LabelFrame(self.company_tab, text="Company Profile & Invoicing Details", padding=14)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.comp_entries = {}
        fields = [
            ("Legal Business Name", "name"),
            ("Market / Yard Address", "address"),
            ("Phone Number", "phone"),
            ("Contact Email", "email"),
            ("GSTIN Number", "gst_number"),
            ("Terms & Conditions (On Invoice)", "terms_and_conditions"),
            ("Signatory Title", "signatory_label"),
        ]

        for idx, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=idx, column=0, padx=12, pady=6, sticky="w")
            ent = ttk.Entry(frame, width=44)
            ent.grid(row=idx, column=1, padx=12, pady=6, sticky="w")
            self.comp_entries[key] = ent

        save_btn = ttk.Button(frame, text="Save Company Profile", command=self._save_company)
        save_btn.grid(row=len(fields), column=1, padx=12, pady=16, sticky="w")

    def load_company(self):
        comp = self.master_svc.get_company()
        for k, ent in self.comp_entries.items():
            ent.delete(0, "end")
            ent.insert(0, str(comp.get(k, "")))

    def _save_company(self):
        try:
            data = {k: ent.get().strip() for k, ent in self.comp_entries.items()}
            self.master_svc.save_company(data)
            messagebox.showinfo("Saved", "Company profile updated successfully!")
        except Exception as ex:
            messagebox.showerror("Error", str(ex))
