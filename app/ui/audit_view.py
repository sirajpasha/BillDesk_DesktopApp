"""System Audit Logs: what was done to bills (create, void, return...) and who signed in. Read-only; filter by date, action and words; export to CSV."""
from __future__ import annotations

import csv
import logging
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from app.services.audit_service import AuditService
from app.ui import theme
from app.ui.components.calendar_popup import attach_date_picker
from app.ui.components.data_table import DataTable
from app.utils.formatters import format_datetime

log = logging.getLogger(__name__)


class _Tab:
    """One audit list with its own filter bar."""

    def __init__(self, view, parent, fetch, actions, columns, empty_text):
        self.view, self.fetch, self.actions = view, fetch, actions
        bar = tk.Frame(parent, bg=theme.BG)
        bar.pack(fill="x", pady=(10, 8))
        tk.Label(bar, text="FROM", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
        self.from_ent = tk.Entry(bar, width=12, relief="solid", bd=1)
        self.from_ent.pack(side="left", padx=(6, 10), ipady=4)
        self.from_picker = attach_date_picker(self.from_ent, "%d/%m/%Y", button=True, on_selected=lambda _d: self.load(), label="The From date")
        tk.Label(bar, text="TO", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
        self.to_ent = tk.Entry(bar, width=12, relief="solid", bd=1)
        self.to_ent.pack(side="left", padx=(6, 10), ipady=4)
        self.to_picker = attach_date_picker(self.to_ent, "%d/%m/%Y", button=True, on_selected=lambda _d: self.load(), label="The To date",
                                            not_before=lambda: self.from_picker.value())
        tk.Label(bar, text="ACTION", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
        self.action_var = tk.StringVar(value="All")
        self.action_cb = ttk.Combobox(bar, textvariable=self.action_var, values=["All"], state="readonly", width=18)
        self.action_cb.pack(side="left", padx=(6, 10))
        self.action_cb.bind("<<ComboboxSelected>>", lambda _e: self.load())
        tk.Label(bar, text="SEARCH", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
        self.query_var = tk.StringVar()
        q = tk.Entry(bar, textvariable=self.query_var, width=22, relief="solid", bd=1)
        q.pack(side="left", padx=(6, 10), ipady=4)
        q.bind("<Return>", lambda _e: self.load())
        theme.primary_button(bar, "Show", self.load).pack(side="left")
        theme.secondary_button(bar, "Export CSV", self.export).pack(side="right")
        self.table = DataTable(parent, columns=columns, empty_text=empty_text, show_search=False)
        self.table.pack(fill="both", expand=True)
        self.count = tk.Label(parent, text="", font=theme.F_BOLD, fg=theme.TEXT, bg=theme.BG, anchor="w")
        self.count.pack(fill="x", pady=(6, 0))
        self.rows = []
        self.keys = [c[0] for c in columns]
        self.headings = [c[1] for c in columns]

    def load(self):
        for picker, entry in ((self.from_picker, self.from_ent), (self.to_picker, self.to_ent)):
            problem = picker.error()
            if problem:
                messagebox.showwarning("Date", problem, parent=self.view)
                entry.focus_set()
                return
        lo = datetime.combine(self.from_picker.value(), datetime.min.time()) if self.from_picker.value() else None
        hi = datetime.combine(self.to_picker.value(), datetime.min.time()) if self.to_picker.value() else None
        self.action_cb.config(values=["All"] + self.actions())
        self.rows = self.fetch(lo, hi, self.action_var.get(), self.query_var.get())
        shown = []
        for r in self.rows:
            d = dict(r)
            d["when"] = format_datetime(r.get("when")) if r.get("when") else ""
            shown.append(d)
        self.table.set_data(shown)
        self.count.config(text=f"{len(self.rows)} entr{'y' if len(self.rows) == 1 else 'ies'}" + (f" (the newest {AuditService.LIMIT} are listed; narrow the dates)" if len(self.rows) >= AuditService.LIMIT else ""))

    def export(self):
        if not self.rows:
            messagebox.showinfo("Export", "There is nothing to export.", parent=self.view)
            return
        path = filedialog.asksaveasfilename(parent=self.view, defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="audit_log.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(self.headings)
            for r in self.rows:
                w.writerow([format_datetime(r["when"]) if k == "when" and r.get("when") else r.get(k, "") for k in self.keys])
        messagebox.showinfo("Export", f"Saved {path}", parent=self.view)


class AuditLogView(ttk.Frame):
    def __init__(self, parent, db, current_user=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.svc = AuditService(db)
        self.current_user = current_user
        theme.page_header(self, "System Audit Logs", "Who did what, and when. Nothing here can be changed.").pack(fill="x", padx=28, pady=(20, 10))
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=28, pady=(0, 16))
        self.bills_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.bills_tab, text="Bill changes")
        self.activity_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.activity_tab, text="Sign-ins and activity")
        self.bills = _Tab(self, self.bills_tab, self.svc.bill_changes, self.svc.bill_actions,
                          [("when", "When", 140), ("user", "User", 110), ("invoice_no", "Invoice", 130), ("action", "Action", 130),
                           ("field", "Field", 90), ("old", "Before", 170), ("new", "After", 190)],
                          "No bill changes recorded yet. Making, voiding or returning a bill is listed here.")
        self.activity = _Tab(self, self.activity_tab, self.svc.user_activity, self.svc.activity_actions,
                             [("when", "When", 150), ("user", "User", 130), ("action", "Action", 140), ("details", "Details", 520)],
                             "No activity recorded yet. Sign-ins are listed here.")
        self.refresh()

    def refresh(self):
        self.bills.load()
        self.activity.load()
