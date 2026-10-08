import logging
import os
import subprocess
import tempfile
import platform
import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from app.config.settings import settings
from app.utils.currency import money
from app.models.billing import BillCreate, BillLine
from app.printing.invoice import generate_invoice_pdf
from app.ui.print_preview import show_print_preview
from app.ui.duplicate_dialog import DuplicateItemDialog
from app.services.master_service import MasterService
from app.services.pricing_service import PricingService
from app.utils.currency import format_inr


class BillingFrame(ttk.Frame):
    """Authentic BillDesk POS Billing Terminal matching 04-billing-empty.png, 05, 06, 07."""
    def __init__(self, parent, db, billing, user, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.billing = billing
        self.user = user
        self.master_svc = MasterService(db)
        self.pricing_svc = PricingService(db)

        self.selected_customer = None
        self.selected_company = None
        self.parked_bills_count = 0
        self.row_widgets = []
        self.rows = self.row_widgets
        self.NUM_ROWS = settings.default_num_rows

        self.configure(style="App.TFrame")
        self._build_ui()
        self._bind_hotkeys()
        self._load_defaults()
        self._refresh_parked_label()      # bills parked before a restart are still there

    def _build_ui(self):
        # Outer container with padding matching 04-billing-empty.png
        outer = tk.Frame(self, bg="#f8fafc", padx=16, pady=12)
        outer.pack(fill="both", expand=True)

        # ---------------- 1. SUB-HEADER BAR ----------------
        sub_header = tk.Frame(outer, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=14, pady=10)
        sub_header.pack(fill="x", pady=(0, 10))

        # Billing Company
        tk.Label(sub_header, text="Billing Company:", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        self.company_cbo = ttk.Combobox(sub_header, width=22, state="readonly")
        self.company_cbo.pack(side="left", padx=(0, 16))

        # Doc Type
        tk.Label(sub_header, text="Doc Type:", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        self.doctype_cbo = ttk.Combobox(sub_header, values=["Bill/Invoice", "Estimate", "Delivery Note"], width=14, state="readonly")
        self.doctype_cbo.current(0)
        self.doctype_cbo.pack(side="left", padx=(0, 16))

        # Customer (F5)
        tk.Label(sub_header, text="Customer (F5):", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        cust_search_box = tk.Frame(sub_header, bg="#e2e8f0", padx=1, pady=1)
        cust_search_box.pack(side="left", padx=(0, 16))
        self.customer_var = tk.StringVar(value="Cash")
        self.customer_ent = tk.Entry(cust_search_box, textvariable=self.customer_var, font=("Segoe UI", 9), width=30, relief="flat", bd=0)
        self.customer_ent.pack(side="left", ipady=3, padx=4)
        self.customer_ent.bind("<Button-1>", lambda _e: self._open_customer_search())
        self.customer_ent.bind("<Key>", lambda _e: self._open_customer_search())

        # Date
        tk.Label(sub_header, text="Date:", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        date_box = tk.Frame(sub_header, bg="#e2e8f0", padx=1, pady=1)
        date_box.pack(side="left", padx=(0, 16))
        self.date_ent = tk.Entry(date_box, font=("Segoe UI", 9), width=12, relief="flat", bd=0)
        self.date_ent.insert(0, date.today().strftime("%d/%m/%Y"))
        self.date_ent.pack(side="left", ipady=3, padx=4)

        # Invoice No Tag
        inv_badge = tk.Label(sub_header, text="Inv No: New", font=("Segoe UI", 9, "bold"), fg="#475569", bg="#f1f5f9", padx=12, pady=4)
        inv_badge.pack(side="right")

        # ---------------- 2. SPREADSHEET TABLE GRID (20 ROWS, FULL WIDTH) ----------------
        grid_container = tk.Frame(outer, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        grid_container.pack(fill="both", expand=True, pady=(0, 10))

        # Column definitions: (col_idx, weight, minsize, title, anchor)
        cols_def = [
            (0, 0, 48, "Sno", "center"),
            (1, 1, 110, "Code", "w"),
            (2, 6, 320, "Item Description", "w"),
            (3, 1, 95, "Qty", "e"),
            (4, 1, 95, "Unit", "center"),
            (5, 1, 110, "Rate", "e"),
            (6, 1, 130, "Amount", "e"),
            (7, 0, 42, "", "center")
        ]

        # Table Header Row
        th_frame = tk.Frame(grid_container, bg="#f8fafc", height=34)
        th_frame.pack(fill="x")

        th_scroll_spacer = tk.Frame(th_frame, bg="#f8fafc", width=16)
        th_scroll_spacer.pack(side="right", fill="y")

        th_cols = tk.Frame(th_frame, bg="#f8fafc")
        th_cols.pack(side="left", fill="both", expand=True)

        for col_idx, weight, minsize, title, anchor in cols_def:
            th_cols.grid_columnconfigure(col_idx, weight=weight, minsize=minsize)
            lbl = tk.Label(
                th_cols,
                text=title,
                font=("Segoe UI", 9, "bold"),
                fg="#1e293b",
                bg="#f8fafc",
                anchor=anchor,
                padx=6,
                pady=6
            )
            lbl.grid(row=0, column=col_idx, sticky="nsew")

        # Scrollable table rows canvas
        t_canvas = tk.Canvas(grid_container, bg="#ffffff", highlightthickness=0)
        t_scroll = ttk.Scrollbar(grid_container, orient="vertical", command=t_canvas.yview)
        rows_frame = tk.Frame(t_canvas, bg="#ffffff")

        rows_frame.bind("<Configure>", lambda e: t_canvas.configure(scrollregion=t_canvas.bbox("all")))
        t_win = t_canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        t_canvas.bind("<Configure>", lambda e: t_canvas.itemconfig(t_win, width=e.width))
        t_canvas.configure(yscrollcommand=t_scroll.set)

        t_canvas.pack(side="left", fill="both", expand=True)
        t_scroll.pack(side="right", fill="y")

        self.grid_container = grid_container
        self.cols_def = cols_def
        self.t_canvas = t_canvas
        self.rows_frame = rows_frame
        self.t_scroll = t_scroll

        # Bind mousewheel scrolling
        self.t_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.rows_frame.bind("<MouseWheel>", self._on_mousewheel)

        # Build initial interactive rows filling the line item section
        for i in range(self.NUM_ROWS):
            row_data = self._create_row_widget(i)
            self.row_widgets.append(row_data)

        # ---------------- 3. BOTTOM SUMMARY SECTION ----------------
        # Matches 04-billing-empty.png & 06-billing-filled.png
        summary_bar = tk.Frame(outer, bg="#f8fafc")
        summary_bar.pack(fill="x", pady=(0, 10))

        # Card 1: Customer Delivery
        card_delivery = tk.Frame(summary_bar, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=10, width=260, height=85)
        card_delivery.pack(side="left", padx=(0, 10))
        card_delivery.pack_propagate(False)

        self.deliv_name_lbl = tk.Label(card_delivery, text="Customer (Delivery): Cash", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff", anchor="w")
        self.deliv_name_lbl.pack(fill="x")
        self.deliv_addr_lbl = tk.Label(card_delivery, text="Cash Customer", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff", anchor="w")
        self.deliv_addr_lbl.pack(fill="x")
        self.deliv_phone_lbl = tk.Label(card_delivery, text="", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff", anchor="w")
        self.deliv_phone_lbl.pack(fill="x")

        # Card 2: Bill To
        card_billto = tk.Frame(summary_bar, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=10, width=260, height=85)
        card_billto.pack(side="left", padx=(0, 10))
        card_billto.pack_propagate(False)

        tk.Label(card_billto, text="Bill To:", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff", anchor="w").pack(fill="x")
        self.billto_lbl = tk.Label(card_billto, text="-", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff", anchor="w")
        self.billto_lbl.pack(fill="x")

        # Card 3: Internal Notes (Light Yellow Box)
        card_notes = tk.Frame(summary_bar, bg="#fffbeb", highlightbackground="#fef3c7", highlightthickness=1, padx=12, pady=8, width=340, height=85)
        card_notes.pack(side="left", padx=(0, 10))
        card_notes.pack_propagate(False)

        tk.Label(card_notes, text="Internal Notes:", font=("Segoe UI", 9, "bold"), fg="#92400e", bg="#fffbeb", anchor="w").pack(fill="x")
        self.notes_ent = tk.Entry(card_notes, font=("Segoe UI", 8), bg="#fffbeb", fg="#78350f", relief="flat", bd=0)
        self.notes_ent.insert(0, "Add internal notes...")
        self.notes_ent.pack(fill="x", pady=(4, 0))

        # Far Right: Massive Total Display
        total_box = tk.Frame(summary_bar, bg="#f8fafc", padx=16)
        total_box.pack(side="right", fill="y")
        self.total_lbl = tk.Label(total_box, text="Total: ₹0.00", font=("Segoe UI", 22, "bold"), fg="#15803d", bg="#f8fafc")
        self.total_label = self.total_lbl
        self.total_lbl.pack(side="right", pady=16)

        # ---------------- 4. ACTION BUTTONS (BOTTOM RIGHT) ----------------
        # Matches Park (F6) and Parked (0) (F7) docked to the right
        btn_bar = tk.Frame(outer, bg="#f8fafc")
        btn_bar.pack(fill="x", side="bottom")

        self.parked_list_btn = tk.Button(
            btn_bar,
            text="📥 Parked (0) (F7)",
            font=("Segoe UI", 9, "bold"),
            bg="#3b82f6",
            fg="#ffffff",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._open_parked_modal
        )
        self.parked_list_btn.pack(side="right", padx=(6, 0))

        self.park_btn = tk.Button(
            btn_bar,
            text="🗂️ Park (F6)",
            font=("Segoe UI", 9, "bold"),
            bg="#f59e0b",
            fg="#ffffff",
            activebackground="#d97706",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self.park_bill
        )
        self.park_btn.pack(side="right", padx=(0, 6))

    def _bind_hotkeys(self):
        self.bind_all("<F5>", lambda _e: self._open_customer_search())
        self.bind_all("<F6>", lambda _e: self.park_bill())
        self.bind_all("<F7>", lambda _e: self._open_parked_modal())

    def _load_defaults(self):
        # Load companies
        try:
            comps = list(self.db.collection("companies").find())
            self._companies_list = comps
            names = [c["name"] for c in comps if "name" in c] or [settings.default_company_name]
            self.company_cbo["values"] = names
            self.company_cbo.current(0)
        except Exception:
            self._companies_list = []
            self.company_cbo["values"] = [settings.default_company_name]
            self.company_cbo.current(0)

        # Focus on first row's code entry
        if self.row_widgets:
            self.row_widgets[0]["code"].focus_set()

    def _on_mousewheel(self, event):
        if hasattr(self, "t_canvas") and event.delta:
            self.t_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _create_row_widget(self, row_idx: int) -> dict:
        row_f = tk.Frame(self.rows_frame, bg="#ffffff", height=32)
        row_f.pack(fill="x", expand=True, pady=1)

        for col_idx, weight, minsize, title, anchor in self.cols_def:
            row_f.grid_columnconfigure(col_idx, weight=weight, minsize=minsize)

        # Sno
        sno_lbl = tk.Label(row_f, text=str(row_idx + 1), font=("Segoe UI", 9), fg="#64748b", bg="#ffffff", anchor="center")
        sno_lbl.grid(row=0, column=0, sticky="nsew", padx=1, pady=2)

        # Code
        c_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        c_box.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        code_ent = tk.Entry(c_box, font=("Segoe UI", 9), width=5, relief="flat", bd=0)
        code_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # Item Description (stretches to fill table)
        d_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        d_box.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        name_ent = tk.Entry(d_box, font=("Segoe UI", 9), width=10, relief="flat", bd=0)
        name_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # Qty
        q_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        q_box.grid(row=0, column=3, sticky="nsew", padx=2, pady=2)
        qty_ent = tk.Entry(q_box, font=("Segoe UI", 9), width=5, relief="flat", bd=0, justify="right")
        qty_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # Unit
        unit_cbo = ttk.Combobox(
            row_f,
            values=["Kg", "Nos", "Bunch", "Pkt", "Box", "Bag", "Dz", "Gm", "Crate"],
            width=5
        )
        unit_cbo.grid(row=0, column=4, sticky="nsew", padx=2, pady=2)

        # Rate
        r_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        r_box.grid(row=0, column=5, sticky="nsew", padx=2, pady=2)
        rate_ent = tk.Entry(r_box, font=("Segoe UI", 9), width=5, relief="flat", bd=0, justify="right")
        rate_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # Amount
        amt_lbl = tk.Label(row_f, text="₹0.00", font=("Segoe UI", 9, "bold"), fg="#0f172a", bg="#ffffff", anchor="e", padx=4)
        amt_lbl.grid(row=0, column=6, sticky="nsew", padx=2, pady=2)

        # Red Delete Button [X]
        del_btn = tk.Button(
            row_f,
            text="✕",
            font=("Segoe UI", 8, "bold"),
            fg="#ffffff",
            bg="#ef4444",
            activebackground="#dc2626",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=lambda r=row_idx: self._delete_row_and_shift_up(r)
        )
        del_btn.grid(row=0, column=7, sticky="nsew", padx=2, pady=2)

        # Event Bindings for Spreadsheet Interactivity
        code_ent.bind("<Return>", lambda e, r=row_idx: self._on_code_entered(r))
        code_ent.bind("<FocusOut>", lambda e, r=row_idx: self._on_code_entered(r, focus_next=False))
        qty_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._recalculate_row(r))
        qty_ent.bind("<Return>", lambda e, r=row_idx: self._on_qty_entered(r))
        unit_cbo.bind("<Return>", lambda e, r=row_idx: self._on_unit_entered(r))
        unit_cbo.bind("<<ComboboxSelected>>", lambda e, r=row_idx: self._on_unit_entered(r))
        rate_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._recalculate_row(r))
        rate_ent.bind("<Return>", lambda e, r=row_idx: self._on_rate_entered(r))

        # Mouse wheel binding on all widgets of the row
        for w in (row_f, sno_lbl, code_ent, name_ent, qty_ent, unit_cbo, rate_ent, amt_lbl, del_btn):
            w.bind("<MouseWheel>", self._on_mousewheel, add="+")

        return {
            "sno": sno_lbl,
            "code": code_ent,
            "name": name_ent,
            "qty": qty_ent,
            "unit": unit_cbo,
            "rate": rate_ent,
            "amount": amt_lbl,
            "del_btn": del_btn,
            "item_id": None,
            "frame": row_f,
        }

    def _add_row(self) -> int:
        new_idx = len(self.row_widgets)
        row_data = self._create_row_widget(new_idx)
        self.row_widgets.append(row_data)
        self.rows_frame.update_idletasks()
        self.t_canvas.configure(scrollregion=self.t_canvas.bbox("all"))
        return new_idx

    def _scroll_to_row(self, row_idx: int):
        try:
            if row_idx < 0 or row_idx >= len(self.row_widgets):
                return
            self.rows_frame.update_idletasks()
            total_rows = len(self.row_widgets)
            if total_rows > 0:
                fraction = max(0.0, min(1.0, row_idx / total_rows))
                self.t_canvas.yview_moveto(fraction)
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

    # ---------------- SPREADSHEET ROW LOGIC ----------------
    def _on_code_entered(self, row_idx: int, focus_next: bool = True):
        if row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        code = row["code"].get().strip()
        if not code:
            return

        # Leaving/re-entering an already-resolved code must not re-resolve the line: that would overwrite
        # a rate or quantity the cashier has typed since.
        if row.get("item_id"):
            cur = self.db.collection("items").find_one({"item_id": row["item_id"]})
            if cur and code.lower() in (str(cur.get("item_alias", "")).lower(), str(cur.get("item_id", "")).lower()):
                if focus_next:
                    row["qty"].focus_set()
                    row["qty"].select_range(0, tk.END)
                return

        # Query item by item_alias or item_id or name prefix
        escaped_code = re.escape(code)
        item = self.db.collection("items").find_one({
            "$or": [
                {"item_alias": code},
                {"item_id": code},
                {"item_alias": {"$regex": f"^{escaped_code}$", "$options": "i"}},
                {"item_id": {"$regex": f"^{escaped_code}$", "$options": "i"}},
                {"name": {"$regex": f"^{escaped_code}", "$options": "i"}}
            ],
            "status": "active",
            "is_deleted": 0
        })

        if not item:
            # Fallback search by case-insensitive name contains
            item = self.db.collection("items").find_one({
                "name": {"$regex": escaped_code, "$options": "i"},
                "is_deleted": 0
            })
            if not item:
                messagebox.showwarning("Item Not Found", f"No item matches code or name '{code}'.", parent=self)
                row["code"].delete(0, tk.END)
                row["code"].focus_set()
                return

        row["item_id"] = item["item_id"]
        row["code"].delete(0, tk.END)
        row["code"].insert(0, item.get("item_alias") or item["item_id"])

        row["name"].delete(0, tk.END)
        row["name"].insert(0, item.get("name", ""))

        # Fetch default unit from item master
        unit = item.get("unit") or "Kg"
        vals = list(row["unit"]["values"])
        if unit not in vals:
            vals.append(unit)
            row["unit"]["values"] = vals
        row["unit"].set(unit)

        # Resolve rate (Fixed pricing for customer takes priority!)
        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"
        default_rate = float(item.get("standard_rate") or item.get("rate") or item.get("default_rate") or settings.default_rate)
        resolved_rate, _is_fixed = self.pricing_svc.resolve_rate(cust_id, item["item_id"], default_rate=default_rate)
        row["rate"].delete(0, tk.END)
        row["rate"].insert(0, f"{resolved_rate:.2f}")

        # Set default Qty to 1 if empty
        if not row["qty"].get().strip():
            row["qty"].insert(0, "1")

        self._recalculate_row(row_idx)

        # Check duplicate item in prior rows
        if self._check_and_handle_duplicate(row_idx):
            return

        if focus_next:
            row["qty"].focus_set()
            row["qty"].select_range(0, tk.END)

    def _find_duplicate_row(self, row_idx: int) -> Optional[int]:
        if row_idx <= 0 or row_idx >= len(self.row_widgets):
            return None
        curr_row = self.row_widgets[row_idx]
        curr_id = curr_row.get("item_id")
        curr_code = curr_row["code"].get().strip().lower()
        if not curr_id and not curr_code:
            return None
        for k in range(row_idx):
            r = self.row_widgets[k]
            k_id = r.get("item_id")
            k_code = r["code"].get().strip().lower()
            if (curr_id and k_id and k_id == curr_id) or (curr_code and k_code and k_code == curr_code):
                return k
        return None

    def resolve_duplicate(self, row_idx: int, action: str = "ADD", add_qty: Optional[float] = None) -> bool:
        """
        Resolves duplicate item in row_idx.
        If action == 'ADD', adds add_qty (defaults to current row qty) to prior item row,
        recalculates row amount and grand total, and deletes duplicate row.
        If action == 'IGNORE', deletes duplicate row and recalculates grand total.
        """
        dup_idx = self._find_duplicate_row(row_idx)
        if dup_idx is None:
            return False

        curr_row = self.row_widgets[row_idx]
        prev_row = self.row_widgets[dup_idx]

        if add_qty is None:
            try:
                curr_q = float(curr_row["qty"].get().strip() or "1")
            except ValueError:
                curr_q = 1.0
            add_qty = curr_q

        if action.upper() == "ADD":
            try:
                prev_q = float(prev_row["qty"].get().strip() or "0")
            except ValueError:
                prev_q = 0.0
            new_q = prev_q + add_qty
            prev_row["qty"].delete(0, tk.END)
            prev_row["qty"].insert(0, f"{new_q:g}")
            self._recalculate_row(dup_idx)
            self._delete_row_and_shift_up(row_idx)
            self._update_grand_total()
            prev_row["qty"].focus_set()
        else:  # IGNORE
            self._delete_row_and_shift_up(row_idx)
            self._update_grand_total()
            if row_idx < len(self.row_widgets):
                self.row_widgets[row_idx]["code"].focus_set()

        return True

    def _check_and_handle_duplicate(self, row_idx: int) -> bool:
        if getattr(self, "suppress_duplicate_dialog", False):
            return False

        dup_idx = self._find_duplicate_row(row_idx)
        if dup_idx is None:
            return False

        curr_row = self.row_widgets[row_idx]
        prev_row = self.row_widgets[dup_idx]

        try:
            prev_q = float(prev_row["qty"].get().strip() or "0")
        except ValueError:
            prev_q = 0.0

        try:
            curr_q = float(curr_row["qty"].get().strip() or "1")
        except ValueError:
            curr_q = 1.0

        item_name = prev_row["name"].get().strip() or curr_row["name"].get().strip()
        item_code = prev_row["code"].get().strip() or curr_row["code"].get().strip()
        unit = prev_row["unit"].get() or "Kg"

        dlg = DuplicateItemDialog(
            parent=self,
            item_name=item_name,
            item_code=item_code,
            prev_row_num=dup_idx + 1,
            prev_qty=prev_q,
            curr_qty=curr_q,
            unit=unit
        )
        return self.resolve_duplicate(row_idx, action=dlg.action, add_qty=dlg.add_qty)

    def _on_qty_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        self._recalculate_row(row_idx)
        if self._check_and_handle_duplicate(row_idx):
            return
        # Advance focus to Unit field
        row = self.row_widgets[row_idx]
        row["unit"].focus_set()

    def _on_unit_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        self._recalculate_row(row_idx)
        # Advance focus to Rate field and select existing text
        row = self.row_widgets[row_idx]
        row["rate"].focus_set()
        row["rate"].select_range(0, tk.END)

    def _recalculate_row(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        try:
            qty_str = row["qty"].get().strip()
            qty = float(qty_str) if qty_str else 0.0
        except (ValueError, TypeError):
            qty = 0.0

        try:
            rate_str = row["rate"].get().strip()
            rate = float(rate_str) if rate_str else 0.0
        except (ValueError, TypeError):
            rate = 0.0

        amount = money(qty * rate) if (qty > 0 and rate >= 0) else 0.0     # invalid rows never count
        row["amount"].config(text=f"₹{amount:.2f}")
        self._update_grand_total()

    def _is_row_empty(self, row_idx: int) -> bool:
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return True
        row = self.row_widgets[row_idx]
        code = row["code"].get().strip()
        name = row["name"].get().strip()
        item_id = row.get("item_id")
        return not code and not name and not item_id

    def _compact_row_gap(self, row_idx: int) -> int:
        """
        If there is any gap above row_idx (an empty row among 0..row_idx-1),
        move the item from row_idx to the first empty row (N+1 position).
        Returns the target row index where the item now resides.
        """
        if row_idx <= 0 or row_idx >= len(self.row_widgets):
            return row_idx

        # If current row is empty, nothing to compact
        if self._is_row_empty(row_idx):
            return row_idx

        # Find the first empty row above row_idx
        first_empty_idx = None
        for k in range(row_idx):
            if self._is_row_empty(k):
                first_empty_idx = k
                break

        if first_empty_idx is None:
            # No gap above, item stays at row_idx
            return row_idx

        # Move item from row_idx to first_empty_idx
        src = self.row_widgets[row_idx]
        dest = self.row_widgets[first_empty_idx]

        dest["item_id"] = src.get("item_id")

        dest["code"].delete(0, tk.END)
        dest["code"].insert(0, src["code"].get())

        dest["name"].delete(0, tk.END)
        dest["name"].insert(0, src["name"].get())

        dest["qty"].delete(0, tk.END)
        dest["qty"].insert(0, src["qty"].get())

        dest["unit"].set(src["unit"].get())

        dest["rate"].delete(0, tk.END)
        dest["rate"].insert(0, src["rate"].get())

        # Clear the source row
        self._clear_row(row_idx)

        # Recalculate the destination row
        self._recalculate_row(first_empty_idx)

        return first_empty_idx

    def _on_rate_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        if self._is_row_empty(row_idx):
            return

        if self._check_and_handle_duplicate(row_idx):
            return

        self._recalculate_row(row_idx)

        # Compact any gap above this row
        target_idx = self._compact_row_gap(row_idx)

        # Advance to the first empty row at or after target_idx + 1
        next_row_idx = target_idx + 1
        while next_row_idx < len(self.row_widgets) and not self._is_row_empty(next_row_idx):
            next_row_idx += 1

        if next_row_idx >= len(self.row_widgets):
            self._add_row()

        if next_row_idx < len(self.row_widgets):
            next_row = self.row_widgets[next_row_idx]
            next_row["code"].focus_set()
            next_row["code"].select_range(0, tk.END)
            self._scroll_to_row(next_row_idx)

    def _delete_row_and_shift_up(self, row_idx: int):
        """Clear row and shift all subsequent rows up to maintain contiguous list."""
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return

        # Shift all subsequent rows up by one position
        for k in range(row_idx, len(self.row_widgets) - 1):
            next_row = self.row_widgets[k + 1]
            curr_row = self.row_widgets[k]

            curr_row["code"].delete(0, tk.END)
            curr_row["code"].insert(0, next_row["code"].get())

            curr_row["name"].delete(0, tk.END)
            curr_row["name"].insert(0, next_row["name"].get())

            curr_row["qty"].delete(0, tk.END)
            curr_row["qty"].insert(0, next_row["qty"].get())

            curr_row["unit"].set(next_row["unit"].get())

            curr_row["rate"].delete(0, tk.END)
            curr_row["rate"].insert(0, next_row["rate"].get())

            curr_row["item_id"] = next_row.get("item_id")
            self._recalculate_row(k)

        # Clear the last row
        last_idx = len(self.row_widgets) - 1
        self._clear_row(last_idx)
        self._update_grand_total()

    def _clear_row(self, row_idx: int):
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        row["code"].delete(0, tk.END)
        row["name"].delete(0, tk.END)
        row["qty"].delete(0, tk.END)
        row["unit"].set("")
        row["rate"].delete(0, tk.END)
        row["amount"].config(text="₹0.00")
        row["item_id"] = None
        self._update_grand_total()

    def _update_grand_total(self) -> float:
        total = 0.0
        for row in self.row_widgets:
            try:
                qty_str = row["qty"].get().strip()
                rate_str = row["rate"].get().strip()
                qty = float(qty_str) if qty_str else 0.0
                rate = float(rate_str) if rate_str else 0.0
                if qty > 0 and rate >= 0:
                    total += money(qty * rate)
            except Exception:
                logging.getLogger(__name__).warning("Ignored error", exc_info=True)
        self.total_lbl.config(text=f"Total: ₹{total:.2f}")
        return total

    # ---------------- CUSTOMER SEARCH MODAL (F5) ----------------
    # Matches 05-billing-customer-search.png
    def _open_customer_search(self):
        modal = tk.Toplevel(self)
        modal.title("Select Customer (F5)")
        modal.geometry("500x380")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        # Center on screen
        sw = modal.winfo_screenwidth()
        sh = modal.winfo_screenheight()
        modal.geometry(f"500x380+{(sw-500)//2}+{(sh-380)//2}")

        frame = tk.Frame(modal, bg="#ffffff", padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        top_bar = tk.Frame(frame, bg="#ffffff")
        top_bar.pack(fill="x", pady=(0, 12))
        tk.Label(top_bar, text="Select Customer (F5)", font=("Segoe UI", 12, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left")
        tk.Button(top_bar, text="✕", font=("Segoe UI", 10), bg="#ffffff", fg="#64748b", relief="flat", bd=0, command=modal.destroy).pack(side="right")

        # Search Entry with border
        s_box = tk.Frame(frame, bg="#3b82f6", padx=1, pady=1)
        s_box.pack(fill="x", pady=(0, 12))
        search_ent = tk.Entry(s_box, font=("Segoe UI", 11), relief="flat", bd=0)
        search_ent.pack(fill="x", ipady=6, padx=8)
        search_ent.focus_set()

        # List Container
        list_canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=1, highlightbackground="#e2e8f0")
        list_scroll = ttk.Scrollbar(frame, orient="vertical", command=list_canvas.yview)
        cards_box = tk.Frame(list_canvas, bg="#ffffff")

        cards_box.bind("<Configure>", lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        c_win = list_canvas.create_window((0, 0), window=cards_box, anchor="nw")
        list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfig(c_win, width=e.width))
        list_canvas.configure(yscrollcommand=list_scroll.set)

        list_canvas.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")

        customers = list(self.db.collection("customers").find({"is_deleted": 0}))

        def _render_customers(query=""):
            for w in cards_box.winfo_children():
                w.destroy()

            # Always offer Walk-in / Cash option
            if not query or "cash" in query.lower():
                c_card = tk.Frame(cards_box, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=8, cursor="hand2")
                c_card.pack(fill="x", pady=3, padx=4)
                tk.Label(c_card, text="Cash Customer", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")
                tk.Label(c_card, text="Counter Walk-in Sale", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff").pack(anchor="w")
                c_card.bind("<Button-1>", lambda _e: _pick_customer(None))

            q_lower = query.lower()
            matched = [
                c for c in customers
                if q_lower in c.get("name", "").lower()
                or q_lower in str(c.get("bill_to_name", "")).lower()
                or query in str(c.get("phone", ""))
                or query in str(c.get("contact_person_phone", ""))
                or query in str(c.get("bill_to_phone", ""))
            ]
            for cust in matched:
                c_card = tk.Frame(cards_box, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=12, pady=8, cursor="hand2")
                c_card.pack(fill="x", pady=3, padx=4)
                tk.Label(c_card, text=cust.get("name", ""), font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")

                bname = cust.get("bill_to_name")
                bname_str = f"Bill To: {bname}  |  " if (bname and bname != cust.get("name")) else ""
                phone_str = cust.get("contact_person_phone") or cust.get("phone") or cust.get("bill_to_phone") or "-"
                gst_str = cust.get("gst_number", "")
                gst_part = f"  |  GST: {gst_str}" if gst_str else ""
                tk.Label(c_card, text=f"{bname_str}{phone_str}{gst_part}", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff").pack(anchor="w")

                c_card.bind("<Button-1>", lambda _e, cu=cust: _pick_customer(cu))

        def _pick_customer(cust):
            self.selected_customer = cust
            if cust:
                self.customer_var.set(cust.get("name", "Cash"))
                self.deliv_name_lbl.config(text=f"Customer (Delivery): {cust.get('name')}")
                addr = cust.get("address") or cust.get("bill_to_address") or "-"
                phone = cust.get("contact_person_phone") or cust.get("phone") or cust.get("bill_to_phone") or ""
                self.deliv_addr_lbl.config(text=addr)
                self.deliv_phone_lbl.config(text=phone)
                bill_to = cust.get("bill_to_name") or cust.get("name", "-")
                self.billto_lbl.config(text=bill_to)

                # Auto-select company in company_cbo if matching company_id
                target_comp_id = cust.get("company_id")
                if target_comp_id and hasattr(self, "_companies_list"):
                    for idx, c in enumerate(self._companies_list):
                        if c.get("company_id") == target_comp_id:
                            self.company_cbo.current(idx)
                            break
            else:
                self.customer_var.set("Cash")
                self.deliv_name_lbl.config(text="Customer (Delivery): Cash")
                self.deliv_addr_lbl.config(text="Cash Customer")
                self.deliv_phone_lbl.config(text="")
                self.billto_lbl.config(text="-")

            # Re-resolve rates for any rows already entered!
            cust_id = cust.get("cust_id") if cust else "CASH"
            for r_idx, row in enumerate(self.row_widgets):
                if row.get("item_id"):
                    item_id = row["item_id"]
                    item = self.db.collection("items").find_one({"item_id": item_id})
                    default_rate = float(item.get("standard_rate") or item.get("rate") or item.get("default_rate") or settings.default_rate) if item else settings.default_rate
                    r_rate, _ = self.pricing_svc.resolve_rate(cust_id, item_id, default_rate=default_rate)
                    row["rate"].delete(0, tk.END)
                    row["rate"].insert(0, f"{r_rate:.2f}")
                    self._recalculate_row(r_idx)

            modal.destroy()

        search_ent.bind("<KeyRelease>", lambda _e: _render_customers(search_ent.get().strip()))
        _render_customers()

    # ---------------- BILL SAVING & PAYMENT RECEIPT MODAL (F2 / F3) ----------------
    # Matches 07-billing-payment.png
    def _on_f2_save(self):
        self._open_payment_modal(print_pdf=False)

    def _on_f3_save_print(self):
        self._open_payment_modal(print_pdf=True)

    def _open_payment_modal(self, print_pdf: bool = False):
        total_amount = self._update_grand_total()
        if total_amount <= 0:
            messagebox.showwarning("Empty Bill", "Please add at least one line item before saving.", parent=self)
            return

        modal = tk.Toplevel(self)
        modal.title("Record Payment Receipt")
        modal.geometry("640x520")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        sw = modal.winfo_screenwidth()
        sh = modal.winfo_screenheight()
        modal.geometry(f"640x520+{(sw-640)//2}+{(sh-520)//2}")

        frame = tk.Frame(modal, bg="#ffffff", padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        # Header with close X
        h_box = tk.Frame(frame, bg="#ffffff")
        h_box.pack(fill="x", pady=(0, 16))
        tk.Label(h_box, text="Record Payment Receipt", font=("Segoe UI", 14, "bold"), fg="#0f172a", bg="#ffffff").pack(side="left")
        tk.Button(h_box, text="✕", font=("Segoe UI", 10), bg="#ffffff", fg="#64748b", relief="flat", bd=0, command=modal.destroy).pack(side="right")

        # Top section: 2 columns
        grid_two = tk.Frame(frame, bg="#ffffff")
        grid_two.pack(fill="x", pady=(0, 16))

        # Left Box (Customer Info)
        left_box = tk.Frame(grid_two, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=14, pady=12, width=280)
        left_box.pack(side="left", fill="both", expand=True, padx=(0, 8))

        if self.selected_customer is None:
            tk.Label(left_box, text="Walk-in counter sale", font=("Segoe UI", 9, "bold"), fg="#475569", bg="#ffffff").pack(anchor="w", pady=(0, 8))

        tk.Label(left_box, text="Customer", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        cust_name_str = self.selected_customer.get("name") if self.selected_customer else "Cash"
        tk.Label(left_box, text=cust_name_str, font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#f1f5f9", padx=8, pady=4).pack(fill="x", pady=(2, 12))

        unpaid_count = 0
        cur_bal = 0.0
        if self.selected_customer:
            fresh = self.db.collection("customers").find_one({"cust_id": self.selected_customer.get("cust_id")}) or self.selected_customer
            cur_bal = float(fresh.get("current_balance", 0.0) or 0.0)
            unpaid_count = self.db.collection("bills").count_documents({
                "customer_id": self.selected_customer.get("cust_id"), "status": {"$in": ["unpaid", "partial"]}, "is_deleted": 0})
        bal_row = tk.Frame(left_box, bg="#ffffff")
        bal_row.pack(fill="x")
        tk.Label(bal_row, text=f"OUTSTANDING\n₹{cur_bal:.2f}", font=("Segoe UI", 8, "bold"), fg="#475569", bg="#ffffff", justify="left").pack(side="left")
        tk.Label(bal_row, text=f"UNPAID BILLS\n{unpaid_count}", font=("Segoe UI", 8, "bold"), fg="#475569", bg="#ffffff", justify="left").pack(side="right")

        # Right Box (Payment Details)
        right_box = tk.Frame(grid_two, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=14, pady=12, width=280)
        right_box.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Label(right_box, text="Amount Received", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=0, column=0, sticky="w")
        tk.Label(right_box, text="Payment Date", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=0, column=1, sticky="w", padx=(10, 0))

        amt_box = tk.Frame(right_box, bg="#cbd5e1", padx=1, pady=1)
        amt_box.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        amt_rec_ent = tk.Entry(amt_box, font=("Segoe UI", 12, "bold"), width=12, relief="flat", bd=0)
        amt_rec_ent.insert(0, f"{total_amount:.0f}")
        amt_rec_ent.pack(fill="both", ipady=4, padx=4)

        date_box = tk.Frame(right_box, bg="#cbd5e1", padx=1, pady=1)
        date_box.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(2, 10))
        pay_date_ent = tk.Entry(date_box, font=("Segoe UI", 10), width=12, relief="flat", bd=0)
        pay_date_ent.insert(0, date.today().strftime("%d - %m - %Y"))
        pay_date_ent.pack(fill="both", ipady=4, padx=4)

        tk.Label(right_box, text="Payment Method", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=2, column=0, sticky="w")
        tk.Label(right_box, text="Reference / UTR", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").grid(row=2, column=1, sticky="w", padx=(10, 0))

        method_cbo = ttk.Combobox(right_box, values=["Cash", "UPI", "Cheque", "NEFT/RTGS", "Credit/Due"], state="readonly", width=12)
        method_cbo.current(0)
        method_cbo.grid(row=3, column=0, sticky="ew", pady=(2, 0))

        utr_box = tk.Frame(right_box, bg="#cbd5e1", padx=1, pady=1)
        utr_box.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(2, 0))
        utr_ent = tk.Entry(utr_box, font=("Segoe UI", 10), width=12, relief="flat", bd=0)
        utr_ent.insert(0, "NEW")
        utr_ent.pack(fill="both", ipady=4, padx=4)

        # Payment Allocation Box
        alloc_box = tk.Frame(frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=14, pady=12)
        alloc_box.pack(fill="x", pady=(0, 20))

        alloc_h = tk.Frame(alloc_box, bg="#ffffff")
        alloc_h.pack(fill="x", pady=(0, 8))
        tk.Label(alloc_h, text="Payment Allocation", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left")


        # Info tip
        tip_box = tk.Frame(alloc_box, bg="#eff6ff", padx=10, pady=8)
        tip_box.pack(fill="x")
        tk.Label(tip_box, text="ⓘ  The amount received is applied to this bill. Any balance stays outstanding on the customer account.", font=("Segoe UI", 8), fg="#1e40af", bg="#eff6ff").pack(anchor="w")

        # Bottom buttons: Cancel and Post Payment
        bot_btns = tk.Frame(frame, bg="#ffffff")
        bot_btns.pack(fill="x", side="bottom")

        def _execute_post():
            pay_method = method_cbo.get()
            raw_amt = amt_rec_ent.get().strip().replace(",", "")
            try:
                rec_amount = float(raw_amt) if raw_amt else 0.0
            except ValueError:
                messagebox.showerror("Invalid Amount", f"'{amt_rec_ent.get()}' is not a valid amount received.", parent=modal)
                amt_rec_ent.focus_set()
                return
            if rec_amount < 0 or rec_amount != rec_amount:
                messagebox.showerror("Invalid Amount", "Amount received cannot be negative.", parent=modal)
                amt_rec_ent.focus_set()
                return
            if rec_amount - total_amount > 0.005:
                messagebox.showerror(
                    "Invalid Amount",
                    f"Amount received (₹{rec_amount:.2f}) is more than the bill total (₹{total_amount:.2f}).",
                    parent=modal,
                )
                amt_rec_ent.focus_set()
                return
            if pay_method == "Credit/Due":
                rec_amount = 0.0
            pay_ref = utr_ent.get().strip()
            if pay_ref.upper() == "NEW":   # untouched placeholder
                pay_ref = ""
            # Construct line items
            lines = []
            problems = []
            for r_idx, row in enumerate(self.row_widgets, 1):
                code = row["code"].get().strip()
                if not code:
                    continue
                label = f"Row {r_idx} ({row['name'].get().strip() or code})"
                try:
                    qty = float(row["qty"].get().strip())
                except ValueError:
                    problems.append(f"{label}: quantity is not a number")
                    continue
                try:
                    rate = float(row["rate"].get().strip())
                except ValueError:
                    problems.append(f"{label}: rate is not a number")
                    continue
                if qty <= 0:
                    problems.append(f"{label}: quantity must be greater than zero")
                    continue
                if rate < 0:
                    problems.append(f"{label}: rate cannot be negative")
                    continue

                lines.append(BillLine(
                    item_id=row.get("item_id") or code,
                    name=row["name"].get().strip() or "Produce",
                    qty=qty,
                    unit=row["unit"].get() or "kg",
                    rate=rate,
                    amount=money(qty * rate)
                ))

            if problems:
                messagebox.showerror("Fix These Lines", "The bill was not saved:\n\n" + "\n".join(problems), parent=modal)
                return

            if not lines:
                messagebox.showerror("Error", "No valid items to bill.", parent=modal)
                return

            cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"
            cust_name = self.selected_customer.get("name") if self.selected_customer else "Cash Customer"

            # Resolve selected company_id
            sel_comp_name = self.company_cbo.get()
            sel_comp_id = "Company0001"
            if hasattr(self, "_companies_list"):
                for c in self._companies_list:
                    if c.get("name") == sel_comp_name:
                        sel_comp_id = c.get("company_id", "Company0001")
                        break

            # Create bill
            bill_in = BillCreate(
                invoice_date=datetime.now().strftime("%Y-%m-%d"),
                customer_id=cust_id,
                customer_name=cust_name,
                company_id=sel_comp_id,
                items=lines,
                total_amount=money(sum(l.amount for l in lines)),
                balance_due=max(0.0, total_amount - rec_amount),
                amount_received=rec_amount,
                payment_method=pay_method,
                payment_reference=pay_ref or None,
                created_by=self.user.username
            )

            try:
                saved = self.billing.create_bill(bill_in)
                invoice_no = saved["invoice_no"]
                modal.destroy()

                # Generate PDF if requested
                if print_pdf:
                    self._generate_and_open_pdf(saved)

                messagebox.showinfo("Bill Saved", f"Invoice #{invoice_no} generated successfully!\nTotal: ₹{total_amount:.2f}", parent=self)
                self._reset_bill()

            except Exception as e:
                messagebox.showerror("Failed to Save Bill", str(e), parent=modal)

        tk.Button(
            bot_btns,
            text="Post Payment",
            font=("Segoe UI", 10, "bold"),
            bg="#5b54d6",
            fg="#ffffff",
            activebackground="#4a43c2",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=20,
            pady=8,
            cursor="hand2",
            command=_execute_post
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            bot_btns,
            text="Cancel",
            font=("Segoe UI", 10),
            bg="#f1f5f9",
            fg="#475569",
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            command=modal.destroy
        ).pack(side="right")

    def _generate_and_open_pdf(self, bill_data: dict):
        try:
            inv_no = bill_data.get("invoice_no", "bill")
            out_dir = os.path.abspath("Docs/Output")
            os.makedirs(out_dir, exist_ok=True)
            pdf_path = os.path.join(out_dir, f"Inv- {inv_no}.pdf")

            comp = self.master_svc.get_company(bill_data.get("company_id"))
            cust = self.selected_customer
            generate_invoice_pdf(pdf_path, bill_data, company=comp, customer=cust)
            show_print_preview(
                self,
                pdf_path,
                title=f"Invoice — {inv_no}",
                default_filename=f"Inv- {inv_no}.pdf"
            )
        except Exception as e:
            messagebox.showwarning("Print Preview", f"Could not generate/preview PDF:\n{e}", parent=self)

    # ---------------- PARK & RECALL (F6 / F7) ----------------
    def _refresh_parked_label(self):
        self.parked_bills_count = len(self.billing.get_parked_bills())
        self.parked_list_btn.config(text=f"📥 Parked ({self.parked_bills_count}) (F7)")

    def _grid_has_items(self) -> bool:
        return any(r["code"].get().strip() for r in self.row_widgets)

    def park_bill(self):
        """Park the current bill; it is saved to disk so it survives closing or crashing the app."""
        total = self._update_grand_total()
        if total <= 0:
            return

        lines = []
        for row in self.row_widgets:
            code = row["code"].get().strip()
            if code:
                lines.append({
                    "code": code,
                    "item_id": row.get("item_id"),
                    "name": row["name"].get(),
                    "qty": row["qty"].get(),
                    "unit": row["unit"].get(),
                    "rate": row["rate"].get(),
                })

        park_data = {
            "customer": self.selected_customer,
            "company": self.company_cbo.get(),
            "lines": lines,
            "total": total,
            "parked_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "parked_by": self.user.username
        }
        try:
            self.billing.park_bill(park_data)
        except OSError as ex:
            messagebox.showerror("Could Not Park Bill", f"The bill was NOT parked (cannot write the parked-bills file):\n{ex}", parent=self)
            return
        self._refresh_parked_label()
        self._reset_bill()
        messagebox.showinfo("Bill Parked", f"Bill parked successfully. Current parked: {self.parked_bills_count}", parent=self)

    def _open_parked_modal(self):
        parked = self.billing.get_parked_bills()
        if not parked:
            messagebox.showinfo("Parked Bills", "No parked bills found.", parent=self)
            return

        modal = tk.Toplevel(self)
        modal.title("Recall Parked Bill (F7)")
        modal.geometry("450x320")
        sw = modal.winfo_screenwidth()
        sh = modal.winfo_screenheight()
        modal.geometry(f"450x320+{(sw-450)//2}+{(sh-320)//2}")

        frame = tk.Frame(modal, bg="#ffffff", padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Select Parked Bill to Recall", font=("Segoe UI", 11, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w", pady=(0, 10))

        for idx, pb in enumerate(parked):
            c_name = pb["customer"].get("name") if pb.get("customer") else "Cash Customer"
            card = tk.Frame(frame, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=8, cursor="hand2")
            card.pack(fill="x", pady=4)
            tk.Label(card, text=f"#{idx+1} {c_name} — Total: ₹{pb['total']:.2f}", font=("Segoe UI", 9, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w")
            tk.Label(card, text=f"Parked {pb['parked_at']}" + (f" by {pb['parked_by']}" if pb.get("parked_by") else "") + f" ({len(pb['lines'])} items)", font=("Segoe UI", 8), fg="#64748b", bg="#f8fafc").pack(anchor="w")

            card.bind("<Button-1>", lambda _e, i=idx: _recall(i))

        def _recall(i):
            if self._grid_has_items() and not messagebox.askyesno(
                    "Replace Current Bill", "The current bill has items that are not saved. Replace it with the parked bill?", parent=modal):
                return
            bills = self.billing.get_parked_bills()
            modal.destroy()
            if 0 <= i < len(bills):
                self._load_parked_bill(bills[i])           # load first ...
                self.billing.discard_parked_bill(i)        # ... then remove, so a failure never loses the bill
                self._refresh_parked_label()

    def _load_parked_bill(self, pb: dict):
        self._reset_bill()
        self.selected_customer = pb.get("customer")
        if self.selected_customer:
            self.customer_var.set(self.selected_customer.get("name"))
        else:
            self.customer_var.set("Cash")

        for idx, l in enumerate(pb.get("lines", [])):
            while idx >= len(self.row_widgets):
                self._add_row()
            row = self.row_widgets[idx]
            row["code"].insert(0, l.get("code", ""))
            row["name"].insert(0, l.get("name", ""))
            row["qty"].insert(0, l.get("qty", ""))
            row["unit"].set(l.get("unit", "Kg"))
            row["rate"].insert(0, l.get("rate", ""))
            row["item_id"] = l.get("item_id")
            self._recalculate_row(idx)

        self._refresh_parked_label()

    def _reset_bill(self):
        for idx in range(len(self.row_widgets)):
            self._clear_row(idx)
        self.selected_customer = None
        self.customer_var.set("Cash")
        self.deliv_name_lbl.config(text="Customer (Delivery): Cash")
        self.deliv_addr_lbl.config(text="Cash Customer")
        self.deliv_phone_lbl.config(text="")
        self.billto_lbl.config(text="-")
        self._update_grand_total()
        if self.row_widgets:
            self.row_widgets[0]["code"].focus_set()
