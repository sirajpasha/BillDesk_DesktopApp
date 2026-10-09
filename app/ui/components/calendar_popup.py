"""A small drop-down calendar for date entry boxes (no extra package needed).

    attach_date_picker(entry, fmt="%d/%m/%Y", on_selected=callback)

The calendar opens under the box when it gets the focus (or is clicked). Arrow keys move the day, Page Up / Page Down the
month, Enter or a click picks the day, Esc closes it. Enter in the box itself accepts a typed date."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, datetime
from typing import Callable, Optional
from app.ui import theme

BG, BORDER, PRIMARY, MUTED = theme.SURFACE, theme.BORDER_DARK, theme.PRIMARY, theme.TEXT_MUTED


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
    def __init__(self, anchor: tk.Widget, initial: date, on_pick: Callable[[date], None], on_close: Optional[Callable[[], None]] = None,
                 allowed: Optional[Callable[[date], bool]] = None):
        super().__init__(anchor)
        self.anchor, self.on_pick, self.on_close = anchor, on_pick, on_close
        self.allowed = allowed or (lambda _d: True)
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
        self.title_lbl = tk.Label(head, text="", font=theme.F_TEXT10B, bg=BG, width=16)
        self.title_lbl.pack(side="left", expand=True)
        tk.Button(head, text="▶", relief="flat", bg=BG, bd=0, cursor="hand2", command=lambda: self._shift_month(1)).pack(side="right")

        grid = tk.Frame(body, bg=BG)
        grid.pack(pady=(6, 4))
        for c, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(grid, text=name, font=theme.F_LABEL, fg=MUTED, bg=BG, width=4).grid(row=0, column=c)
        for r in range(6):
            for c in range(7):
                lbl = tk.Label(grid, text="", font=theme.F_BODY, bg=BG, width=4, pady=3, cursor="hand2")
                lbl.grid(row=r + 1, column=c)
                lbl.bind("<Button-1>", lambda _e, rr=r, cc=c: self._click(rr, cc))
                self._cells[(r, c)] = lbl
        tk.Button(body, text="Today", relief="flat", bg=theme.HEADING_BG, bd=0, cursor="hand2", pady=3,
                  command=lambda: self._pick(date.today())).pack(fill="x")
        self.today_btn = body.winfo_children()[-1]

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
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if y + h > self.winfo_screenheight() - 40:                  # no room below the box: open above it
            y = max(0, anchor.winfo_rooty() - h - 2)
        x = max(0, min(x, self.winfo_screenwidth() - w - 8))
        self.attributes("-topmost", True)        # without this the main window can cover the drop-down on Windows
        self.geometry(f"+{x}+{y}")               # (after the attribute: setting it afterwards resets the position to 0,0)
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
                if not self.allowed(d):
                    lbl.config(text=str(d.day), bg=BG, fg=theme.BORDER, cursor="arrow")
                elif d == self.selected:
                    lbl.config(text=str(d.day), bg=PRIMARY, fg=theme.SURFACE)
                elif d == today:
                    lbl.config(text=str(d.day), bg="#e0e7ff", fg=theme.TEXT_STRONG)
                else:
                    lbl.config(text=str(d.day), bg=BG, fg=theme.TEXT_STRONG if inside else theme.BORDER_DARK)

    def _click(self, r: int, c: int):
        d = getattr(self._cells[(r, c)], "date", None)
        if d:
            self._pick(d)

    def _pick(self, d: date):
        if not self.allowed(d):
            return
        cb = self.on_pick
        self.close()
        cb(d)


class DatePickerController:
    """Calendar drop-down plus validation for one date box.

    allow_future=False refuses dates after today; allow_blank=False makes the box required; `not_before` returns another box's
    date (a "to" box must not be earlier than its "from" box). `error()` gives the sentence to show the user, or None."""

    def __init__(self, entry: tk.Entry, fmt: str, on_selected: Optional[Callable[[date], None]], allow_future: bool = True,
                 allow_blank: bool = True, not_before: Optional[Callable[[], Optional[date]]] = None, label: str = "Date", partial_ok: bool = False):
        self.entry, self.fmt, self.on_selected = entry, fmt, on_selected
        self.allow_future, self.allow_blank, self.not_before, self.label = allow_future, allow_blank, not_before, label
        self.partial_ok = partial_ok                # a search box: "09/2026" is a fine thing to type, not an error
        self.popup: Optional[CalendarPopup] = None
        self._suppress = False
        self._normal_fg = entry.cget("fg")
        entry.bind("<FocusIn>", lambda _e: self.open(), add="+")
        entry.bind("<Button-1>", lambda _e: self.open(), add="+")
        entry.bind("<Down>", lambda _e: self.open(), add="+")
        entry.bind("<Return>", self._typed, add="+")
        entry.bind("<FocusOut>", lambda _e: entry.after(200, self.flag), add="+")
        entry.bind("<KeyRelease>", lambda _e: self.flag(), add="+")
        entry.bind("<Unmap>", lambda _e: self._close_popup(), add="+")      # the screen was switched: do not leave the calendar floating

    def add_button(self) -> Optional[tk.Widget]:
        """A small 📅 button right after the box, so it is obvious a calendar exists (the box also opens it on click)."""
        parent = self.entry.master
        try:
            bg = parent.cget("bg")
        except tk.TclError:
            bg = BG
        btn = tk.Button(parent, text="📅", relief="flat", bd=0, bg=bg, activebackground=bg, cursor="hand2", padx=3, pady=0,
                        command=lambda: (self.entry.focus_set(), self.open()))
        manager = self.entry.winfo_manager()
        if manager == "pack":
            info = self.entry.pack_info()
            pad = info.get("padx", 0)
            left, right = pad if isinstance(pad, (tuple, list)) else (pad, pad)
            self.entry.pack_configure(padx=(left, 0))                 # the button sits against the box; the old right-hand gap moves after the button
            btn.pack(side=info.get("side", "left"), after=self.entry, padx=(2, right))
        elif manager == "grid":
            info = self.entry.grid_info()
            btn.grid(row=info["row"], column=int(info["column"]) + 1, padx=(0, 6))
        else:
            btn.destroy()
            return None
        self.button = btn
        return btn

    def _close_popup(self) -> None:
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.close()

    # ---- value and validation
    def value(self) -> Optional[date]:
        return parse_date(self.entry.get(), self.fmt)

    def allowed(self, d: date) -> bool:
        if not self.allow_future and d > date.today():
            return False
        floor = self.not_before() if self.not_before else None
        return not (floor and d < floor)

    def error(self) -> Optional[str]:
        text = self.entry.get().strip()
        if not text:
            return None if self.allow_blank else f"{self.label} is required."
        d = parse_date(text, self.fmt)
        if d is None and self.partial_ok:
            return None
        if d is None:
            return f"{self.label} is not a valid date. Use {self.hint()}, or pick it from the calendar."
        if not self.allow_future and d > date.today():
            return f"{self.label} cannot be in the future."
        floor = self.not_before() if self.not_before else None
        if floor and d < floor:
            return f"{self.label} cannot be before {floor.strftime(self.fmt)}."
        return None

    def hint(self) -> str:
        return self.fmt.replace("%d", "DD").replace("%m", "MM").replace("%Y", "YYYY")

    def flag(self) -> None:
        """Red text while the box holds something that cannot be used."""
        try:
            self.entry.config(fg=theme.DANGER if self.error() else self._normal_fg)
        except tk.TclError:
            pass

    def set(self, d: Optional[date]) -> None:
        self.entry.delete(0, tk.END)
        if d:
            self.entry.insert(0, d.strftime(self.fmt))
        self.flag()

    # ---- the drop-down
    def current(self) -> date:
        return self.value() or date.today()

    def open(self):
        if self._suppress or (self.popup is not None and self.popup.winfo_exists()):
            return
        self.popup = CalendarPopup(self.entry, self.current(), self._picked, on_close=self._closed, allowed=self.allowed)

    def _closed(self):
        self.popup = None

    def _picked(self, d: date):
        self.set(d)
        self._finish(d)

    def _typed(self, _event=None):
        d = self.value()
        if d is None and not self.entry.get().strip() and self.allow_blank:
            if self.popup is not None and self.popup.winfo_exists():
                self.popup.close()
            self._finish(None)
            return "break"
        if d is None or not self.allowed(d):
            self.flag()
            return "break"
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.close()
        self.set(d)
        self._finish(d)
        return "break"

    def _finish(self, d: Optional[date]):
        self._suppress = True                       # moving the focus on must not pop the calendar open again
        try:
            if self.on_selected:
                self.on_selected(d)
        finally:
            self.entry.after(300, lambda: setattr(self, "_suppress", False))


def attach_date_picker(entry: tk.Entry, fmt: str = "%d/%m/%Y", on_selected: Optional[Callable[[date], None]] = None, *, allow_future: bool = True,
                       allow_blank: bool = True, not_before: Optional[Callable[[], Optional[date]]] = None, label: str = "Date",
                       partial_ok: bool = False, button: bool = False) -> DatePickerController:
    ctrl = DatePickerController(entry, fmt, on_selected, allow_future, allow_blank, not_before, label, partial_ok)
    ctrl.button = None
    if button:
        ctrl.add_button()
    entry._date_picker = ctrl            # keep a reference (and let tests reach it)
    return ctrl
