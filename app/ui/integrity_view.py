"""Accounts > Integrity Check: run the read-only consistency checks and read the findings."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.services.integrity_service import IntegrityService
from app.ui import theme

log = logging.getLogger(__name__)
ICONS = {"ok": "OK", "warn": "WARNING", "fail": "FAIL", "info": "NOTE"}
COLORS = {"ok": "#15803d", "warn": "#b45309", "fail": "#b91c1c", "info": theme.SLATE_600}


class IntegrityView(tk.Frame):
    def __init__(self, parent, db, current_user=None, **kwargs):
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.db = db
        self.current_user = current_user
        self.report = None
        self._build()

    def _build(self):
        top = tk.Frame(self, bg=theme.BG)
        top.pack(fill="x", padx=14, pady=(16, 8))
        title = tk.Frame(top, bg=theme.BG)
        title.pack(side="left")
        tk.Label(title, text="Integrity Check", font=("Segoe UI", 18, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")
        tk.Label(title, text="Do bills, payments, customer balances, stock and the ledger agree with each other? (read-only)",
                 font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.BG).pack(anchor="w")
        btns = tk.Frame(top, bg=theme.BG)
        btns.pack(side="right")
        self.run_btn = tk.Button(btns, text="Run Check", command=self.run, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat",
                                 font=theme.F_BOLD, padx=16, pady=6)
        self.run_btn.pack(side="left", padx=4)
        tk.Button(btns, text="Save Report...", command=self.save_report, relief="solid", bd=1, bg=theme.SURFACE,
                  font=theme.F_BODY, padx=12, pady=5).pack(side="left", padx=4)

        self.summary_lbl = tk.Label(self, text="", font=theme.F_TEXT10B, bg=theme.BG, fg=theme.TEXT, anchor="w")
        self.summary_lbl.pack(fill="x", padx=16, pady=(0, 6))

        box = tk.Frame(self, bg=theme.BG)
        box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.tree = ttk.Treeview(box, columns=("status", "check", "result"), show="headings", height=13, selectmode="browse")
        for col, text, w in (("status", "Status", 90), ("check", "Check", 360), ("result", "Result", 620)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w")
        for st, color in COLORS.items():
            self.tree.tag_configure(st, foreground=color)
        self.tree.pack(side="top", fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._show_details)

        tk.Label(box, text="Details of the selected check", font=theme.F_BOLD, bg=theme.BG, fg=theme.SLATE_600).pack(anchor="w", pady=(10, 2))
        self.details = tk.Text(box, height=10, font=("Consolas", 9), bg=theme.SURFACE, relief="solid", bd=1, wrap="none", state="disabled")
        self.details.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ actions
    def refresh(self):
        self.run()

    def run(self):
        self.config(cursor="watch")
        self.run_btn.config(state="disabled")
        self.update_idletasks()
        try:
            self.report = IntegrityService(self.db).run_all()
        except Exception:
            log.exception("Integrity check failed to run")
            messagebox.showerror("Integrity Check", "The check could not run. See the log file for details.", parent=self)
            return
        finally:
            self.config(cursor="")
            self.run_btn.config(state="normal")
        self._render()

    def _render(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.report["checks"]:
            self.tree.insert("", "end", iid=r["id"], tags=(r["status"],), values=(ICONS[r["status"]], r["title"], r["summary"]))
        s = self.report["summary"]
        self.summary_lbl.config(
            text=f"{s['ok']} ok   {s['warn']} warnings   {s['fail']} failures   {s['info']} notes      (checked {self.report['run_at']:%d/%m/%Y %H:%M})",
            fg=COLORS["fail"] if s["fail"] else COLORS["warn"] if s["warn"] else COLORS["ok"])
        self._set_details("Select a check above to see which records are affected.")

    def _set_details(self, text: str):
        self.details.config(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.config(state="disabled")

    def _show_details(self, _event=None):
        sel = self.tree.selection()
        if not sel or not self.report:
            return
        r = next(c for c in self.report["checks"] if c["id"] == sel[0])
        body = "\n".join(r["details"]) if r["details"] else "Nothing to report - no records are affected."
        self._set_details(f"{r['title']}\n{r['summary']}\n\n{body}")

    def save_report(self):
        if not self.report:
            self.run()
        if not self.report:
            return
        path = filedialog.asksaveasfilename(parent=self, title="Save integrity report", defaultextension=".txt",
                                            initialfile=f"integrity_{self.report['run_at']:%Y%m%d_%H%M}.txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(IntegrityService.format_report(self.report))
            messagebox.showinfo("Integrity Check", f"Report saved to\n{path}", parent=self)
