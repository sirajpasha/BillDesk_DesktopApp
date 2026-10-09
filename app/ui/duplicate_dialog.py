from __future__ import annotations
import tkinter as tk
from app.ui import theme


class DuplicateItemDialog(tk.Toplevel):
    """
    Modal dialog prompted when a duplicate item is entered in Billing or Order forms.
    Prompts the user to confirm whether to Add the QTY to the existing line item or Ignore (delete duplicate).
    """

    def __init__(
        self,
        parent,
        item_name: str,
        item_code: str,
        prev_row_num: int,
        prev_qty: float,
        curr_qty: float,
        unit: str = "Kg"
    ):
        super().__init__(parent)
        self.title("Duplicate Item Detected")
        self.geometry("480x280")
        self.resizable(False, False)
        self.configure(bg=theme.SURFACE)
        if hasattr(parent, "winfo_toplevel"):
            self.transient(parent.winfo_toplevel())
        self.grab_set()

        self.action: str = "IGNORE"
        self.add_qty: float = curr_qty if curr_qty > 0 else 1.0

        # Header banner
        header = tk.Frame(self, bg=theme.WARNING, padx=16, pady=10)
        header.pack(fill="x")
        tk.Label(
            header,
            text="⚠️  Duplicate Item Detected",
            font=theme.F_H12B,
            fg=theme.SURFACE,
            bg=theme.WARNING
        ).pack(side="left")

        # Body
        body = tk.Frame(self, bg=theme.SURFACE, padx=20, pady=14)
        body.pack(fill="both", expand=True)

        msg = (
            f"Item '{item_name}' (Code: {item_code}) is already entered in "
            f"Line #{prev_row_num} with Quantity: {prev_qty:g} {unit}.\n\n"
            f"Would you like to Add this quantity to Line #{prev_row_num} or Ignore this line?"
        )
        tk.Label(
            body,
            text=msg,
            font=theme.F_BODY,
            fg=theme.TEXT_STRONG,
            bg=theme.SURFACE,
            justify="left",
            wraplength=430
        ).pack(anchor="w", pady=(0, 10))

        # Qty input frame
        qty_box = tk.Frame(body, bg=theme.BG, padx=12, pady=8, relief="solid", bd=1)
        qty_box.pack(fill="x", pady=(0, 12))
        tk.Label(
            qty_box,
            text=f"Quantity to Add to Line #{prev_row_num}:",
            font=theme.F_BOLD,
            fg=theme.SLATE_700,
            bg=theme.BG
        ).pack(side="left")

        self.qty_var = tk.StringVar(value=f"{self.add_qty:g}")
        self.qty_entry = tk.Entry(
            qty_box,
            textvariable=self.qty_var,
            font=theme.F_TEXT10B,
            width=8,
            justify="center",
            relief="solid",
            bd=1
        )
        self.qty_entry.pack(side="left", padx=8)
        tk.Label(
            qty_box,
            text=unit,
            font=theme.F_BODY,
            fg=theme.TEXT_MUTED,
            bg=theme.BG
        ).pack(side="left")

        # Button row
        btn_box = tk.Frame(body, bg=theme.SURFACE)
        btn_box.pack(fill="x", pady=(8, 0))

        add_btn = tk.Button(
            btn_box,
            text="➕ Add the QTY (Enter)",
            font=theme.F_BOLD,
            bg="#16a34a",
            fg=theme.SURFACE,
            activebackground="#15803d",
            activeforeground=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._on_add
        )
        add_btn.pack(side="left")

        ignore_btn = tk.Button(
            btn_box,
            text="🗑️ Ignore (Delete Duplicate)",
            font=theme.F_BODY,
            bg=theme.HEADING_BG,
            fg=theme.DANGER,
            activebackground="#fee2e2",
            activeforeground="#b91c1c",
            relief="solid",
            bd=1,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_ignore
        )
        ignore_btn.pack(side="right")

        self.bind("<Return>", lambda e: self._on_add())
        self.bind("<Escape>", lambda e: self._on_ignore())

        self.qty_entry.focus_set()
        self.qty_entry.select_range(0, tk.END)

        self.wait_window()

    def _on_add(self):
        try:
            val = float(self.qty_var.get().strip())
            self.add_qty = val if val > 0 else 1.0
        except ValueError:
            self.add_qty = 1.0
        self.action = "ADD"
        self.destroy()

    def _on_ignore(self):
        self.action = "IGNORE"
        self.destroy()
