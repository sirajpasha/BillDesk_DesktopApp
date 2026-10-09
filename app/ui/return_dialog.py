"""Take goods back against an invoice (credit note)."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional

from app.services.returns_service import ReturnsService
from app.utils.currency import format_inr

log = logging.getLogger(__name__)


class ReturnDialog(tk.Toplevel):
    """Opened from Bill History. `result` holds the saved return, or None if cancelled."""

    def __init__(self, parent, db, invoice_no: str, customer_name: str, walk_in: bool, user: str = "system"):
        super().__init__(parent)
        self.svc = ReturnsService(db)
        self.invoice_no, self.walk_in, self.user = invoice_no, walk_in, user
        self.result: Optional[Dict[str, Any]] = None
        self.title(f"Return goods - invoice {invoice_no}")
        self.configure(bg="#ffffff")
        self.transient(parent.winfo_toplevel())

        head = tk.Frame(self, bg="#4f46e5", padx=16, pady=10)
        head.pack(fill="x")
        tk.Label(head, text=f"Return against {invoice_no}", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")
        tk.Label(head, text=customer_name or "Cash customer", font=("Segoe UI", 9), fg="#c7d2fe", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(self, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)
        for c, (text, w) in enumerate((("Item", 26), ("Billed", 8), ("Returned", 9), ("Return qty", 10), ("Spoiled?", 8), ("Credit", 12))):
            tk.Label(body, text=text, font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff", width=w, anchor="w" if c == 0 else "e").grid(row=0, column=c, padx=3, pady=(0, 4))

        self.lines = self.svc.returnable_lines(invoice_no)
        self.rows: List[Dict[str, Any]] = []
        for r, line in enumerate(self.lines, start=1):
            tk.Label(body, text=line["name"], font=("Segoe UI", 9), bg="#ffffff", anchor="w", width=26).grid(row=r, column=0, padx=3, pady=2, sticky="w")
            tk.Label(body, text=f"{line['billed']:g} {line['unit']}", font=("Segoe UI", 9), bg="#ffffff", anchor="e", width=8).grid(row=r, column=1)
            tk.Label(body, text=f"{line['returned']:g}", font=("Segoe UI", 9), bg="#ffffff", anchor="e", width=9).grid(row=r, column=2)
            qty = tk.StringVar()
            ent = tk.Entry(body, textvariable=qty, width=10, justify="right", relief="solid", bd=1,
                           state="normal" if line["returnable"] > 0 else "disabled")
            ent.grid(row=r, column=3, padx=3, ipady=2)
            waste = tk.BooleanVar()
            chk = tk.Checkbutton(body, variable=waste, bg="#ffffff", state="normal" if line["returnable"] > 0 else "disabled")
            chk.grid(row=r, column=4)
            credit = tk.Label(body, text="", font=("Segoe UI", 9, "bold"), bg="#ffffff", anchor="e", width=12)
            credit.grid(row=r, column=5)
            qty.trace_add("write", lambda *_: self._recalc())
            self.rows.append({"line": line, "qty": qty, "waste": waste, "credit": credit, "entry": ent})

        foot = tk.Frame(self, bg="#ffffff", padx=16, pady=4)
        foot.pack(fill="x")
        tk.Label(foot, text="Reason", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=0, column=0, sticky="w")
        self.reason = tk.Entry(foot, relief="solid", bd=1, width=48)
        self.reason.grid(row=0, column=1, padx=8, pady=3, ipady=2, sticky="w")
        self.method = tk.StringVar(value="Cash")
        if walk_in:
            tk.Label(foot, text="Refund by", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=1, column=0, sticky="w")
            ttk.Combobox(foot, textvariable=self.method, values=["Cash", "UPI", "Bank"], state="readonly", width=12).grid(row=1, column=1, padx=8, pady=3, sticky="w")
        else:
            tk.Label(foot, text="The credit reduces what the customer still owes on this invoice; any excess stays as credit on their account.",
                     font=("Segoe UI", 8), fg="#64748b", bg="#ffffff", wraplength=520, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        self.total_lbl = tk.Label(self, text="Credit total: ₹0.00", font=("Segoe UI", 12, "bold"), fg="#15803d", bg="#ffffff", anchor="e", padx=16)
        self.total_lbl.pack(fill="x")

        btns = tk.Frame(self, bg="#ffffff", padx=16, pady=10)
        btns.pack(fill="x")
        tk.Button(btns, text="Save return", bg="#4f46e5", fg="#ffffff", relief="flat", bd=0, padx=16, pady=6, command=self.save).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Cancel", bg="#f1f5f9", relief="flat", bd=0, padx=14, pady=6, command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        first = next((r["entry"] for r in self.rows if str(r["entry"].cget("state")) == "normal"), None)
        if first is not None:
            first.focus_set()

    def _qty(self, row) -> float:
        try:
            return float(row["qty"].get().strip() or 0)
        except ValueError:
            return 0.0

    def _recalc(self) -> None:
        total = 0.0
        for row in self.rows:
            q = self._qty(row)
            amt = round(q * row["line"]["rate"], 2) if q > 0 else 0.0
            row["credit"].config(text=format_inr(amt, symbol=False) if amt else "")
            total += amt
        self.total_lbl.config(text=f"Credit total: {format_inr(total)}")

    def save(self) -> None:
        payload = []
        for row in self.rows:
            q = self._qty(row)
            if q > 0:
                payload.append({"item_id": row["line"]["item_id"], "qty": q, "is_waste": row["waste"].get()})
        try:
            self.result = self.svc.create_return(self.invoice_no, payload, reason=self.reason.get().strip(),
                                                 refund_method=self.method.get(), user_id=self.user)
        except Exception as exc:
            messagebox.showerror("Return", str(exc), parent=self)
            return
        messagebox.showinfo("Return saved", f"{self.result['return_id']} recorded.\nCredit {format_inr(self.result['total_refund_amount'])}.", parent=self)
        self.destroy()
