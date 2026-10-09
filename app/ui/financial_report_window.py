"""Trial Balance, Profit & Loss and Balance Sheet windows with the period chosen on screen.

    mode "range"  -> From / To   (Profit & Loss: the result of a period)
    mode "as_of"  -> As of       (Trial Balance, Balance Sheet: the position on a day)

Every date box has the calendar; blank means "all entries" / "up to now"."""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from app.ui import theme
from app.ui.components.calendar_popup import attach_date_picker


def financial_year_start(today: Optional[date] = None) -> date:
    """The Indian financial year starts on 1 April."""
    t = today or date.today()
    return date(t.year if t.month >= 4 else t.year - 1, 4, 1)


class FinancialReportWindow(tk.Toplevel):
    def __init__(self, parent, title: str, mode: str, render: Callable[[Optional[datetime], Optional[datetime]], str], on_render: Optional[Callable[[str, str], None]] = None):
        super().__init__(parent)
        self.mode, self.render, self.on_render, self.report_title = mode, render, on_render, title
        self.title(title)
        self.geometry("700x640")
        self.transient(parent.winfo_toplevel())
        self.configure(bg=theme.SURFACE)

        bar = tk.Frame(self, bg=theme.BG, padx=14, pady=10)
        bar.pack(fill="x")
        if mode == "range":
            tk.Label(bar, text="FROM", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
            self.from_ent = tk.Entry(bar, width=12, relief="solid", bd=1)
            self.from_ent.pack(side="left", padx=(6, 0), ipady=4)
            self.from_picker = attach_date_picker(self.from_ent, "%d/%m/%Y", button=True, on_selected=lambda _d: self.show(), label="The From date")
            tk.Label(bar, text="TO", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
            self.to_ent = tk.Entry(bar, width=12, relief="solid", bd=1)
            self.to_ent.pack(side="left", padx=(6, 0), ipady=4)
            self.to_picker = attach_date_picker(self.to_ent, "%d/%m/%Y", button=True, on_selected=lambda _d: self.show(), label="The To date",
                                                not_before=lambda: self.from_picker.value())
        else:
            self.from_ent = self.from_picker = None
            tk.Label(bar, text="AS OF", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left")
            self.to_ent = tk.Entry(bar, width=12, relief="solid", bd=1)
            self.to_ent.pack(side="left", padx=(6, 0), ipady=4)
            self.to_picker = attach_date_picker(self.to_ent, "%d/%m/%Y", button=True, on_selected=lambda _d: self.show(), label="The As-of date")
        theme.primary_button(bar, "Show", self.show).pack(side="left", padx=(4, 12))
        presets = ([("This month", self._this_month), ("This financial year", self._this_year), ("All time", self._all)] if mode == "range"
                   else [("Today", self._today), ("End of last month", self._last_month_end), ("All entries", self._all)])
        for label, fn in presets:
            tk.Button(bar, text=label, command=fn, relief="flat", bd=0, bg=theme.HEADING_BG, padx=10, pady=4, cursor="hand2").pack(side="left", padx=(0, 6))

        self.box = tk.Text(self, font=("Consolas", 10), bg=theme.SURFACE, fg=theme.TEXT, relief="flat", padx=16, pady=14, wrap="none")
        self.box.pack(fill="both", expand=True)
        foot = tk.Frame(self, bg=theme.SURFACE)
        foot.pack(fill="x", pady=8)
        tk.Button(foot, text="Close", command=self.destroy, relief="flat", bg=theme.PRIMARY, fg=theme.SURFACE, font=theme.F_BOLD, padx=16, pady=5).pack(side="right", padx=14)
        theme.secondary_button(foot, "Save as text…", self.save_text).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.text = ""
        self.show()

    # ------------------------------------------------------------------ the period
    def period(self):
        """(from, to) as datetimes covering whole days, or raises ValueError with the sentence to show."""
        for picker in (self.from_picker, self.to_picker):
            if picker is not None and picker.error():
                raise ValueError(picker.error())
        lo = datetime.combine(self.from_picker.value(), datetime.min.time()) if self.from_picker is not None and self.from_picker.value() else None
        hi = datetime.combine(self.to_picker.value(), datetime.max.time().replace(microsecond=0)) if self.to_picker.value() else None
        return lo, hi

    def show(self):
        try:
            lo, hi = self.period()
        except ValueError as exc:
            messagebox.showwarning(self.report_title, str(exc), parent=self)
            return
        self.text = self.render(lo, hi)
        self.box.config(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", self.text)
        self.box.config(state="disabled")
        if self.on_render:
            self.on_render(self.report_title, self.text)

    def _set(self, lo: Optional[date], hi: Optional[date]):
        if self.from_picker is not None:
            self.from_picker.set(lo)
        self.to_picker.set(hi)
        self.show()

    def _this_month(self):
        t = date.today()
        self._set(t.replace(day=1), t)

    def _this_year(self):
        self._set(financial_year_start(), date.today())

    def _all(self):
        self._set(None, None)

    def _today(self):
        self._set(None, date.today())

    def _last_month_end(self):
        self._set(None, date.today().replace(day=1) - timedelta(days=1))

    def save_text(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", initialfile=self.report_title.replace(" & ", "_and_").replace(" ", "_") + ".txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)
            messagebox.showinfo(self.report_title, f"Saved {path}", parent=self)
