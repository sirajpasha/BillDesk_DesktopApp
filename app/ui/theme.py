"""One place for the look of the application: colours, fonts, ttk styles and the small building blocks.

New screens should use these names instead of repeating hex codes. The older screens are being moved over; the
default ttk look is replaced for every screen by `apply_ttk_theme`."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ---- colours
BG = "#f8fafc"            # page background
SURFACE = "#ffffff"       # cards
BORDER = "#e2e8f0"
TEXT = "#0f172a"
TEXT_MUTED = "#64748b"
TEXT_FAINT = "#94a3b8"
PRIMARY = "#4f46e5"
PRIMARY_DARK = "#4338ca"
SUCCESS = "#059669"
WARNING = "#d97706"
DANGER = "#dc2626"
ROW_ALT = "#f9fafb"
HEADING_BG = "#f1f5f9"
SELECT_BG = "#e0e7ff"

# ---- fonts
FONT = "Segoe UI"
F_TITLE = (FONT, 22, "bold")
F_SECTION = (FONT, 12, "bold")
F_BODY = (FONT, 9)
F_BOLD = (FONT, 9, "bold")
F_SMALL = (FONT, 8)
F_BUTTON = (FONT, 9, "bold")


def apply_ttk_theme(style: ttk.Style) -> None:
    """Give every ttk widget (tables, tabs, buttons, entries, group boxes) the application's look."""
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    style.configure(".", font=F_BODY)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=F_BODY)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=TEXT, font=F_SECTION)
    style.configure("TCheckbutton", background=BG)
    style.configure("TRadiobutton", background=BG)
    style.configure("TButton", font=F_BUTTON, padding=(12, 5))
    style.configure("TEntry", padding=(4, 4))
    style.configure("TCombobox", padding=(4, 4))
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", font=F_BUTTON, padding=(16, 7), background=HEADING_BG)
    style.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", PRIMARY)])
    style.configure("Treeview", font=F_BODY, rowheight=26, background=SURFACE, fieldbackground=SURFACE, bordercolor=BORDER)
    style.configure("Treeview.Heading", font=F_BOLD, background=HEADING_BG, foreground=TEXT, padding=(6, 5))
    style.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", TEXT)])
    style.configure("App.TFrame", background=BG)
    style.configure("White.TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
    style.configure("Title.TLabel", font=F_TITLE, background=BG, foreground=TEXT)
    style.configure("Section.TLabel", font=F_SECTION, background=BG, foreground="#1e293b")
    style.configure("Muted.TLabel", font=F_BODY, background=BG, foreground=TEXT_MUTED)
    style.configure("Primary.TButton", font=(FONT, 10, "bold"), padding=(14, 7))


def page_header(parent, title: str, subtitle: str = "", actions: list | None = None) -> tk.Frame:
    """Title (and optional one-line subtitle) on the left, action buttons on the right: the same header every screen uses."""
    bar = tk.Frame(parent, bg=BG)
    box = tk.Frame(bar, bg=BG)
    box.pack(side="left")
    tk.Label(box, text=title, font=F_TITLE, fg=TEXT, bg=BG).pack(anchor="w")
    if subtitle:
        tk.Label(box, text=subtitle, font=F_BODY, fg=TEXT_MUTED, bg=BG).pack(anchor="w")
    for text, command in reversed(actions or []):
        primary_button(bar, text, command).pack(side="right", padx=(8, 0))
    return bar


def primary_button(parent, text: str, command) -> tk.Button:
    return tk.Button(parent, text=text, command=command, font=F_BUTTON, bg=PRIMARY, fg="#ffffff", activebackground=PRIMARY_DARK,
                     activeforeground="#ffffff", relief="flat", bd=0, padx=16, pady=6, cursor="hand2")


def secondary_button(parent, text: str, command) -> tk.Button:
    return tk.Button(parent, text=text, command=command, font=F_BUTTON, bg=SURFACE, fg="#334155", activebackground=HEADING_BG,
                     relief="solid", bd=1, padx=12, pady=4, cursor="hand2")


def card(parent, **pack) -> tk.Frame:
    f = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    if pack:
        f.pack(**pack)
    return f


def empty_state(parent, headline: str, hint: str, action_text: str = "", action=None) -> tk.Frame:
    """What an empty list shows: a plain sentence about what goes here and what to do first."""
    f = tk.Frame(parent, bg=SURFACE)
    tk.Label(f, text=headline, font=(FONT, 12, "bold"), fg="#334155", bg=SURFACE).pack(pady=(28, 4))
    tk.Label(f, text=hint, font=F_BODY, fg=TEXT_MUTED, bg=SURFACE, wraplength=460, justify="center").pack()
    if action_text and action:
        primary_button(f, action_text, action).pack(pady=14)
    return f
