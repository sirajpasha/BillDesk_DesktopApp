"""Customer statement: invoices and receipts with a running balance, for any date range."""
from __future__ import annotations

import csv
import logging
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
from typing import Any, Dict, Optional

from app.services.payment_service import PaymentService
from app.utils.currency import format_inr, format_balance
from app.utils.formatters import format_date

log = logging.getLogger(__name__)


class StatementWindow(tk.Toplevel):
    """Opened from the Customer Master and from the Receivables screen."""

    def __init__(self, parent, db, customer_id: str, customer_name: str = ""):
        super().__init__(parent)
        self.pay_svc = PaymentService(db)
        self.customer_id = customer_id
        self.title(f"Statement - {customer_name or customer_id}")
        self.geometry("920x600")
        self.configure(bg="#f8fafc")
        self.transient(parent.winfo_toplevel())
        self._result: Optional[Dict[str, Any]] = None

        head = tk.Frame(self, bg="#4f46e5", padx=16, pady=10)
        head.pack(fill="x")
        self.title_lbl = tk.Label(head, text=customer_name or customer_id, font=("Segoe UI", 13, "bold"), fg="#ffffff", bg="#4f46e5")
        self.title_lbl.pack(anchor="w")

        bar = tk.Frame(self, bg="#f8fafc", padx=16, pady=10)
        bar.pack(fill="x")
        tk.Label(bar, text="From (YYYY-MM-DD)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left")
        self.from_var = tk.StringVar()
        self.from_ent = tk.Entry(bar, textvariable=self.from_var, width=12, relief="solid", bd=1)
        self.from_ent.pack(side="left", padx=(4, 12), ipady=3)
        tk.Label(bar, text="To", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left")
        self.to_var = tk.StringVar()
        self.to_ent = tk.Entry(bar, textvariable=self.to_var, width=12, relief="solid", bd=1)
        self.to_ent.pack(side="left", padx=(4, 12), ipady=3)
        tk.Button(bar, text="Show", bg="#4f46e5", fg="#ffffff", relief="flat", padx=14, pady=3, command=self.refresh).pack(side="left")
        tk.Button(bar, text="Export CSV", bg="#ffffff", relief="solid", bd=1, padx=10, pady=2, command=self.export_csv).pack(side="right")
        self.from_ent.bind("<Return>", lambda _e: self.refresh())
        self.to_ent.bind("<Return>", lambda _e: self.refresh())

        cols = ("date", "type", "ref", "note", "debit", "credit", "balance")
        frame = tk.Frame(self, bg="#ffffff", bd=1, relief="solid")
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for key, text, width, anchor in (("date", "Date", 90, "w"), ("type", "Type", 70, "w"), ("ref", "Reference", 130, "w"),
                                         ("note", "Details", 200, "w"), ("debit", "Billed (Dr)", 110, "e"),
                                         ("credit", "Received (Cr)", 110, "e"), ("balance", "Balance", 130, "e")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("opening", background="#f1f5f9")

        self.summary = tk.Label(self, text="", font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#f8fafc", anchor="w")
        self.summary.pack(fill="x", padx=16, pady=(0, 12))
        self.refresh()

    @staticmethod
    def _parse(text: str) -> Optional[datetime]:
        text = (text or "").strip()
        if not text:
            return None
        return datetime.strptime(text, "%Y-%m-%d")

    def refresh(self) -> None:
        try:
            lo, hi = self._parse(self.from_var.get()), self._parse(self.to_var.get())
        except ValueError:
            messagebox.showwarning("Date", "Enter dates as YYYY-MM-DD (e.g. 2026-04-01), or leave blank.", parent=self)
            return
        try:
            res = self.pay_svc.customer_statement(self.customer_id, lo, hi)
        except Exception as exc:
            log.exception("Statement failed")
            messagebox.showerror("Statement", str(exc), parent=self)
            return
        self._result = res
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end", tags=("opening",), values=("", "", "", "Balance brought forward", "", "", format_balance(res["opening"])))
        for r in res["rows"]:
            self.tree.insert("", "end", values=(
                format_date(r["date"]), r["type"], r["ref"], r["note"],
                format_inr(r["debit"], symbol=False) if r["debit"] else "",
                format_inr(r["credit"], symbol=False) if r["credit"] else "",
                format_balance(r["balance"])))
        self.summary.config(text=f"Billed {format_inr(res['total_debit'])}    Received {format_inr(res['total_credit'])}    "
                                 f"Closing balance {format_balance(res['closing'])}")

    def export_csv(self) -> None:
        if not self._result:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile=f"statement_{self.customer_id}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        res = self._result
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Date", "Type", "Reference", "Details", "Billed", "Received", "Balance"])
            w.writerow(["", "", "", "Balance brought forward", "", "", res["opening"]])
            for r in res["rows"]:
                w.writerow([format_date(r["date"]), r["type"], r["ref"], r["note"], r["debit"] or "", r["credit"] or "", r["balance"]])
            w.writerow(["", "", "", "Closing balance", res["total_debit"], res["total_credit"], res["closing"]])
        messagebox.showinfo("Export", f"Saved {path}", parent=self)
