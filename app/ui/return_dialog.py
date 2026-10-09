"""Take goods back against an invoice (credit note)."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional

from app.services.returns_service import ReturnsService
from app.utils.currency import format_inr

log = logging.getLogger(__name__)


def open_note_pdf(parent, db, kind: str, ret: Dict[str, Any]) -> Optional[str]:
    """Make the credit note ("sales") or debit note ("purchase") PDF for a saved return and show it in the print preview."""
    import os
    from app import paths
    from app.printing.notes import generate_credit_note_pdf, generate_debit_note_pdf
    from app.services.master_service import MasterService
    from app.ui.print_preview import show_print_preview
    try:
        out_dir = str(paths.output_dir())
        os.makedirs(out_dir, exist_ok=True)
        if kind == "sales":
            bill = db.collection("bills").find_one({"invoice_no": str(ret.get("original_invoice_no") or "").strip()}) or {}
            cust = db.collection("customers").find_one({"cust_id": ret.get("customer_id")}) or {}
            name, label = f"Credit Note- {ret['return_id']}.pdf", "Credit Note"
            path = generate_credit_note_pdf(os.path.join(out_dir, name), ret, MasterService(db).get_company(bill.get("company_id")), cust)
        else:
            pur = db.collection("purchase_bills").find_one({"purchase_id": ret.get("purchase_id")}) or {}
            supp = db.collection("suppliers").find_one({"supplier_id": ret.get("supplier_id")}) or {}
            name, label = f"Debit Note- {ret['return_id']}.pdf", "Debit Note"
            path = generate_debit_note_pdf(os.path.join(out_dir, name), ret, MasterService(db).get_company(pur.get("company_id")), supp)
        show_print_preview(parent, path, title=f"{label} - {ret['return_id']}", default_filename=name)
        return path
    except Exception as exc:
        log.exception("Could not make the %s note", kind)
        messagebox.showwarning("Print", f"Could not create the PDF:\n{exc}", parent=parent)
        return None


class ReturnDialog(tk.Toplevel):
    """Opened from Bill History. `result` holds the saved return, or None if cancelled."""

    HEADING = "Return against {ref}"
    TITLE = "Return goods - invoice {ref}"
    CREDIT_HEADER = "Credit"
    CREDIT_TOTAL = "Credit total"
    SPOILED_COLUMN = True
    NOTE = ("The credit reduces what the customer still owes on this invoice; any excess stays as credit on their account.")

    KIND = "sales"
    NOTE_NOUN = "credit note"

    def _make_service(self, db):
        return ReturnsService(db)

    def _create(self, payload, reason: str):
        return self.svc.create_return(self.invoice_no, payload, reason=reason, refund_method=self.method.get(), user_id=self.user)

    def __init__(self, parent, db, invoice_no: str, customer_name: str, walk_in: bool, user: str = "system"):
        super().__init__(parent)
        self.svc = self._make_service(db)
        self.db = db
        self.invoice_no, self.walk_in, self.user = invoice_no, walk_in, user
        self.result: Optional[Dict[str, Any]] = None
        self.title(self.TITLE.format(ref=invoice_no))
        self.configure(bg="#ffffff")
        self.transient(parent.winfo_toplevel())

        head = tk.Frame(self, bg="#4f46e5", padx=16, pady=10)
        head.pack(fill="x")
        tk.Label(head, text=self.HEADING.format(ref=invoice_no), font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")
        tk.Label(head, text=customer_name or "Cash customer", font=("Segoe UI", 9), fg="#c7d2fe", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(self, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)
        for c, (text, w) in enumerate((("Item", 26), ("Billed", 8), ("Returned", 9), ("Return qty", 10), ("Spoiled?" if self.SPOILED_COLUMN else "", 8), (self.CREDIT_HEADER, 12))):
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
            if self.SPOILED_COLUMN:
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
            tk.Label(foot, text=self.NOTE,
                     font=("Segoe UI", 8), fg="#64748b", bg="#ffffff", wraplength=520, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        self.total_lbl = tk.Label(self, text=f"{self.CREDIT_TOTAL}: ₹0.00", font=("Segoe UI", 12, "bold"), fg="#15803d", bg="#ffffff", anchor="e", padx=16)
        self.total_lbl.pack(fill="x")

        btns = tk.Frame(self, bg="#ffffff", padx=16, pady=10)
        btns.pack(fill="x")
        tk.Button(btns, text="Save return", bg="#4f46e5", fg="#ffffff", relief="flat", bd=0, padx=16, pady=6, command=self.save).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Cancel", bg="#f1f5f9", relief="flat", bd=0, padx=14, pady=6, command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        first = next((r["entry"] for r in self.rows if str(r["entry"].cget("state")) == "normal"), None)
        if first is not None:
            first.focus_set()

    @staticmethod
    def _amount(result) -> float:
        return result["total_refund_amount"]

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
        self.total_lbl.config(text=f"{self.CREDIT_TOTAL}: {format_inr(total)}")

    def save(self) -> None:
        payload = []
        for row in self.rows:
            q = self._qty(row)
            if q > 0:
                payload.append({"item_id": row["line"]["item_id"], "qty": q, "is_waste": row["waste"].get()})
        try:
            self.result = self._create(payload, self.reason.get().strip())
        except Exception as exc:
            messagebox.showerror("Return", str(exc), parent=self)
            return
        messagebox.showinfo("Return saved", f"{self.result['return_id']} recorded.\n{self.CREDIT_TOTAL} {format_inr(self._amount(self.result))}.", parent=self)
        if messagebox.askyesno("Print", f"Open the {self.NOTE_NOUN} to print or save it?", parent=self):
            open_note_pdf(self, self.db, self.KIND, self.result)
        self.destroy()


class PurchaseReturnDialog(ReturnDialog):
    """Send goods back to a supplier against a vendor bill (debit note)."""
    HEADING = "Return to supplier against {ref}"
    TITLE = "Return to supplier - bill {ref}"
    CREDIT_HEADER = "Value"
    CREDIT_TOTAL = "Debit note total"
    SPOILED_COLUMN = False
    KIND = "purchase"
    NOTE_NOUN = "debit note"
    NOTE = ("The value (less any TDS that was deducted) reduces what you still owe on this bill; any excess stays as credit with the supplier.")

    def _make_service(self, db):
        from app.services.purchase_returns_service import PurchaseReturnsService
        return PurchaseReturnsService(db)

    def _create(self, payload, reason: str):
        return self.svc.create_return(self.invoice_no, payload, reason=reason, user_id=self.user)

    @staticmethod
    def _amount(result) -> float:
        return result["net_amount"]
