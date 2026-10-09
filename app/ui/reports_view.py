"""Daybook, item-wise and customer-wise sales: one screen, a report picker and a date range."""
from __future__ import annotations

import csv
import logging
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
from typing import Any, Dict, List, Optional

from app.services.report_service import ReportService
from app.utils.currency import format_inr, format_balance
from app.utils.formatters import format_date
from app.ui.components.calendar_popup import attach_date_picker

log = logging.getLogger(__name__)

REPORTS = ("Daybook", "Item-wise Sales", "Customer-wise Sales")


class ReportsFrame(tk.Frame):
    def __init__(self, parent, db, current_user=None, **kwargs):
        super().__init__(parent, bg="#f8fafc", **kwargs)
        self.db = db
        self.svc = ReportService(db)
        self.current_user = current_user
        self._rows: List[Dict[str, Any]] = []
        self._cols: List[tuple] = []
        self._totals_text = ""

        tk.Label(self, text="Reports", font=("Segoe UI", 22, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w", padx=28, pady=(20, 8))

        bar = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=14, pady=10)
        bar.pack(fill="x", padx=28, pady=(0, 12))
        tk.Label(bar, text="REPORT", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(side="left")
        self.report_var = tk.StringVar(value=REPORTS[0])
        self.report_cb = ttk.Combobox(bar, textvariable=self.report_var, values=REPORTS, state="readonly", width=20)
        self.report_cb.pack(side="left", padx=(6, 18))
        self.report_cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        today = datetime.now()
        tk.Label(bar, text="FROM", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(side="left")
        self.from_var = tk.StringVar(value=today.replace(day=1).strftime("%d/%m/%Y"))
        self.from_ent = tk.Entry(bar, textvariable=self.from_var, width=12, relief="solid", bd=1)
        self.from_ent.pack(side="left", padx=(6, 12), ipady=4)
        self.from_picker = attach_date_picker(self.from_ent, "%d/%m/%Y", on_selected=lambda _d: self.refresh(), label="The From date")
        tk.Label(bar, text="TO", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(side="left")
        self.to_var = tk.StringVar(value=today.strftime("%d/%m/%Y"))
        self.to_ent = tk.Entry(bar, textvariable=self.to_var, width=12, relief="solid", bd=1)
        self.to_ent.pack(side="left", padx=(6, 12), ipady=4)
        self.to_picker = attach_date_picker(self.to_ent, "%d/%m/%Y", on_selected=lambda _d: self.refresh(), label="The To date",
                                            not_before=lambda: self.from_picker.value())
        tk.Button(bar, text="Show", bg="#4f46e5", fg="#ffffff", relief="flat", bd=0, padx=16, pady=5, cursor="hand2", command=self.refresh).pack(side="left")
        tk.Button(bar, text="Export CSV", bg="#ffffff", relief="solid", bd=1, padx=12, pady=3, cursor="hand2", command=self.export_csv).pack(side="right")
        for label, days in (("This month", 0), ("Today", -1)):
            tk.Button(bar, text=label, bg="#f1f5f9", relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                      command=lambda d=days: self._preset(d)).pack(side="right", padx=(0, 6))

        card = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        card.pack(fill="both", expand=True, padx=28, pady=(0, 8))
        self.tree = ttk.Treeview(card, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        self.summary = tk.Label(self, text="", font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#f8fafc", anchor="w")
        self.summary.pack(fill="x", padx=28, pady=(0, 14))

    # ------------------------------------------------------------------ actions
    def show_report(self, name: str) -> None:
        if name in REPORTS:
            self.report_var.set(name)
        self.refresh()

    def _preset(self, which: int) -> None:
        today = datetime.now()
        self.to_var.set(today.strftime("%d/%m/%Y"))
        self.from_var.set(today.strftime("%d/%m/%Y") if which < 0 else today.replace(day=1).strftime("%d/%m/%Y"))
        self.refresh()

    def _dates(self):
        def as_dt(d):
            return datetime.combine(d, datetime.min.time()) if d else None
        return as_dt(self.from_picker.value()), as_dt(self.to_picker.value())

    def refresh(self) -> None:
        for picker, entry in ((self.from_picker, self.from_ent), (self.to_picker, self.to_ent)):
            problem = picker.error()
            if problem:
                messagebox.showwarning("Date", problem, parent=self)
                entry.focus_set()
                return
        lo, hi = self._dates()
        name = self.report_var.get()
        try:
            if name == "Daybook":
                res = self.svc.daybook(lo, hi)
                t = res["totals"]
                cols = [("date", "Date", 90, "w"), ("type", "Type", 80, "w"), ("ref", "Reference", 140, "w"), ("party", "Party", 220, "w"),
                        ("billed", "Billed", 110, "e"), ("bought", "Bought", 110, "e"), ("money_in", "Money in", 110, "e"), ("money_out", "Money out", 110, "e")]
                rows = [{**r, "date": format_date(r["date"]), **{k: self._amt(r[k]) for k in ("billed", "bought", "money_in", "money_out")}} for r in res["rows"]]
                self._totals_text = (f"Billed {format_inr(t['billed'])}    Bought {format_inr(t['bought'])}    Money in {format_inr(t['money_in'])}    "
                                     f"Money out {format_inr(t['money_out'])}    Net money {format_inr(t['net_money'])}")
            elif name == "Item-wise Sales":
                res = self.svc.item_sales(lo, hi)
                cols = [("name", "Item", 240, "w"), ("bills", "Bills", 60, "e"), ("qty", "Sold qty", 90, "e"), ("returned_qty", "Returned", 90, "e"),
                        ("net_qty", "Net qty", 90, "e"), ("unit", "Unit", 60, "w"), ("avg_rate", "Avg rate", 100, "e"), ("net_amount", "Net amount", 130, "e")]
                rows = [{**r, "avg_rate": self._amt(r["avg_rate"]), "net_amount": self._amt(r["net_amount"])} for r in res["rows"]]
                self._totals_text = f"{res['totals']['items']} items    Net sales {format_inr(res['totals']['net_amount'])}"
            else:
                res = self.svc.customer_sales(lo, hi)
                cols = [("name", "Customer", 260, "w"), ("bills", "Bills", 60, "e"), ("billed", "Billed", 120, "e"), ("returned", "Returned", 110, "e"),
                        ("net", "Net sales", 130, "e"), ("balance", "Owes now", 140, "e")]
                rows = [{**r, "billed": self._amt(r["billed"]), "returned": self._amt(r["returned"]), "net": self._amt(r["net"]),
                         "balance": format_balance(r["balance"])} for r in res["rows"]]
                tt = res["totals"]
                self._totals_text = f"{tt['customers']} customers    {tt['bills']} bills    Net sales {format_inr(tt['net'])}"
        except Exception as exc:
            log.exception("Report failed")
            messagebox.showerror("Report", str(exc), parent=self)
            return
        self._cols, self._rows = cols, rows
        self.tree.configure(columns=[c[0] for c in cols])
        for key, text, width, anchor in cols:
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor)
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", values=[r.get(c[0], "") for c in cols])
        self.summary.config(text=self._totals_text if rows else "Nothing in this date range.")

    @staticmethod
    def _amt(v: float) -> str:
        return format_inr(v, symbol=False) if v else ""

    def export_csv(self) -> None:
        if not self._rows:
            messagebox.showinfo("Export", "There is nothing to export.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile=f"{self.report_var.get().replace(' ', '_').lower()}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([c[1] for c in self._cols])
            for r in self._rows:
                w.writerow([r.get(c[0], "") for c in self._cols])
            w.writerow([])
            w.writerow([self._totals_text])
        messagebox.showinfo("Export", f"Saved {path}", parent=self)
