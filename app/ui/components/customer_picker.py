"""The customer search dialog used by New Bill and New Customer Order (F5), so both behave the same.

    open_customer_picker(owner, db, on_pick, allow_cash=True)

`on_pick(customer_or_None)` is called with the chosen customer document (None = the walk-in "Cash" customer) after the dialog
has closed. Type to filter, Up / Down to move, Enter to choose, Esc to close; a click picks too."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, Optional


def open_customer_picker(owner: tk.Widget, db: Any, on_pick: Callable[[Optional[Dict[str, Any]]], None], allow_cash: bool = True) -> tk.Toplevel:
    modal = tk.Toplevel(owner)
    modal.title("Select Customer (F5)")
    modal.resizable(False, False)
    modal.transient(owner.winfo_toplevel())
    modal.grab_set()
    sw, sh = modal.winfo_screenwidth(), modal.winfo_screenheight()
    modal.geometry(f"500x380+{(sw - 500) // 2}+{(sh - 380) // 2}")

    frame = tk.Frame(modal, bg="#ffffff", padx=20, pady=16)
    frame.pack(fill="both", expand=True)
    top_bar = tk.Frame(frame, bg="#ffffff")
    top_bar.pack(fill="x", pady=(0, 12))
    tk.Label(top_bar, text="Select Customer (F5)", font=("Segoe UI", 12, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left")
    tk.Button(top_bar, text="✕", font=("Segoe UI", 10), bg="#ffffff", fg="#64748b", relief="flat", bd=0, command=modal.destroy).pack(side="right")

    s_box = tk.Frame(frame, bg="#3b82f6", padx=1, pady=1)
    s_box.pack(fill="x", pady=(0, 12))
    search_ent = tk.Entry(s_box, font=("Segoe UI", 11), relief="flat", bd=0)
    search_ent.pack(fill="x", ipady=6, padx=8)
    modal.focus_force()
    search_ent.focus_force()

    list_canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=1, highlightbackground="#e2e8f0")
    list_scroll = ttk.Scrollbar(frame, orient="vertical", command=list_canvas.yview)
    cards_box = tk.Frame(list_canvas, bg="#ffffff")
    cards_box.bind("<Configure>", lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
    c_win = list_canvas.create_window((0, 0), window=cards_box, anchor="nw")
    list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfig(c_win, width=e.width))
    list_canvas.configure(yscrollcommand=list_scroll.set)
    list_canvas.pack(side="left", fill="both", expand=True)
    list_scroll.pack(side="right", fill="y")

    try:
        customers = list(db.collection("customers").find({"is_deleted": 0}))
    except Exception:
        customers = []
    customers.sort(key=lambda c: str(c.get("name", "")).lower())

    choices: list = []          # (card frame, customer or None for the cash customer), in on-screen order
    cursor = {"i": 0}

    def _highlight(i: int):
        if not choices:
            return
        cursor["i"] = max(0, min(i, len(choices) - 1))
        for n, (frame_, _c) in enumerate(choices):
            frame_.configure(highlightbackground="#4f46e5" if n == cursor["i"] else "#e2e8f0",
                             highlightthickness=2 if n == cursor["i"] else 1)
        frame_ = choices[cursor["i"]][0]
        list_canvas.update_idletasks()
        bbox = list_canvas.bbox("all")
        if bbox and bbox[3] > 0:
            list_canvas.yview_moveto(max(0.0, (frame_.winfo_y() - 40) / bbox[3]))

    def _card(title: str, detail: str, target):
        c_card = tk.Frame(cards_box, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=8, cursor="hand2")
        c_card.pack(fill="x", pady=3, padx=4)
        tk.Label(c_card, text=title, font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")
        tk.Label(c_card, text=detail, font=("Segoe UI", 8), fg="#64748b", bg="#ffffff").pack(anchor="w")
        for w in (c_card, *c_card.winfo_children()):
            w.bind("<Button-1>", lambda _e, t=target: _pick(t))
        choices.append((c_card, target))

    def _render(query: str = ""):
        for w in cards_box.winfo_children():
            w.destroy()
        choices.clear()
        if allow_cash and (not query or "cash" in query.lower()):
            _card("Cash Customer", "Counter Walk-in Sale", None)
        q_lower = query.lower()
        for cust in customers:
            if (q_lower in str(cust.get("name", "")).lower() or q_lower in str(cust.get("bill_to_name", "")).lower()
                    or query in str(cust.get("phone", "")) or query in str(cust.get("contact_person_phone", ""))
                    or query in str(cust.get("bill_to_phone", ""))):
                bname = cust.get("bill_to_name")
                bname_str = f"Bill To: {bname}  |  " if (bname and bname != cust.get("name")) else ""
                phone = cust.get("contact_person_phone") or cust.get("phone") or cust.get("bill_to_phone") or "-"
                gst = f"  |  GST: {cust['gst_number']}" if cust.get("gst_number") else ""
                _card(cust.get("name", ""), f"{bname_str}{phone}{gst}", cust)
        _highlight(0)

    def _pick(cust):
        modal.destroy()
        on_pick(cust)

    def _on_key(e):
        if e.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        _render(search_ent.get().strip())

    def _enter(_e=None):
        if choices:
            _pick(choices[cursor["i"]][1])
        return "break"

    search_ent.bind("<KeyRelease>", _on_key)
    search_ent.bind("<Down>", lambda _e: (_highlight(cursor["i"] + 1), "break")[1])
    search_ent.bind("<Up>", lambda _e: (_highlight(cursor["i"] - 1), "break")[1])
    search_ent.bind("<Return>", _enter)
    modal.bind("<Escape>", lambda _e: modal.destroy())
    # handles for tests and callers: a withdrawn test window cannot receive real key events
    modal.refresh_list = lambda: _render(search_ent.get().strip())
    modal.move_highlight = lambda d: _highlight(cursor["i"] + d)
    modal.pick_highlighted = _enter
    modal.search_entry = search_ent
    _render()
    return modal
