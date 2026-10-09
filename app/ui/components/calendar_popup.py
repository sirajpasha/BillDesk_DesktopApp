"""A small drop-down calendar for date entry boxes (no extra package needed).

    attach_date_picker(entry, fmt="%d/%m/%Y", on_selected=callback)

The calendar opens under the box when it gets the focus (or is clicked). Arrow keys move the day, Page Up / Page Down the
month, Enter or a click picks the day, Esc closes it. Enter in the box itself accepts a typed date."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, datetime
from typing import Callable, Optional

BG, BORDER, PRIMARY, MUTED = "#ffffff", "#cbd5e1", "#4f46e5", "#64748b"


def parse_date(text: str, fmt: str = "%d/%m/%Y") -> Optional[date]:
    """Accepts the field's own format plus the other separators people type (13-10-2026, 13 - 10 - 2026, 2026-10-13)."""
    t = (text or "").strip()
    if not t:
        return None
    t = t.replace(" ", "").replace("-", "/").replace(".", "/")
    for f in (fmt.replace(" ", "").replace("-", "/"), "%d/%m/%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


class CalendarPopup(tk.Toplevel):
    def __init__(self, anchor: tk.Widget, initial: date, on_pick: Callable[[date], None], on_close: Optional[Callable[[], None]] = None):
        super().__init__(anchor)
        self.anchor, self.on_pick, self.on_close = anchor, on_pick, on_close
        self.selected = initial
        self.view = initial.replace(day=1)
        self.overrideredirect(True)
        self.configure(bg=BORDER)
        self._cells: dict = {}
        body = tk.Frame(self, bg=BG, padx=8, pady=8)
        body.pack(padx=1, pady=1)

        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")
        tk.Button(head, text="◀", relief="flat", bg=BG, bd=0, cursor="hand2", command=lambda: self._shift_month(-1)).pack(side="left")
        self.title_lbl = tk.Label(head, text="", font=("Segoe UI", 10, "bold"), bg=BG, width=16)
        self.title_lbl.pack(side="left", expand=True)
        tk.Button(head, text="▶", relief="flat", bg=BG, bd=0, cursor="hand2", command=lambda: self._shift_month(1)).pack(side="right")

        grid = tk.Frame(body, bg=BG)
        grid.pack(pady=(6, 4))
        for c, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(grid, text=name, font=("Segoe UI", 8, "bold"), fg=MUTED, bg=BG, width=4).grid(row=0, column=c)
        for r in range(6):
            for c in range(7):
                lbl = tk.Label(grid, text="", font=("Segoe UI", 9), bg=BG, width=4, pady=3, cursor="hand2")
                lbl.grid(row=r + 1, column=c)
                lbl.bind("<Button-1>", lambda _e, rr=r, cc=c: self._click(rr, cc))
                self._cells[(r, c)] = lbl
        tk.Button(body, text="Today", relief="flat", bg="#f1f5f9", bd=0, cursor="hand2", pady=3,
                  command=lambda: self._pick(date.today())).pack(fill="x")

        for seq, fn in (("<Left>", -1), ("<Right>", 1), ("<Up>", -7), ("<Down>", 7)):
            self.bind(seq, lambda _e, d=fn: self._move(d))
        self.bind("<Prior>", lambda _e: self._shift_month(-1, keep_day=True))
        self.bind("<Next>", lambda _e: self._shift_month(1, keep_day=True))
        self.bind("<Return>", lambda _e: self._pick(self.selected))
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<FocusOut>", lambda _e: self.after(120, self._maybe_close))
        self._render()
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        self.geometry(f"+{x}+{y}")
        self.attributes("-topmost", True)        # without this the main window can cover the drop-down on Windows
        self.lift()
        self.after(10, self._take_focus)

    def _take_focus(self):
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _maybe_close(self):
        try:
            if not self.winfo_exists():
                return
            focus = self.focus_get()
            if focus is None or not str(focus).startswith(str(self)):
                self.close()
        except (tk.TclError, KeyError):
            self.close()

    def close(self):
        cb, self.on_close = self.on_close, None
        try:
            self.destroy()
        except tk.TclError:
            pass
        if cb:
            cb()

    def _shift_month(self, delta: int, keep_day: bool = False):
        y, m = self.view.year, self.view.month + delta
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        self.view = date(y, m, 1)
        if keep_day:
            last = calendar.monthrange(y, m)[1]
            self.selected = date(y, m, min(self.selected.day, last))
        self._render()

    def _move(self, days: int):
        from datetime import timedelta
        self.selected = self.selected + timedelta(days=days)
        self.view = self.selected.replace(day=1)
        self._render()

    def _render(self):
        self.title_lbl.config(text=self.view.strftime("%B %Y"))
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(self.view.year, self.view.month)
        today = date.today()
        for r in range(6):
            for c in range(7):
                lbl = self._cells[(r, c)]
                d = weeks[r][c] if r < len(weeks) else None
                lbl.date = d
                if d is None:
                    lbl.config(text="", bg=BG)
                    continue
                inside = d.month == self.view.month
                if d == self.selected:
                    lbl.config(text=str(d.day), bg=PRIMARY, fg="#ffffff")
                elif d == today:
                    lbl.config(text=str(d.day), bg="#e0e7ff", fg="#1e293b")
                else:
                    lbl.config(text=str(d.day), bg=BG, fg="#1e293b" if inside else "#cbd5e1")

    def _click(self, r: int, c: int):
        d = getattr(self._cells[(r, c)], "date", None)
        if d:
            self._pick(d)

    def _pick(self, d: date):
        cb = self.on_pick
        self.close()
        cb(d)


class DatePickerController:
    def __init__(self, entry: tk.Entry, fmt: str, on_selected: Optional[Callable[[date], None]]):
        self.entry, self.fmt, self.on_selected = entry, fmt, on_selected
        self.popup: Optional[CalendarPopup] = None
        self._suppress = False
        entry.bind("<FocusIn>", lambda _e: self.open(), add="+")
        entry.bind("<Button-1>", lambda _e: self.open(), add="+")
        entry.bind("<Down>", lambda _e: self.open(), add="+")
        entry.bind("<Return>", self._typed, add="+")

    def current(self) -> date:
        return parse_date(self.entry.get(), self.fmt) or date.today()

    def open(self):
        if self._suppress or (self.popup is not None and self.popup.winfo_exists()):
            return
        self.popup = CalendarPopup(self.entry, self.current(), self._picked, on_close=self._closed)

    def _closed(self):
        self.popup = None

    def _picked(self, d: date):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, d.strftime(self.fmt))
        self._finish(d)

    def _typed(self, _event=None):
        d = parse_date(self.entry.get(), self.fmt)
        if d is None:
            return "break"
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.close()
        self.entry.delete(0, tk.END)
        self.entry.insert(0, d.strftime(self.fmt))
        self._finish(d)
        return "break"

    def _finish(self, d: date):
        self._suppress = True                       # moving the focus on must not pop the calendar open again
        try:
            if self.on_selected:
                self.on_selected(d)
        finally:
            self.entry.after(300, lambda: setattr(self, "_suppress", False))


def attach_date_picker(entry: tk.Entry, fmt: str = "%d/%m/%Y", on_selected: Optional[Callable[[date], None]] = None) -> DatePickerController:
    ctrl = DatePickerController(entry, fmt, on_selected)
    entry._date_picker = ctrl            # keep a reference (and let tests reach it)
    return ctrl
