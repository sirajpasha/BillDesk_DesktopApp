import logging
import tkinter as tk
from app.utils import validation as V
from tkinter import ttk, messagebox
from app.ui.components.data_table import DataTable
from app.ui.financial_report_window import FinancialReportWindow
from app.services.payment_service import PaymentService
from app.services.ledger_service import LedgerService
from app.services.banking_service import BankingService
from app.utils.currency import format_inr
from app.ui import theme

class FinanceView(tk.Frame):
    """
    Financial Management View matching:
    - 25-accounting-home.png (Accounting Dashboard with 4 KPI cards and 6 quick-action cards)
    - 32-receivables-invoices.png & 34-receivables-aging.png (AR Sub-ledger)
    - 35-payables-bills.png (AP Sub-ledger)
    - 38-brs-start.png (Bank Reconciliation)
    - 26-trial-balance.png & 27-profit-loss.png (General Ledger Reports)
    """
    def __init__(self, parent, db, current_user, **kwargs):
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.db = db
        self.current_user = current_user
        self.pay_svc = PaymentService(db)
        self.ledger_svc = LedgerService(db)
        self.bank_svc = BankingService(db)

        # Style notebook
        style = ttk.Style()
        style.configure("Finance.TNotebook", background=theme.BG)
        style.configure("Finance.TNotebook.Tab", font=theme.F_BOLD, padding=[14, 6])

        self.notebook = ttk.Notebook(self, style="Finance.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(12, 16))

        # Tab 0: Accounting Dashboard (Matches 25-accounting-home.png)
        self.home_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.home_tab, text="Accounting Home")
        self._build_home_tab()

        # Tab 1: AR Aging & Receipts
        self.ar_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.ar_tab, text="Accounts Receivable (AR)")
        self._build_ar_tab()

        # Tab 2: AP Disbursements
        self.ap_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.ap_tab, text="Accounts Payable (AP)")
        self._build_ap_tab()

        # Tab 3: Banking & BRS
        self.bank_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.bank_tab, text="Banking & BRS")
        self._build_bank_tab()

        # Tab 4: General Ledger & Reports
        self.gl_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.gl_tab, text="General Ledger")
        self._build_gl_tab()

        self.refresh()

    def refresh(self):
        self.load_home_kpis()
        self.load_ar()
        self.load_ap()
        self.load_bank()
        self.load_gl()

    # =========================================================================
    # 0. ACCOUNTING HOME (Matches 25-accounting-home.png)
    # =========================================================================
    def _build_home_tab(self):
        top_bar = tk.Frame(self.home_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=14, pady=(16, 12))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Accounting Dashboard", font=("Segoe UI", 18, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")
        tk.Label(title_box, text="Real-time financial status and reporting", font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.BG).pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Set Opening Balance",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._post_journal_dialog
        ).pack(side="right")

        # 4 KPI Cards: Total Receivables (Purple), Total Payables (Red), Bank Balance (Green), Net Profit (YTD) (Indigo)
        kpi_row = tk.Frame(self.home_tab, bg=theme.BG)
        kpi_row.pack(fill="x", padx=14, pady=(0, 16))

        self.kpi_home_ar, _ = self._make_card(kpi_row, "₹ 0.00", "Total Receivables", "#5046e5")
        self.kpi_home_ap, _ = self._make_card(kpi_row, "₹ 0.00", "Total Payables", theme.DANGER)
        self.kpi_home_bank, _ = self._make_card(kpi_row, "₹ 0.00", "Bank Balance", theme.SUCCESS)
        self.kpi_home_profit, _ = self._make_card(kpi_row, "₹ 0.00", "Net Profit (YTD)", theme.PRIMARY)

        # 6 Action Cards in 2 rows of 3 (Matching 25-accounting-home.png)
        grid_container = tk.Frame(self.home_tab, bg=theme.SURFACE, bd=1, relief="solid", padx=20, pady=20)
        grid_container.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # Row 1
        r1 = tk.Frame(grid_container, bg=theme.SURFACE)
        r1.pack(fill="x", pady=(0, 16))

        # 1. BRS
        self._make_action_card(
            r1,
            icon="🏦",
            title="Bank Reconciliation (BRS)",
            desc="Upload statements and auto-match transactions with scoring logic.",
            btn_text="Open BRS",
            command=lambda: self.notebook.select(self.bank_tab)
        )
        # 2. AR
        self._make_action_card(
            r1,
            icon="👥",
            title="Accounts Receivable",
            desc="Manage customer sub-ledgers, aging, and adjustments.",
            btn_text="Open AR Dashboard",
            command=lambda: self.notebook.select(self.ar_tab)
        )
        # 3. AP
        self._make_action_card(
            r1,
            icon="🏢",
            title="Accounts Payable",
            desc="Manage vendor sub-ledgers and 3-way match bills.",
            btn_text="Open AP Dashboard",
            command=lambda: self.notebook.select(self.ap_tab)
        )

        # Row 2
        r2 = tk.Frame(grid_container, bg=theme.SURFACE)
        r2.pack(fill="x")

        # 4. Profit & Loss
        self._make_action_card(
            r2,
            icon="📊",
            title="Profit & Loss",
            desc="Detailed analysis of income and operating expenses.",
            btn_text="View P&L",
            command=self._view_pl
        )
        # 5. Balance Sheet
        self._make_action_card(
            r2,
            icon="⚖",
            title="Balance Sheet",
            desc="Statement of financial position and equity status.",
            btn_text="View Balance Sheet",
            command=self._view_balance_sheet
        )
        # 6. Trial Balance
        self._make_action_card(
            r2,
            icon="📑",
            title="Trial Balance",
            desc="Consolidated ledger balances with audit drill-down.",
            btn_text="View Trial Balance",
            command=self._view_trial_balance
        )

    def _make_action_card(self, parent, icon: str, title: str, desc: str, btn_text: str, command):
        card = tk.Frame(parent, bg=theme.SURFACE, bd=1, relief="solid", padx=16, pady=16)
        card.pack(side="left", fill="both", expand=True, padx=8)

        tk.Label(card, text=icon, font=("Segoe UI", 16), bg=theme.SURFACE, fg=theme.PRIMARY).pack(anchor="w")
        tk.Label(card, text=title, font=theme.F_H11B, fg=theme.TEXT, bg=theme.SURFACE).pack(anchor="w", pady=(6, 2))
        tk.Label(card, text=desc, font=theme.F_SMALL, fg=theme.TEXT_MUTED, bg=theme.SURFACE, wraplength=220, justify="left").pack(anchor="w", pady=(0, 14))

        tk.Button(
            card,
            text=btn_text,
            font=theme.F_BOLD,
            bg=theme.BG,
            fg=theme.SLATE_700,
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            cursor="hand2",
            command=command
        ).pack(fill="x")

    def load_home_kpis(self):
        try:
            ar_data = self.pay_svc.get_ar_aging()
            total_ar = ar_data.get("summary", {}).get("total", 0.0)
            self.kpi_home_ar.config(text=format_inr(total_ar))
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

        try:
            pl = self.ledger_svc.get_profit_and_loss()
            self.kpi_home_profit.config(text=format_inr(pl.get("net_profit", 0.0)))
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

        try:
            accs = self.bank_svc.get_bank_accounts()
            tot_bank = sum(a.get("current_balance", 0.0) for a in accs)
            self.kpi_home_bank.config(text=format_inr(tot_bank))
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

        try:
            # Payables count from purchases
            purchases = list(self.db.collection("purchase_bills").find({"balance_due": {"$gt": 0}, "is_deleted": 0}))
            tot_ap = sum(p.get("balance_due", 0.0) for p in purchases)
            self.kpi_home_ap.config(text=format_inr(tot_ap))
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

    # =========================================================================
    # 1. AR AGING & RECEIPTS TAB
    # =========================================================================
    def _build_ar_tab(self):
        top_bar = tk.Frame(self.ar_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Accounts Receivable (AR Aging)", font=("Segoe UI", 16, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Record Customer Receipt",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._record_payment_dialog
        ).pack(side="right")
        tk.Button(
            top_bar, text="Customer Statement", font=theme.F_BOLD, bg=theme.SURFACE, fg=theme.SLATE_700,
            relief="solid", bd=1, padx=12, pady=4, cursor="hand2", command=self._open_statement
        ).pack(side="right", padx=(0, 8))

        card = tk.Frame(self.ar_tab, bg=theme.SURFACE, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.ar_summary_label = tk.Label(card, font=theme.F_BOLD, fg=theme.TEXT_STRONG, bg=theme.SURFACE, padx=16, pady=10)
        self.ar_summary_label.pack(anchor="w")

        cols = [
            ("customer_name", "Customer Name", 240),
            ("current", "Current (₹)", 120),
            ("1_30", "1-30 Days (₹)", 120),
            ("31_60", "31-60 Days (₹)", 120),
            ("61_90", "61-90 Days (₹)", 120),
            ("90_plus", "90+ Overdue (₹)", 130),
            ("total", "Total Outstanding (₹)", 150),
        ]
        self.ar_table = DataTable(card, columns=cols, empty_text="Nobody owes anything right now.")
        self.ar_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _open_statement(self):
        row = self.ar_table.get_selected()
        if not row or not row.get("customer_id"):
            messagebox.showinfo("Select Customer", "Select a customer in the list first.", parent=self)
            return
        from app.ui.statement_view import StatementWindow
        StatementWindow(self, self.db, row["customer_id"], row.get("customer_name", ""))

    def load_ar(self):
        res = self.pay_svc.get_ar_aging()
        summary = res.get("summary", {})
        self.ar_summary_label.config(
            text=f"Total AR Outstanding: {format_inr(summary.get('total', 0.0))}   |   "
                 f"Current: {format_inr(summary.get('current', 0.0))}   |   "
                 f"1-30 Days: {format_inr(summary.get('1_30', 0.0))}   |   "
                 f"90+ Overdue: {format_inr(summary.get('90_plus', 0.0))}   |   "
                 f"Advances held (not counted): {format_inr(summary.get('advances', 0.0))}"
        )
        formatted = []
        for c in res.get("customers", []):
            d = dict(c)
            for k in ["current", "1_30", "31_60", "61_90", "90_plus", "total"]:
                d[k] = format_inr(d.get(k, 0.0), symbol=False)
            formatted.append(d)
        self.ar_table.set_data(formatted)

    def _record_payment_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Record Customer Receipt (AR)")
        dlg.geometry("460x360")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=theme.SURFACE)

        hdr = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Record Customer Payment Receipt", font=theme.F_H12B, fg=theme.SURFACE, bg=theme.PRIMARY).pack(anchor="w")

        body = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        entries = {}
        fields = [
            ("Customer ID *", "customer_id", ""),
            ("Payment Amount (₹) *", "amount", ""),
            ("Payment Mode", "payment_method", "Cash"),
            ("Invoice No (Leave blank for FIFO)", "invoice_no", ""),
            ("UTR / Cheque Ref No", "reference_no", ""),
            ("Notes", "notes", ""),
        ]

        for idx, (label, key, val) in enumerate(fields):
            tk.Label(body, text=label, font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=idx, column=0, padx=6, pady=4, sticky="w")
            if key == "payment_method":
                ent = ttk.Combobox(body, values=list(PaymentService.PAY_METHODS[:-1]), state="readonly", width=26)
                ent.set(val)
            else:
                ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=28)
                ent.insert(0, val)
            ent.grid(row=idx, column=1, padx=6, pady=4, sticky="ew")
            entries[key] = ent

        def on_save():
            try:
                c_id = entries["customer_id"].get().strip()
                amt = V.number(entries["amount"].get(), "Payment amount", greater_than=0, maximum=100_000_000)
                mode = entries["payment_method"].get().strip()
                inv_no = entries["invoice_no"].get().strip() or None
                ref = entries["reference_no"].get().strip() or None
                notes = entries["notes"].get().strip()
                if not c_id:
                    messagebox.showwarning("Required", "Customer ID is required", parent=dlg)
                    return
                res = self.pay_svc.record_customer_payment(
                    customer_id=c_id,
                    amount=amt,
                    payment_method=mode,
                    invoice_no=inv_no,
                    reference_no=ref,
                    notes=notes,
                    user_id=self.current_user.username
                )
                messagebox.showinfo("Payment Saved", f"Receipt {res['payment_id']} recorded!\nCustomer balance updated.", parent=dlg)
                self.load_ar()
                self.load_home_kpis()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=10)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Save Receipt", font=theme.F_BOLD, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=14, pady=5, command=on_save).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=theme.F_BODY, bg=theme.HEADING_BG, fg=theme.SLATE_600, relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    # =========================================================================
    # 2. AP DISBURSEMENTS TAB
    # =========================================================================
    def _build_ap_tab(self):
        top_bar = tk.Frame(self.ap_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Accounts Payable (AP)", font=("Segoe UI", 16, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Disburse Supplier Payment",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._supplier_payment_dialog
        ).pack(side="right")

        card = tk.Frame(self.ap_tab, bg=theme.SURFACE, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cols = [
            ("purchase_id", "Purchase ID", 140),
            ("supplier_name", "Supplier Name", 220),
            ("payable_amount", "Net Payable (₹)", 130),
            ("balance_due", "Balance Due (₹)", 130),
            ("status", "Status", 90),
        ]
        self.ap_table = DataTable(card, columns=cols, empty_text="No vendor bills yet.")
        self.ap_table.pack(fill="both", expand=True, padx=12, pady=12)

    def load_ap(self):
        purchases = list(self.db.collection("purchase_bills").find({"is_deleted": 0}).sort("bill_date", -1).limit(200))
        formatted = []
        for p in purchases:
            d = dict(p)
            due = float(d.get("balance_due", 0.0) or 0.0)
            paid = due <= 0.005
            d["status"] = "paid" if paid else ("partial" if due < float(d.get("payable_amount", 0.0) or 0.0) - 0.005 else "unpaid")
            d["payable_amount"] = format_inr(d.get("payable_amount", 0.0), symbol=False)
            d["balance_due"] = format_inr(d.get("balance_due", 0.0), symbol=False)
            formatted.append(d)
        self.ap_table.set_data(formatted)

    def _supplier_payment_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Supplier Payment Disbursement (AP)")
        dlg.geometry("450x320")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=theme.SURFACE)

        hdr = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Disburse Supplier Payment", font=theme.F_H12B, fg=theme.SURFACE, bg=theme.PRIMARY).pack(anchor="w")

        body = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        entries = {}
        fields = [
            ("Purchase ID *", "purchase_id", ""),
            ("Supplier ID *", "supplier_id", ""),
            ("Payment Amount (₹) *", "amount", ""),
            ("Payment Mode", "payment_method", "NEFT"),
            ("Reference / UTR", "reference_no", ""),
        ]

        for idx, (label, key, val) in enumerate(fields):
            tk.Label(body, text=label, font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=idx, column=0, padx=6, pady=4, sticky="w")
            if key == "payment_method":
                ent = ttk.Combobox(body, values=list(PaymentService.PAY_METHODS[:-1]), state="readonly", width=24)
                ent.set(val)
            else:
                ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=26)
                ent.insert(0, val)
            ent.grid(row=idx, column=1, padx=6, pady=4, sticky="ew")
            entries[key] = ent

        def on_pay():
            try:
                p_id = entries["purchase_id"].get().strip()
                s_id = entries["supplier_id"].get().strip()
                if not p_id or not s_id:
                    raise ValueError("Purchase ID and Supplier ID are required.")
                amt = V.number(entries["amount"].get(), "Payment amount", greater_than=0, maximum=100_000_000)
                mode = entries["payment_method"].get().strip()
                ref = entries["reference_no"].get().strip() or None
                res = self.pay_svc.record_supplier_payment(p_id, s_id, amt, mode, ref, user_id=self.current_user.username)
                messagebox.showinfo("Success", f"Payment {res['payment_id']} recorded to supplier.", parent=dlg)
                self.load_ap()
                self.load_home_kpis()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=10)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Disburse Payment", font=theme.F_BOLD, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=14, pady=5, command=on_pay).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=theme.F_BODY, bg=theme.HEADING_BG, fg=theme.SLATE_600, relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    # =========================================================================
    # 3. BANKING & BRS TAB
    # =========================================================================
    def _build_bank_tab(self):
        top_bar = tk.Frame(self.bank_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Banking & Bank Reconciliation (BRS)", font=("Segoe UI", 16, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")

        btn_box = tk.Frame(top_bar, bg=theme.BG)
        btn_box.pack(side="right")

        tk.Button(btn_box, text="+ Add Bank Account", font=theme.F_LABEL, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=10, pady=4, command=self._add_bank_dialog).pack(side="left", padx=4)
        tk.Button(btn_box, text="⚡ Auto-Reconciliation", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=4, command=self._auto_reconcile).pack(side="left", padx=4)
        tk.Button(btn_box, text="📄 View BRS Statement", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=4, command=self._view_brs).pack(side="left", padx=4)

        card = tk.Frame(self.bank_tab, bg=theme.SURFACE, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cols = [
            ("account_id", "Account ID", 120),
            ("bank_name", "Bank Name", 220),
            ("account_number", "Account Number", 180),
            ("account_type", "Account Type", 120),
            ("current_balance", "Book Balance (₹)", 150),
            ("status", "Status", 90),
        ]
        self.bank_table = DataTable(card, columns=cols)
        self.bank_table.pack(fill="both", expand=True, padx=12, pady=12)

    def load_bank(self):
        accs = self.bank_svc.get_bank_accounts()
        formatted = []
        for a in accs:
            d = dict(a)
            d["current_balance"] = format_inr(d.get("current_balance", 0.0), symbol=False)
            formatted.append(d)
        self.bank_table.set_data(formatted)

    def _add_bank_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Bank Account")
        dlg.geometry("400x280")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=theme.SURFACE)

        hdr = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Add New Bank Account", font=theme.F_H11B, fg=theme.SURFACE, bg=theme.PRIMARY).pack(anchor="w")

        body = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        entries = {}
        fields = [
            ("Bank Name *", "bank_name", ""),
            ("Account Number *", "account_number", ""),
            ("IFSC (optional)", "ifsc", ""),
            ("Account Type", "account_type", "Current"),
            ("Opening Balance", "current_balance", "0.0"),
        ]

        for idx, (label, key, val) in enumerate(fields):
            tk.Label(body, text=label, font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=idx, column=0, padx=6, pady=4, sticky="w")
            if key == "account_type":
                ent = ttk.Combobox(body, values=["Current", "Savings", "OD"], state="readonly", width=20)
                ent.set(val)
            else:
                ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
                ent.insert(0, val)
            ent.grid(row=idx, column=1, padx=6, pady=4, sticky="ew")
            entries[key] = ent

        def on_save():
            try:
                bal = V.number(entries["current_balance"].get(), "Opening balance", minimum=-1_000_000_000, maximum=1_000_000_000, required=False, default=0.0)
                self.bank_svc.save_bank_account({"bank_name": entries["bank_name"].get(), "account_number": entries["account_number"].get(),
                                                 "ifsc": entries["ifsc"].get(), "account_type": entries["account_type"].get(), "current_balance": bal})
                self.load_bank()
                self.load_home_kpis()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=10)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Save Bank", font=theme.F_BOLD, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=14, pady=5, command=on_save).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=theme.F_BODY, bg=theme.HEADING_BG, fg=theme.SLATE_600, relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    def _auto_reconcile(self):
        sel = self.bank_table.get_selected()
        if not sel:
            messagebox.showinfo("Select Account", "Please select a bank account to reconcile", parent=self)
            return
        res = self.bank_svc.auto_reconcile(sel["account_id"])
        messagebox.showinfo("Reconciliation Result", f"Auto-matched {res['matched_count']} entries against statement lines.", parent=self)

    def _view_brs(self):
        sel = self.bank_table.get_selected()
        if not sel:
            messagebox.showinfo("Select Account", "Please select a bank account to view BRS", parent=self)
            return
        brs = self.bank_svc.get_brs_report(sel["account_id"])
        msg = (
            f"=== Bank Reconciliation Statement ===\n\n"
            f"Book Balance: {format_inr(brs['book_balance'])}\n"
            f"+ Unpresented Cheques (Payments): {format_inr(brs['unreconciled_payments'])}\n"
            f"- Uncleared Deposits (Receipts): {format_inr(brs['unreconciled_receipts'])}\n"
            f"-----------------------------------------\n"
            f"Calculated Bank Balance: {format_inr(brs['calculated_bank_balance'])}\n"
        )
        messagebox.showinfo("BRS Report", msg, parent=self)

    # =========================================================================
    # 4. GENERAL LEDGER TAB
    # =========================================================================
    def _build_gl_tab(self):
        top_bar = tk.Frame(self.gl_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="General Ledger & Chart of Accounts", font=("Segoe UI", 16, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")

        btn_box = tk.Frame(top_bar, bg=theme.BG)
        btn_box.pack(side="right")

        tk.Button(btn_box, text="+ Post Manual Journal", font=theme.F_LABEL, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=10, pady=4, command=self._post_journal_dialog).pack(side="left", padx=4)
        tk.Button(btn_box, text="Trial Balance", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=4, command=self._view_trial_balance).pack(side="left", padx=4)
        tk.Button(btn_box, text="Profit & Loss", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=4, command=self._view_pl).pack(side="left", padx=4)

        card = tk.Frame(self.gl_tab, bg=theme.SURFACE, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cols = [
            ("code", "GL Code", 100),
            ("name", "Account Title", 260),
            ("type", "Type", 120),
            ("root_type", "Classification", 130),
            ("is_bs_account", "Balance Sheet", 110),
            ("is_pl_account", "P&L Account", 110),
        ]
        self.gl_table = DataTable(card, columns=cols)
        self.gl_table.pack(fill="both", expand=True, padx=12, pady=12)

    def load_gl(self):
        accs = self.ledger_svc.get_accounts()
        self.gl_table.set_data(accs)

    # ---------------- Financial statements (rendered from the general ledger) ----------------
    @staticmethod
    def _fmt(v: float) -> str:
        return format_inr(v, symbol=False)

    @staticmethod
    def _period_line(date_from=None, date_to=None, as_of_word: str = "") -> str:
        f = date_from.strftime("%d/%m/%Y") if date_from else ""
        t = date_to.strftime("%d/%m/%Y") if date_to else ""
        if as_of_word:
            return f"As of {t}" if t else "All entries to date"
        if f and t:
            return f"For the period {f} to {t}"
        return f"From {f} to date" if f else (f"Up to {t}" if t else "All entries to date")

    def trial_balance_text(self, date_to=None) -> str:
        """Every account's net debit / credit position up to a day (blank = all entries)."""
        tb = self.ledger_svc.get_trial_balance(date_to=date_to)
        w = 70
        out = ["TRIAL BALANCE", self._period_line(date_to=date_to, as_of_word="as of"), "=" * w, f"{'Code':<6}{'Account':<36}{'Debit':>14}{'Credit':>14}", "-" * w]
        for r in tb["rows"]:
            out.append(f"{r['account_code']:<6}{r['account_name'][:35]:<36}"
                       f"{self._fmt(r['debit']) if r['debit'] else '':>14}{self._fmt(r['credit']) if r['credit'] else '':>14}")
        if not tb["rows"]:
            out.append("(no postings yet)")
        out += ["-" * w, f"{'TOTAL':<42}{self._fmt(tb['total_debit']):>14}{self._fmt(tb['total_credit']):>14}",
                "", "Debits equal credits: " + ("YES - ledger is balanced" if tb["is_balanced"] else "NO - LEDGER IS OUT OF BALANCE")]
        return "\n".join(out)

    def profit_and_loss_text(self, date_from=None, date_to=None) -> str:
        """Profit and loss of a period (blank = all entries)."""
        pl = self.ledger_svc.get_profit_and_loss(date_from, date_to)
        w = 60

        def row(label, val, bold=False):
            return f"{('' if not bold else '')}{label:<40}{self._fmt(val):>18}"

        out = ["PROFIT & LOSS STATEMENT", self._period_line(date_from, date_to), "=" * w,
               row("Sales revenue", pl["total_sales"]),
               row("Commission & fee income", pl["fee_income"])]
        if pl["other_income"]:
            out.append(row("Other income", pl["other_income"]))
        out += [row("Total revenue", pl["total_revenue"]), "",
                row("Less: Cost of goods sold", pl["cost_of_goods_sold"])]
        if pl["total_purchases"]:
            out.append(row("Less: Purchases expensed directly", pl["total_purchases"]))
        out += ["-" * w, row("GROSS PROFIT", pl["gross_profit"]), "",
                row("Less: Spoilage & waste", pl["total_waste"]),
                row("Less: Operating expenses", pl["operating_expenses"]),
                "=" * w, row("NET PROFIT / (LOSS)", pl["net_profit"])]
        return "\n".join(out)

    def balance_sheet_text(self, as_of=None) -> str:
        """What you own and owe on a day (blank = now)."""
        bs = self.ledger_svc.get_balance_sheet(as_of)
        w = 60
        out = ["BALANCE SHEET", self._period_line(date_to=as_of, as_of_word="as of"), "=" * w, "ASSETS"]
        out += [f"  {r['account_name']:<44}{self._fmt(r['amount']):>14}" for r in bs["assets"]] or ["  (none)"]
        out += [f"{'Total assets':<46}{self._fmt(bs['total_assets']):>14}", "", "LIABILITIES"]
        out += [f"  {r['account_name']:<44}{self._fmt(r['amount']):>14}" for r in bs["liabilities"]] or ["  (none)"]
        out += [f"{'Total liabilities':<46}{self._fmt(bs['total_liabilities']):>14}", "", "EQUITY"]
        out += [f"  {r['account_name']:<44}{self._fmt(r['amount']):>14}" for r in bs["equity"]]
        out += [f"{'Total equity':<46}{self._fmt(bs['total_equity']):>14}", "-" * w,
                f"{'Liabilities + Equity':<46}{self._fmt(bs['total_liabilities'] + bs['total_equity']):>14}", "",
                "Assets = Liabilities + Equity: " + ("YES - balance sheet balances" if bs["is_balanced"] else "NO - DOES NOT BALANCE")]
        return "\n".join(out)

    def _remember_report(self, title: str, text: str):
        self.last_report = (title, text)

    def _show_report(self, title: str, mode: str, render):
        """Open a statement window with its period / as-of date boxes (and calendars)."""
        win = FinancialReportWindow(self, title, mode, render, on_render=self._remember_report)
        self.report_window = win
        return win

    def _view_trial_balance(self):
        return self._show_report("Trial Balance", "as_of", lambda _lo, hi: self.trial_balance_text(hi))

    def _view_pl(self):
        return self._show_report("Profit & Loss", "range", lambda lo, hi: self.profit_and_loss_text(lo, hi))

    def _view_balance_sheet(self):
        return self._show_report("Balance Sheet", "as_of", lambda _lo, hi: self.balance_sheet_text(hi))

    def _post_journal_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Post Balanced Journal Entry")
        dlg.geometry("450x320")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=theme.SURFACE)

        hdr = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Post Balanced Double-Entry Journal", font=theme.F_H11B, fg=theme.SURFACE, bg=theme.PRIMARY).pack(anchor="w")

        body = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Reference (e.g. ADJ-001):", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=0, column=0, padx=6, pady=4, sticky="w")
        ref_ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
        ref_ent.grid(row=0, column=1, padx=6, pady=4)

        tk.Label(body, text="Debit Account Code:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=1, column=0, padx=6, pady=4, sticky="w")
        dr_acc = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
        dr_acc.insert(0, "1200")
        dr_acc.grid(row=1, column=1, padx=6, pady=4)

        tk.Label(body, text="Debit Amount (₹):", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=2, column=0, padx=6, pady=4, sticky="w")
        dr_amt = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
        dr_amt.grid(row=2, column=1, padx=6, pady=4)

        tk.Label(body, text="Credit Account Code:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=3, column=0, padx=6, pady=4, sticky="w")
        cr_acc = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
        cr_acc.insert(0, "4000")
        cr_acc.grid(row=3, column=1, padx=6, pady=4)

        tk.Label(body, text="Credit Amount (₹):", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=4, column=0, padx=6, pady=4, sticky="w")
        cr_amt = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1, width=22)
        cr_amt.grid(row=4, column=1, padx=6, pady=4)

        def on_post():
            try:
                ref = V.text(ref_ent.get(), "Reference", max_len=40)
                d_acc = V.text(dr_acc.get(), "Debit account code", max_len=10)
                c_acc = V.text(cr_acc.get(), "Credit account code", max_len=10)
                d_val = V.number(dr_amt.get(), "Debit amount", greater_than=0, maximum=1_000_000_000)
                c_val = V.number(cr_amt.get(), "Credit amount", greater_than=0, maximum=1_000_000_000)
                if d_acc == c_acc:
                    raise ValueError("The debit and credit accounts must be different.")
                if abs(d_val - c_val) > 0.005:
                    raise ValueError(f"The entry does not balance: debit {d_val:,.2f} but credit {c_val:,.2f}.")
                lines = [
                    {"account_id": d_acc, "debit": d_val, "credit": 0.0},
                    {"account_id": c_acc, "debit": 0.0, "credit": c_val},
                ]
                self.ledger_svc.post_journal_entry(ref, "manual", lines, user_id=self.current_user.username)
                messagebox.showinfo("Success", "Balanced journal entry posted successfully!", parent=dlg)
                self.load_gl()
                self.load_home_kpis()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=10)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Post Entry", font=theme.F_BOLD, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", bd=0, padx=14, pady=5, command=on_post).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=theme.F_BODY, bg=theme.HEADING_BG, fg=theme.SLATE_600, relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    # =========================================================================
    # Helpers
    # =========================================================================
    def _make_card(self, parent, initial_val: str, label_text: str, bg_color: str):
        card = tk.Frame(parent, bg=bg_color, padx=20, pady=16, bd=0)
        card.pack(side="left", fill="both", expand=True, padx=4)

        val_label = tk.Label(
            card,
            text=initial_val,
            font=("Segoe UI", 22, "bold"),
            fg=theme.SURFACE,
            bg=bg_color,
            anchor="w"
        )
        val_label.pack(fill="x")

        sub_label = tk.Label(
            card,
            text=label_text,
            font=theme.F_BODY,
            fg="#fee2e2" if bg_color == theme.DANGER else "#dcfce7" if bg_color == theme.SUCCESS else "#e0e7ff",
            bg=bg_color,
            anchor="w"
        )
        sub_label.pack(fill="x", pady=(2, 0))

        return val_label, card
