from __future__ import annotations
import logging
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.ui.components.customer_picker import open_customer_picker
from app.utils import validation as V
from app.ui.components.calendar_popup import attach_date_picker
from app.ui.smart_import_dialog import SmartImportDialog
from app.utils.currency import money
from app.models.order import OrderCreate, OrderItem
from app.services.order_service import OrderService
from app.services.master_service import MasterService
from app.services.pricing_service import PricingService
from app.printing.invoice import generate_dc_pdf
from app.ui.print_preview import show_print_preview
from app.utils.currency import format_inr
from app.utils.formatters import format_date


class OrderFormView(tk.Frame):
    """
    Create New Customer Order / Edit Order View.
    Shares identical UI/UX, column structure, spreadsheet keyboard traversal,
    keystroke calculations, gap compaction, and dynamic row addition with New Bill form.
    """

    NUM_ROWS = 15
    ITEM_UNITS = ["Kg", "Nos", "Bunch", "Pkt", "Box", "Bag", "Dz", "Gm", "Crate"]

    def __init__(self, parent, db, current_user, on_navigate=None, **kwargs):
        super().__init__(parent, bg="#ffffff", **kwargs)
        self.db = db
        self.current_user = current_user
        self.on_navigate = on_navigate
        self.order_svc = OrderService(db)
        self.master_svc = MasterService(db)
        self.pricing_svc = PricingService(db)

        self.order_id: Optional[str] = None
        self.is_edit: bool = False
        self.selected_customer: Optional[Dict[str, Any]] = None
        self.companies: List[Dict[str, Any]] = []
        self.items_cache: List[Dict[str, Any]] = []

        self.row_widgets: List[Dict[str, Any]] = []
        self._popup_listbox: Optional[tk.Listbox] = None
        self._popup_window: Optional[tk.Toplevel] = None
        self._active_row_idx: Optional[int] = None

        self._load_caches()
        self._build_ui()
        self._bind_shortcuts()
        self.reset_form()

    def _load_caches(self):
        try:
            self.companies = list(self.db.collection("companies").find({"is_deleted": 0}))
        except Exception:
            self.companies = []
        if not self.companies:
            self.companies = [{"company_id": "COMP-001", "name": settings.default_company_name}]

        try:
            self.items_cache = list(self.db.collection("items").find({"is_deleted": 0}))
        except Exception:
            self.items_cache = []

    def refresh(self):
        self._load_caches()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ---------------- 1. TITLE BAR ----------------
        title_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=10)
        title_bar.grid(row=0, column=0, sticky="ew")

        self.title_label = tk.Label(
            title_bar,
            text="New Order",
            font=("Segoe UI", 16, "bold"),
            fg="#0f172a",
            bg="#ffffff"
        )
        self.title_label.pack(side="left")

        btn_box = tk.Frame(title_bar, bg="#ffffff")
        btn_box.pack(side="right")

        self.smart_btn = tk.Button(
            btn_box,
            text="⇧ Smart (F8)",
            font=("Segoe UI", 9, "bold"),
            bg="#1976d2",
            fg="#ffffff",
            activebackground="#1565c0",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._open_smart_importer
        )
        self.smart_btn.pack(side="left", padx=(0, 8))

        self.close_btn = tk.Button(
            btn_box,
            text="Close (Esc)",
            font=("Segoe UI", 9, "bold"),
            bg="#546e7a",
            fg="#ffffff",
            activebackground="#455a64",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._on_close
        )
        self.close_btn.pack(side="left")

        # Subtle divider
        tk.Frame(self, bg="#e2e8f0", height=1).grid(row=0, column=0, sticky="sew")

        # ---------------- 2. METADATA CONTROLS ROW ----------------
        meta_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=10)
        meta_bar.grid(row=1, column=0, sticky="ew")

        # Company
        tk.Label(meta_bar, text="Company:", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        comp_names = [c.get("name", settings.default_company_name) for c in self.companies]
        self.company_cbo = ttk.Combobox(meta_bar, values=comp_names, width=22, state="readonly")
        if comp_names:
            self.company_cbo.current(0)
        self.company_cbo.pack(side="left", padx=(0, 20))

        # Customer (F5)
        tk.Label(meta_bar, text="Customer (F5):", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        cust_box = tk.Frame(meta_bar, bg="#cbd5e1", padx=1, pady=1)
        cust_box.pack(side="left", padx=(0, 20))
        self.customer_var = tk.StringVar(value="Select Customer (F5)")
        self.customer_ent = tk.Entry(
            cust_box,
            textvariable=self.customer_var,
            font=("Segoe UI", 9),
            width=26,
            relief="flat",
            bd=0
        )
        self.customer_ent.pack(fill="both", ipady=3, padx=4)
        self.customer_ent.bind("<FocusIn>", lambda _e: self._on_cust_focus_in())
        self.customer_ent.bind("<FocusOut>", lambda _e: self._on_cust_focus_out())
        self.customer_ent.bind("<Button-1>", lambda _e: self._open_customer_search())
        self.customer_ent.bind("<Key>", lambda _e: self._open_customer_search())

        # Date
        tk.Label(meta_bar, text="Date:", font=("Segoe UI", 9), fg="#64748b", bg="#ffffff").pack(side="left", padx=(0, 4))
        date_box = tk.Frame(meta_bar, bg="#cbd5e1", padx=1, pady=1)
        date_box.pack(side="left", padx=(0, 6))
        self.date_var = tk.StringVar(value=date.today().strftime("%d - %m - %Y"))
        self.date_ent = tk.Entry(date_box, textvariable=self.date_var, font=("Segoe UI", 9), width=14, relief="flat", bd=0, justify="center")
        self.date_ent.pack(side="left", ipady=3, padx=3)
        self.date_picker = attach_date_picker(self.date_ent, "%d - %m - %Y", on_selected=lambda _d: self.after(60, lambda: self.delivery_ent.focus_set()),
                                              allow_future=False, allow_blank=False, label="The order date")
        cal1 = tk.Label(date_box, text="📅", bg="#ffffff", fg="#64748b", font=("Segoe UI", 9), cursor="hand2")
        cal1.pack(side="left", padx=(0, 4))
        cal1.bind("<Button-1>", lambda _e: (self.date_ent.focus_set(), self.date_picker.open()))

        # Status Combobox (visible in edit mode)
        self.status_container = tk.Frame(meta_bar, bg="#ffffff")
        tk.Label(self.status_container, text="Status:", font=("Segoe UI", 9), fg="#64748b", bg="#ffffff").pack(side="left", padx=(10, 4))
        self.status_cbo = ttk.Combobox(self.status_container, values=["Pending", "Confirmed", "Delivered", "Billed", "Cancelled"], width=12, state="readonly")
        self.status_cbo.current(0)
        self.status_cbo.pack(side="left", padx=(0, 10))

        # Delivery Date
        self.delivery_container = tk.Frame(meta_bar, bg="#ffffff")
        self.delivery_container.pack(side="right")
        tk.Label(self.delivery_container, text="Delivery:", font=("Segoe UI", 9), fg="#64748b", bg="#ffffff").pack(side="left", padx=(0, 4))
        deliv_box = tk.Frame(self.delivery_container, bg="#cbd5e1", padx=1, pady=1)
        deliv_box.pack(side="left")
        tomorrow = date.today() + timedelta(days=1)
        self.delivery_var = tk.StringVar(value=tomorrow.strftime("%d - %m - %Y"))
        self.delivery_ent = tk.Entry(deliv_box, textvariable=self.delivery_var, font=("Segoe UI", 9), width=14, relief="flat", bd=0, justify="center")
        self.delivery_ent.pack(side="left", ipady=3, padx=3)
        self.delivery_picker = attach_date_picker(self.delivery_ent, "%d - %m - %Y", on_selected=lambda _d: self.after(60, self.focus_first_empty_row),
                                                  allow_blank=False, not_before=lambda: self.date_picker.value(), label="The delivery date")
        cal2 = tk.Label(deliv_box, text="📅", bg="#ffffff", fg="#64748b", font=("Segoe UI", 9), cursor="hand2")
        cal2.pack(side="left", padx=(0, 4))
        cal2.bind("<Button-1>", lambda _e: (self.delivery_ent.focus_set(), self.delivery_picker.open()))

        # ---------------- 3. ITEM SECTION (EXACT LOOK & FEEL AS BILLING FORM) ----------------
        grid_container = tk.Frame(self, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        grid_container.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))

        # Column definitions matching New Bill form:
        # (col_idx, weight, minsize, title, anchor)
        self.cols_def = [
            (0, 0, 45, "S.No", "center"),
            (1, 0, 95, "Item Code", "w"),
            (2, 1, 260, "Item Description", "w"),
            (3, 0, 75, "Qty", "e"),
            (4, 0, 85, "Unit", "w"),
            (5, 0, 95, "Rate", "e"),
            (6, 0, 110, "Amount", "e"),
            (7, 0, 40, "", "center")
        ]

        # Table Header
        grid_header = tk.Frame(grid_container, bg="#eef2f6", height=32)
        grid_header.pack(fill="x")

        for col_idx, weight, minsize, title, anchor in self.cols_def:
            grid_header.grid_columnconfigure(col_idx, weight=weight, minsize=minsize)
            lbl = tk.Label(
                grid_header,
                text=title,
                font=("Segoe UI", 9, "bold"),
                fg="#1e293b",
                bg="#eef2f6",
                anchor=anchor,
                padx=6,
                pady=6
            )
            lbl.grid(row=0, column=col_idx, sticky="nsew")

        # Scrollable table rows canvas
        self.t_canvas = tk.Canvas(grid_container, bg="#ffffff", highlightthickness=0)
        self.t_scroll = ttk.Scrollbar(grid_container, orient="vertical", command=self.t_canvas.yview)
        self.rows_frame = tk.Frame(self.t_canvas, bg="#ffffff")

        self.rows_frame.bind("<Configure>", lambda e: self.t_canvas.configure(scrollregion=self.t_canvas.bbox("all")))
        self.t_win = self.t_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.t_canvas.bind("<Configure>", lambda e: self.t_canvas.itemconfig(self.t_win, width=e.width))
        self.t_canvas.configure(yscrollcommand=self.t_scroll.set)

        self.t_canvas.pack(side="left", fill="both", expand=True)
        self.t_scroll.pack(side="right", fill="y")

        # Mousewheel binding
        self.t_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.rows_frame.bind("<MouseWheel>", self._on_mousewheel)

        # Build initial interactive rows filling the line item section
        for i in range(self.NUM_ROWS):
            row_data = self._create_row_widget(i)
            self.row_widgets.append(row_data)

        # ---------------- 4. TOTAL ITEMS SUMMARY & FINANCIALS ----------------
        summary_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=4)
        summary_bar.grid(row=3, column=0, sticky="ew")

        self.total_items_lbl = tk.Label(
            summary_bar,
            text="Total Items: 0",
            font=("Segoe UI", 12, "bold"),
            fg="#1b5e20",
            bg="#ffffff"
        )
        self.total_items_lbl.pack(side="left", padx=(0, 20))

        self.total_amount_lbl = tk.Label(
            summary_bar,
            text="Total Amount: ₹0.00",
            font=("Segoe UI", 14, "bold"),
            fg="#0f172a",
            bg="#ffffff"
        )
        self.total_amount_lbl.pack(side="right", padx=10)

        # ---------------- 5. OPERATIONS BAR (CRATES OUT / IN / Comm / Mandi Fee) ----------------
        ops_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=20, pady=8)
        ops_bar.grid(row=4, column=0, sticky="ew")

        left_ops = tk.Frame(ops_bar, bg="#f8fafc")
        left_ops.pack(side="left")

        tk.Label(left_ops, text="CRATES OUT:", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left", padx=(0, 4))
        c_out_box = tk.Frame(left_ops, bg="#cbd5e1", padx=1, pady=1)
        c_out_box.pack(side="left", padx=(0, 16))
        self.crates_out_var = tk.StringVar(value="")
        self.crates_out_ent = tk.Entry(c_out_box, textvariable=self.crates_out_var, font=("Segoe UI", 9), width=8, relief="flat", bd=0, justify="center")
        self.crates_out_ent.pack(fill="both", ipady=2, padx=2)

        tk.Label(left_ops, text="CRATES IN:", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left", padx=(0, 4))
        c_in_box = tk.Frame(left_ops, bg="#cbd5e1", padx=1, pady=1)
        c_in_box.pack(side="left", padx=(0, 16))
        self.crates_in_var = tk.StringVar(value="")
        self.crates_in_ent = tk.Entry(c_in_box, textvariable=self.crates_in_var, font=("Segoe UI", 9), width=8, relief="flat", bd=0, justify="center")
        self.crates_in_ent.pack(fill="both", ipady=2, padx=2)

        right_ops = tk.Frame(ops_bar, bg="#f8fafc")
        right_ops.pack(side="right")

        self.comm_lbl = tk.Label(right_ops, text="Comm: ₹ 0.00", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc")
        self.comm_lbl.pack(side="left", padx=(0, 16))

        self.mandi_fee_lbl = tk.Label(right_ops, text="Mandi Fee: ₹ 0.00", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc")
        self.mandi_fee_lbl.pack(side="left")

        # ---------------- 6. FUNCTION KEYS TOOLBAR ----------------
        fn_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=8)
        fn_bar.grid(row=5, column=0, sticky="ew")

        def _make_key_btn(parent, key_txt, action_txt, cmd):
            box = tk.Frame(parent, bg="#ffffff", cursor="hand2")
            box.pack(side="left", padx=(0, 14))
            badge = tk.Label(
                box,
                text=key_txt,
                font=("Segoe UI", 8, "bold"),
                bg="#334155",
                fg="#ffffff",
                padx=6,
                pady=2
            )
            badge.pack(side="left")
            lbl = tk.Label(
                box,
                text=f" {action_txt}",
                font=("Segoe UI", 9),
                fg="#1e293b",
                bg="#ffffff"
            )
            lbl.pack(side="left")
            for w in (box, badge, lbl):
                w.bind("<Button-1>", lambda _e, c=cmd: c())
            return box

        self.save_fn_box = _make_key_btn(fn_bar, "F3", "Save", self._on_f3_save)
        _make_key_btn(fn_bar, "F5", "Customer", self._open_customer_search)
        _make_key_btn(fn_bar, "F8", "Smart", self._open_smart_importer)
        self.save_print_fn_box = _make_key_btn(fn_bar, "F10", "Save & Print", self._on_f10_save_print)
        _make_key_btn(fn_bar, "Esc", "Close", self._on_close)

    def _on_mousewheel(self, event):
        if hasattr(self, "t_canvas") and event.delta:
            self.t_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _create_row_widget(self, row_idx: int) -> dict:
        row_f = tk.Frame(self.rows_frame, bg="#ffffff", height=32)
        row_f.pack(fill="x", expand=True, pady=1)

        for col_idx, weight, minsize, title, anchor in self.cols_def:
            row_f.grid_columnconfigure(col_idx, weight=weight, minsize=minsize)

        # 0. S.No
        sno_lbl = tk.Label(row_f, text=str(row_idx + 1), font=("Segoe UI", 9), fg="#64748b", bg="#ffffff", anchor="center")
        sno_lbl.grid(row=0, column=0, sticky="nsew", padx=1, pady=2)

        # 1. Item Code
        c_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        c_box.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        code_var = tk.StringVar(value="")
        code_ent = tk.Entry(c_box, textvariable=code_var, font=("Segoe UI", 9), width=5, relief="flat", bd=0)
        code_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # 2. Item Description
        d_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        d_box.grid(row=0, column=2, sticky="nsew", padx=2, pady=2)
        item_var = tk.StringVar(value="")
        name_ent = tk.Entry(d_box, textvariable=item_var, font=("Segoe UI", 9), width=10, relief="flat", bd=0)
        name_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # 3. Qty
        q_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        q_box.grid(row=0, column=3, sticky="nsew", padx=2, pady=2)
        qty_var = tk.StringVar(value="")
        qty_ent = tk.Entry(q_box, textvariable=qty_var, font=("Segoe UI", 9), width=5, relief="flat", bd=0, justify="right")
        qty_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # 4. Unit
        unit_cbo = ttk.Combobox(
            row_f,
            values=self.ITEM_UNITS,
            width=5
        )
        unit_cbo.grid(row=0, column=4, sticky="nsew", padx=2, pady=2)
        unit_cbo.set("Kg")

        # 5. Rate
        r_box = tk.Frame(row_f, bg="#e2e8f0", padx=1, pady=1)
        r_box.grid(row=0, column=5, sticky="nsew", padx=2, pady=2)
        rate_var = tk.StringVar(value="")
        rate_ent = tk.Entry(r_box, textvariable=rate_var, font=("Segoe UI", 9), width=5, relief="flat", bd=0, justify="right")
        rate_ent.pack(fill="both", expand=True, ipady=3, padx=2)

        # 6. Amount
        amt_lbl = tk.Label(row_f, text="₹0.00", font=("Segoe UI", 9, "bold"), fg="#0f172a", bg="#ffffff", anchor="e", padx=4)
        amt_lbl.grid(row=0, column=6, sticky="nsew", padx=2, pady=2)

        # 7. Red Delete Button [✕]
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

        # Event Bindings for Spreadsheet Interactivity (Matching Billing Form)
        code_ent.bind("<Return>", lambda e, r=row_idx: self._on_code_entered(r))
        code_ent.bind("<FocusOut>", lambda e, r=row_idx: self._on_code_entered(r, focus_next=False))
        code_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._on_code_key(e, r))
        code_ent.bind("<Down>", lambda e, r=row_idx: self._navigate_dropdown(e, 1))
        code_ent.bind("<Up>", lambda e, r=row_idx: self._navigate_dropdown(e, -1))

        name_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._on_item_key(e, r))
        name_ent.bind("<Return>", lambda e, r=row_idx: self._on_name_entered(r))
        name_ent.bind("<Down>", lambda e, r=row_idx: self._navigate_dropdown(e, 1))
        name_ent.bind("<Up>", lambda e, r=row_idx: self._navigate_dropdown(e, -1))

        qty_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._recalculate_row(r))
        qty_ent.bind("<Return>", lambda e, r=row_idx: self._on_qty_entered(r))

        unit_cbo.bind("<Return>", lambda e, r=row_idx: self._on_unit_entered(r))
        unit_cbo.bind("<<ComboboxSelected>>", lambda e, r=row_idx: self._on_unit_entered(r))

        rate_ent.bind("<KeyRelease>", lambda e, r=row_idx: self._recalculate_row(r))
        rate_ent.bind("<Return>", lambda e, r=row_idx: self._on_rate_entered(r))

        # Mouse wheel binding on all row widgets
        for w in (row_f, sno_lbl, code_ent, name_ent, qty_ent, unit_cbo, rate_ent, amt_lbl, del_btn):
            w.bind("<MouseWheel>", self._on_mousewheel, add="+")

        return {
            "idx": row_idx,
            "frame": row_f,
            "sno": sno_lbl,
            "code": code_ent,
            "code_var": code_var,
            "name": name_ent,
            "item": name_ent,       # backwards compatibility for tests
            "item_var": item_var,   # backwards compatibility for tests
            "qty": qty_ent,
            "qty_var": qty_var,     # backwards compatibility for tests
            "unit": unit_cbo,
            "rate": rate_ent,
            "rate_var": rate_var,   # backwards compatibility for tests
            "amount": amt_lbl,
            "del_btn": del_btn,
            "item_id": None,
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

    # ---------------- KEYBOARD-DRIVEN SPREADSHEET ROW LOGIC ----------------
    def _on_code_entered(self, row_idx: int, focus_next: bool = True):
        if row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        code = row["code_var"].get().strip()
        if not code:
            return

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
            item = self.db.collection("items").find_one({
                "name": {"$regex": escaped_code, "$options": "i"},
                "is_deleted": 0
            })
            if not item:
                item = self.db.collection("items").find_one({"is_deleted": 0})
                if not item:
                    return

        row["item_id"] = item["item_id"]
        row["code_var"].set(item.get("item_alias") or item["item_id"])
        row["item_var"].set(item.get("name", ""))

        unit = item.get("unit") or "Kg"
        vals = list(row["unit"]["values"])
        if unit not in vals:
            vals.append(unit)
            row["unit"]["values"] = vals
        row["unit"].set(unit)

        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"
        default_rate = float(item.get("standard_rate") or settings.default_rate)
        resolved_rate, _is_fixed = self.pricing_svc.resolve_rate(cust_id, item["item_id"], default_rate=default_rate)
        row["rate_var"].set(f"{resolved_rate:.2f}")

        if not row["qty_var"].get().strip():
            row["qty_var"].set("1")

        self._close_dropdown()
        self._recalculate_row(row_idx)

        if focus_next:
            row["qty"].focus_set()
            row["qty"].select_range(0, tk.END)

    def _on_name_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        self._close_dropdown()
        row["qty"].focus_set()
        row["qty"].select_range(0, tk.END)

    def _on_qty_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        self._recalculate_row(row_idx)
        row = self.row_widgets[row_idx]
        row["unit"].focus_set()

    def _on_unit_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        self._recalculate_row(row_idx)
        row = self.row_widgets[row_idx]
        row["rate"].focus_set()
        row["rate"].select_range(0, tk.END)

    def _recalculate_row(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        try:
            qty_str = row["qty_var"].get().strip()
            qty = float(qty_str) if qty_str else 0.0
        except (ValueError, TypeError):
            qty = 0.0

        try:
            rate_str = row["rate_var"].get().strip()
            rate = float(rate_str) if rate_str else 0.0
        except (ValueError, TypeError):
            rate = 0.0

        amount = qty * rate
        row["amount"].config(text=f"₹{amount:.2f}")
        self._recalculate()

    def _is_row_empty(self, row_idx: int) -> bool:
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return True
        row = self.row_widgets[row_idx]
        code = row["code_var"].get().strip()
        name = row["item_var"].get().strip()
        item_id = row.get("item_id")
        return not code and not name and not item_id

    def _compact_row_gap(self, row_idx: int) -> int:
        """
        If there is any gap above row_idx (an empty row among 0..row_idx-1),
        moves item from row_idx to the first empty row (N+1 position).
        """
        if row_idx <= 0 or row_idx >= len(self.row_widgets):
            return row_idx

        if self._is_row_empty(row_idx):
            return row_idx

        first_empty_idx = None
        for k in range(row_idx):
            if self._is_row_empty(k):
                first_empty_idx = k
                break

        if first_empty_idx is None:
            return row_idx

        src = self.row_widgets[row_idx]
        dest = self.row_widgets[first_empty_idx]

        dest["item_id"] = src.get("item_id")
        dest["code_var"].set(src["code_var"].get())
        dest["item_var"].set(src["item_var"].get())
        dest["qty_var"].set(src["qty_var"].get())
        dest["unit"].set(src["unit"].get())
        dest["rate_var"].set(src["rate_var"].get())

        self._clear_row(row_idx)
        self._recalculate_row(first_empty_idx)

        return first_empty_idx

    def _on_rate_entered(self, row_idx: int):
        if row_idx >= len(self.row_widgets):
            return
        if self._is_row_empty(row_idx):
            return

        self._recalculate_row(row_idx)
        target_idx = self._compact_row_gap(row_idx)

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
        """Clears row and shifts all subsequent rows up to maintain contiguous list."""
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return

        for k in range(row_idx, len(self.row_widgets) - 1):
            next_row = self.row_widgets[k + 1]
            curr_row = self.row_widgets[k]

            curr_row["item_id"] = next_row.get("item_id")
            curr_row["code_var"].set(next_row["code_var"].get())
            curr_row["item_var"].set(next_row["item_var"].get())
            curr_row["qty_var"].set(next_row["qty_var"].get())
            curr_row["unit"].set(next_row["unit"].get())
            curr_row["rate_var"].set(next_row["rate_var"].get())
            self._recalculate_row(k)

        # Clear the last row
        self._clear_row(len(self.row_widgets) - 1)
        self._recalculate()

    def _clear_row(self, row_idx: int):
        if row_idx < 0 or row_idx >= len(self.row_widgets):
            return
        row = self.row_widgets[row_idx]
        row["item_id"] = None
        row["code_var"].set("")
        row["item_var"].set("")
        row["qty_var"].set("")
        row["unit"].set("Kg")
        row["rate_var"].set("")
        row["amount"].config(text="₹0.00")
        self._recalculate()

    def _recalculate(self):
        count = 0
        subtotal = 0.0

        for row in self.row_widgets:
            code = row["code_var"].get().strip()
            name = row["item_var"].get().strip()
            qty_str = row["qty_var"].get().strip()

            if code or name or row.get("item_id"):
                count += 1
                try:
                    qty = float(qty_str) if qty_str else 0.0
                except ValueError:
                    qty = 0.0
                try:
                    rate_str = row["rate_var"].get().strip()
                    rate = float(rate_str) if rate_str else 0.0
                except ValueError:
                    rate = 0.0
                subtotal += (qty * rate)

        comm, mandi_fee = OrderService.charges(subtotal)
        self.total_items_lbl.config(text=f"Total Items: {count}")
        self.total_amount_lbl.config(text=f"Total Amount: ₹{subtotal + comm + mandi_fee:,.2f}")
        self.comm_lbl.config(text=f"Comm: ₹ {comm:,.2f}" + (f" ({settings.commission_rate:g}%)" if comm else ""))
        self.mandi_fee_lbl.config(text=f"Mandi Fee: ₹ {mandi_fee:,.2f}" + (f" ({settings.mandi_fee_rate:g}%)" if mandi_fee else ""))

    # ---------------- SMART TEXT IMPORTER (F8) ----------------
    def _open_smart_importer(self):
        """F8: read an order from a photo / scan (Tesseract OCR, translated to English) or, via the link, paste text."""
        self._load_caches()
        customers = list(self.db.collection("customers").find({"is_deleted": 0}))
        dlg = SmartImportDialog(self, self.items_cache, customers, on_import=self._import_scanned, on_text_mode=self._open_text_importer)
        self.smart_dialog = dlg
        return dlg

    def _import_scanned(self, rows, customer, order_date):
        """Rows reviewed in the Smart Importer -> the grid. A customer / date read from the image fill the form when it has none yet."""
        if customer and not self.selected_customer:
            self._apply_customer(customer)
        if order_date:
            self.date_var.set(order_date.strftime("%d - %m - %Y"))
        by_id = {it.get("item_id"): it for it in self.items_cache}
        matches = [(by_id[r["item_id"]], r["qty"], r["unit"]) for r in rows if r.get("item_id") in by_id]
        count = self.import_matches(matches)
        messagebox.showinfo("Smart Importer", f"{count} item(s) imported into the order. Check the quantities, then save with F3.", parent=self)
        return count

    def import_matches(self, matches) -> int:
        """Put (item, qty, unit) triples into the grid: a repeated item adds to its row, new items go to the first empty rows."""
        row_of_item = {r.get("item_id"): i for i, r in enumerate(self.row_widgets) if r.get("item_id")}
        start_idx = next((i for i, r in enumerate(self.row_widgets)
                          if not r["code_var"].get().strip() and not r["item_var"].get().strip()), len(self.row_widgets))
        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"
        done = 0
        for matched, qty, unit in matches:
            item_id = matched.get("item_id")
            qty = float(qty) if qty and float(qty) > 0 else 1.0
            if item_id in row_of_item:
                idx = row_of_item[item_id]
                try:
                    prev = float(self.row_widgets[idx]["qty_var"].get() or 0)
                except ValueError:
                    prev = 0.0
                self.row_widgets[idx]["qty_var"].set(f"{prev + qty:g}")
                self._recalculate_row(idx)
                done += 1
                continue
            while start_idx >= len(self.row_widgets):
                self._add_row()
            row = self.row_widgets[start_idx]
            row["item_id"] = item_id
            row["code_var"].set(matched.get("item_alias") or item_id)
            row["item_var"].set(matched.get("name"))
            default_rate = float(matched.get("standard_rate") or matched.get("rate") or matched.get("default_rate") or settings.default_rate)
            resolved_rate, _ = self.pricing_svc.resolve_rate(cust_id, item_id, default_rate=default_rate)
            row["rate_var"].set(f"{resolved_rate:.2f}")
            row["qty_var"].set(f"{qty:g}")
            row["unit"].set(matched.get("unit") or unit or "Kg")
            self._recalculate_row(start_idx)
            row_of_item[item_id] = start_idx
            start_idx += 1
            done += 1
        self._recalculate()
        return done

    def _open_text_importer(self):
        dlg = tk.Toplevel(self)
        dlg.title("Smart Order Importer (F8)")
        dlg.geometry("560x440")
        dlg.resizable(False, False)
        dlg.configure(bg="#ffffff")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        header = tk.Frame(dlg, bg="#1976d2", padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Smart Order Text Importer",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg="#1976d2"
        ).pack(side="left")

        body = tk.Frame(dlg, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Paste raw WhatsApp / message text below (e.g. 'Apple 25kg', '102 50kg'):",
            font=("Segoe UI", 9),
            fg="#475569",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 6))

        text_area = tk.Text(
            body,
            font=("Consolas", 10),
            bg="#f8fafc",
            fg="#0f172a",
            relief="solid",
            bd=1,
            height=10
        )
        text_area.pack(fill="both", expand=True, pady=(0, 12))
        text_area.focus_set()

        btn_row = tk.Frame(body, bg="#ffffff")
        btn_row.pack(fill="x")

        def _import_file():
            path = filedialog.askopenfilename(
                title="Select Order File",
                filetypes=[("Text & CSV Files", "*.txt *.csv"), ("All Files", "*.*")],
                parent=dlg
            )
            if path:
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text_area.delete("1.0", tk.END)
                        text_area.insert("1.0", f.read())
                except Exception as ex:
                    messagebox.showerror("Error", f"Failed to read file: {ex}", parent=dlg)

        tk.Button(
            btn_row,
            text="📂 Load File...",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#334155",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=_import_file
        ).pack(side="left")

        def _do_parse():
            raw_text = text_area.get("1.0", tk.END).strip()
            if not raw_text:
                messagebox.showwarning("Empty Text", "Please enter or paste order items to import.", parent=dlg)
                return

            imported_count = self._parse_and_populate_lines(raw_text)
            skipped = list(getattr(self, "import_skipped", []))
            dlg.destroy()
            msg = f"Smart Importer: {imported_count} items imported successfully."
            if skipped:
                msg += f"\n\n{len(skipped)} line(s) could not be matched to an item and were NOT imported:\n" + "\n".join(f"  - {l}" for l in skipped[:10])
            messagebox.showinfo("Smart Importer", msg, parent=self)

        tk.Button(
            btn_row,
            text="Parse & Populate",
            font=("Segoe UI", 9, "bold"),
            bg="#1976d2",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=18,
            pady=6,
            cursor="hand2",
            command=_do_parse
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_row,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#64748b",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=dlg.destroy
        ).pack(side="right")

    def _parse_and_populate_lines(self, text: str) -> int:
        """Parse pasted order text. Understands item codes ('102 50kg'), names ('Apple 25kg'),
        '<qty> <unit>' in either order and plural units ('2 boxes'). Lines that cannot be matched to a
        catalogue item are NOT guessed: they are skipped and listed in self.import_skipped.
        Repeated items are merged into one row."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        units_lc = {u.lower(): u for u in self.ITEM_UNITS}
        aliases = {str(it.get("item_alias")).lower(): it for it in self.items_cache if it.get("item_alias")}
        self.import_skipped = []

        def unit_of(word: str):
            w = word.lower()
            return units_lc.get(w) or units_lc.get(w.rstrip("s")) or units_lc.get(w[:-2] if w.endswith("es") else w)

        def find_by_name(q: str):
            q = q.lower().strip()
            if not q:
                return None
            for it in self.items_cache:
                if q in (str(it.get("item_id", "")).lower(), str(it.get("item_alias", "")).lower(), str(it.get("name", "")).lower()):
                    return it
            inside = [it for it in self.items_cache if str(it.get("name", "")).lower() and str(it.get("name", "")).lower() in q]
            if inside:
                return max(inside, key=lambda it: len(it.get("name", "")))     # longest catalogue name found in the text
            partial = [it for it in self.items_cache if q in str(it.get("name", "")).lower()]
            return partial[0] if partial else None

        # rows already holding an item (so repeated items merge instead of duplicating)
        row_of_item = {r.get("item_id"): i for i, r in enumerate(self.row_widgets) if r.get("item_id")}
        start_idx = next((i for i, r in enumerate(self.row_widgets)
                          if not r["code_var"].get().strip() and not r["item_var"].get().strip()), len(self.row_widgets))
        imported = 0
        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"

        for line in lines:
            qty = None
            unit = None
            bare = []
            name_parts = []
            for tok in line.split():
                m = re.match(r"^(\d+(?:\.\d+)?)([a-zA-Z]+)$", tok)
                if m and unit_of(m.group(2)):
                    qty, unit = float(m.group(1)), unit_of(m.group(2))
                    continue
                try:
                    bare.append(str(float(tok)) if not tok.isdigit() else tok)
                    continue
                except ValueError:
                    pass
                if unit_of(tok):
                    unit = unit_of(tok)
                    continue
                name_parts.append(tok)

            name = " ".join(name_parts)
            matched = None
            if not name:
                code = next((b for b in bare if b.lower() in aliases), None)
                if code:
                    matched = aliases[code.lower()]
                    bare.remove(code)
            else:
                matched = find_by_name(name)
            if qty is None and bare:
                qty = float(bare[0])

            if not matched:
                self.import_skipped.append(line)
                continue
            if qty is None or qty <= 0:
                qty = 1.0

            item_id = matched.get("item_id")
            if item_id in row_of_item:                       # same item again -> add to the existing row
                idx = row_of_item[item_id]
                try:
                    prev = float(self.row_widgets[idx]["qty_var"].get() or 0)
                except ValueError:
                    prev = 0.0
                self.row_widgets[idx]["qty_var"].set(f"{prev + qty:g}")
                self._recalculate_row(idx)
                imported += 1
                continue

            while start_idx >= len(self.row_widgets):
                self._add_row()
            row = self.row_widgets[start_idx]
            row["item_id"] = item_id
            row["code_var"].set(matched.get("item_alias") or item_id)
            row["item_var"].set(matched.get("name"))
            default_rate = float(matched.get("standard_rate") or matched.get("rate") or matched.get("default_rate") or settings.default_rate)
            resolved_rate, _ = self.pricing_svc.resolve_rate(cust_id, item_id, default_rate=default_rate)
            row["rate_var"].set(f"{resolved_rate:.2f}")
            row["qty_var"].set(f"{qty:g}")
            row["unit"].set(matched.get("unit") or unit or "Kg")
            self._recalculate_row(start_idx)
            row_of_item[item_id] = start_idx
            start_idx += 1
            imported += 1

        self._recalculate()
        return imported

    # ---------------- DROPDOWN AUTOCOMPLETE & ITEM SEARCH ----------------
    def _on_code_key(self, event, row_idx: int):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._active_row_idx = row_idx
        q = self.row_widgets[row_idx]["code_var"].get().strip().lower()
        if not q:
            self._close_dropdown()
            return
        matches = [
            it for it in self.items_cache
            if q in it.get("item_id", "").lower() or q in it.get("item_alias", "").lower() or q in it.get("name", "").lower()
        ]
        self._show_dropdown(row_idx, self.row_widgets[row_idx]["code"], matches)

    def _on_item_key(self, event, row_idx: int):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._active_row_idx = row_idx
        q = self.row_widgets[row_idx]["item_var"].get().strip().lower()
        if not q:
            self._close_dropdown()
            return
        matches = [
            it for it in self.items_cache
            if q in it.get("name", "").lower() or q in it.get("item_alias", "").lower() or q in it.get("item_id", "").lower()
        ]
        self._show_dropdown(row_idx, self.row_widgets[row_idx]["name"], matches)

    def _show_dropdown(self, row_idx: int, widget: tk.Widget, items: List[Dict[str, Any]]):
        if not items:
            self._close_dropdown()
            return

        if not self._popup_window or not self._popup_window.winfo_exists():
            self._popup_window = tk.Toplevel(self)
            self._popup_window.wm_overrideredirect(True)
            self._popup_window.attributes("-topmost", True)
            self._popup_listbox = tk.Listbox(
                self._popup_window,
                font=("Segoe UI", 9),
                bg="#ffffff",
                fg="#0f172a",
                selectbackground="#eef2ff",
                selectforeground="#4338ca",
                bd=1,
                relief="solid",
                highlightthickness=0
            )
            self._popup_listbox.pack(fill="both", expand=True)
            self._popup_listbox.bind("<Button-1>", lambda _e: self._on_dropdown_click())
            self._popup_listbox.bind("<Return>", lambda _e: self._on_dropdown_select())

        self._active_dropdown_items = items
        self._popup_listbox.delete(0, tk.END)
        for it in items[:15]:
            code = it.get("item_alias") or it.get("item_id") or ""
            name = it.get("name") or ""
            unit = it.get("unit") or "Kg"
            self._popup_listbox.insert(tk.END, f"{name.ljust(26)} [{code}] ({unit})")

        self._popup_listbox.selection_set(0)

        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
        w = max(340, widget.winfo_width())
        h = min(200, 22 * len(items[:15]) + 4)
        self._popup_window.geometry(f"{w}x{h}+{x}+{y}")
        self._popup_window.deiconify()

    def _navigate_dropdown(self, event, direction: int):
        if self._popup_listbox and self._popup_window and self._popup_window.winfo_exists():
            cur = self._popup_listbox.curselection()
            idx = cur[0] if cur else 0
            new_idx = max(0, min(self._popup_listbox.size() - 1, idx + direction))
            self._popup_listbox.selection_clear(0, tk.END)
            self._popup_listbox.selection_set(new_idx)
            self._popup_listbox.see(new_idx)
            return "break"

    def _on_dropdown_click(self):
        self.after(50, self._on_dropdown_select)

    def _on_dropdown_select(self, _event=None):
        if not self._popup_listbox or self._active_row_idx is None:
            return "break"
        cur = self._popup_listbox.curselection()
        if not cur or cur[0] >= len(self._active_dropdown_items):
            self._close_dropdown()
            return "break"

        it = self._active_dropdown_items[cur[0]]
        row = self.row_widgets[self._active_row_idx]
        row["item_id"] = it.get("item_id")
        row["code_var"].set(it.get("item_alias") or it.get("item_id", ""))
        row["item_var"].set(it.get("name", ""))
        row["unit"].set(it.get("unit") or "Kg")

        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else "CASH"
        default_rate = float(it.get("standard_rate") or settings.default_rate)
        resolved_rate, _ = self.pricing_svc.resolve_rate(cust_id, it.get("item_id"), default_rate=default_rate)
        row["rate_var"].set(f"{resolved_rate:.2f}")

        if not row["qty_var"].get().strip():
            row["qty_var"].set("1")

        self._recalculate_row(self._active_row_idx)
        self._close_dropdown()

        row["qty"].focus_set()
        row["qty"].select_range(0, tk.END)
        return "break"

    def _close_dropdown(self):
        if self._popup_window and self._popup_window.winfo_exists():
            self._popup_window.withdraw()

    # ---------------- CUSTOMER SEARCH (F5) ----------------
    def _on_cust_focus_in(self):
        if self.customer_var.get() == "Select Customer (F5)":
            self.customer_var.set("")
            self.customer_ent.config(fg="#0f172a")

    def _on_cust_focus_out(self):
        if not self.customer_var.get().strip():
            self.customer_var.set("Select Customer (F5)")
            self.customer_ent.config(fg="#94a3b8")

    def _open_customer_search(self):
        """Same dialog as New Bill (F5): type to filter, Up / Down, Enter. Orders need a customer from the master, so no walk-in option."""
        return open_customer_picker(self, self.db, self._apply_customer, allow_cash=False)

    def _apply_customer(self, matched):
        if matched:
            self.selected_customer = matched
            self.customer_var.set(matched.get("name", ""))
            self.customer_ent.config(fg="#0f172a")
            for r_idx, row in enumerate(self.row_widgets):                   # fixed rates for the lines already entered
                item_id = row.get("item_id")
                if item_id:
                    res_rate, _ = self.pricing_svc.resolve_rate(matched.get("cust_id"), item_id, default_rate=settings.default_rate)
                    row["rate_var"].set(f"{res_rate:.2f}")
                    self._recalculate_row(r_idx)
        self.after(60, lambda: (self.date_ent.focus_set(), self.date_ent.select_range(0, tk.END)))      # customer -> order date -> delivery date -> items

    def focus_first_empty_row(self) -> int:
        idx = next((i for i in range(len(self.row_widgets)) if self._is_row_empty(i)), None)
        if idx is None:
            idx = self._add_row()
        self._scroll_to_row(idx)
        self.row_widgets[idx]["code"].focus_set()
        return idx

    # ---------------- SAVE & VALIDATION (F2 / F10) ----------------
    @staticmethod
    def _crate_count(text: str, label: str) -> int:
        """A whole number of crates, 0 or more (blank = 0). It used to turn anything unreadable into 0 silently."""
        n = V.number(text, label, minimum=0, maximum=1_000_000, required=False, default=0.0)
        if n != int(n):
            raise ValueError(f"{label} must be a whole number.")
        return int(n)

    def _on_f2_save(self):
        self._save_order(print_pdf=False)

    def _on_f3_save(self):
        self._save_order(print_pdf=False)

    def _on_f10_save_print(self):
        self._save_order(print_pdf=True)

    def _save_order(self, print_pdf: bool = False):
        cust_name = self.customer_var.get().strip()
        if not cust_name or cust_name == "Select Customer (F5)":
            messagebox.showwarning("Customer Required", "Please select a valid customer (F5).", parent=self)
            self._open_customer_search()
            return

        if not self.selected_customer or str(self.selected_customer.get("name", "")).strip().lower() != cust_name.lower():
            # typed text: accept only an exact match to a customer in the master
            exact = next((c for c in self.db.collection("customers").find({"is_deleted": 0})
                          if str(c.get("name", "")).strip().lower() == cust_name.lower()), None)
            if not exact:
                messagebox.showwarning("Unknown Customer", f"'{cust_name}' is not in the customer master. Pick a customer with F5.", parent=self)
                self._open_customer_search()
                return
            self.selected_customer = exact
        cust_id = self.selected_customer.get("cust_id")

        order_items: List[OrderItem] = []
        for idx, row in enumerate(self.row_widgets):
            code = row["code_var"].get().strip()
            name = row["item_var"].get().strip()
            qty_str = row["qty_var"].get().strip()
            rate_str = row["rate_var"].get().strip()

            if code or name or row.get("item_id"):
                try:
                    qty = float(qty_str)
                    if qty <= 0:
                        raise ValueError()
                except ValueError:
                    messagebox.showwarning("Invalid Quantity", f"Please enter a valid quantity for row {idx + 1} ({name or code}).", parent=self)
                    row["qty"].focus_set()
                    return

                try:
                    rate = float(rate_str)
                except ValueError:
                    rate = 0.0

                unit = row["unit"].get() or "Kg"
                order_items.append(OrderItem(
                    item_id=row.get("item_id") or code or name,
                    name=name or code,
                    qty=qty,
                    unit=unit,
                    rate=rate,
                    amount=qty * rate
                ))

        if not order_items:
            messagebox.showwarning("Items Required", "Please enter at least one line item with a quantity.", parent=self)
            self.row_widgets[0]["code"].focus_set()
            return

        deliv_str = self.delivery_var.get().strip()
        order_date_str = self.date_var.get().strip()

        problem = self.date_picker.error()
        if problem:
            messagebox.showwarning("Invalid Order Date", problem, parent=self)
            self.date_ent.focus_set()
            return
        problem = self.delivery_picker.error()
        if problem:
            messagebox.showwarning("Invalid Delivery Date", problem, parent=self)
            self.delivery_ent.focus_set()
            return
        ord_dt = datetime.combine(self.date_picker.value(), datetime.min.time())
        deliv_dt = datetime.combine(self.delivery_picker.value(), datetime.min.time())

        deliv_formatted = deliv_dt.strftime("%A, %d %B %Y")
        confirm = messagebox.askyesno(
            "Confirm Delivery Schedule",
            f"Schedule order for delivery on:\n{deliv_formatted}?\n\nCustomer: {cust_name}\nTotal Items: {len(order_items)}",
            parent=self
        )
        if not confirm:
            return

        try:
            c_out = self._crate_count(self.crates_out_var.get(), "Crates out")
            c_in = self._crate_count(self.crates_in_var.get(), "Crates in")
        except ValueError as exc:
            messagebox.showwarning("Crates", str(exc), parent=self)
            return

        selected_comp_name = self.company_cbo.get()
        selected_comp = next((c for c in self.companies if c.get("name") == selected_comp_name), self.companies[0] if self.companies else {})
        company_id = selected_comp.get("company_id", "COMP-001")

        items_total = money(sum(i.amount for i in order_items))
        comm, mandi = OrderService.charges(items_total)
        total_amount = money(items_total + comm + mandi)

        status_val = self.status_cbo.get().lower() if self.is_edit else "pending"

        if self.is_edit and self.order_id:
            update_data = {
                "customer_id": cust_id,
                "customer_name": cust_name,
                "company_id": company_id,
                "order_date": ord_dt,
                "delivery_date": deliv_dt,
                "items": [i.model_dump() for i in order_items],
                "total_amount": total_amount,
                "status": status_val,
                "crates_issued": c_out,
                "crates_returned": c_in,
                "commission_amt": comm,
                "mandi_fee_amt": mandi,
            }
            saved_order = self.order_svc.update_order(self.order_id, update_data)
            final_id = self.order_id
            messagebox.showinfo("Order Updated", f"Order {final_id} updated successfully!", parent=self)
        else:
            req = OrderCreate(
                customer_id=cust_id,
                customer_name=cust_name,
                company_id=company_id,
                order_date=ord_dt,
                delivery_date=deliv_dt,
                items=order_items,
                total_amount=total_amount,
                status=status_val,
                crates_issued=c_out,
                crates_returned=c_in,
                commission_amt=comm,
                mandi_fee_amt=mandi,
                created_by=self.current_user.username
            )
            saved_order = self.order_svc.create_order(req)
            final_id = saved_order.get("order_id")
            messagebox.showinfo("Order Created", f"Order {final_id} created successfully!", parent=self)

        if print_pdf:
            self._print_order(saved_order or {"order_id": final_id, "customer_name": cust_name, "items": [i.model_dump() for i in order_items], "delivery_date": deliv_dt})

        self.reset_form()
        if self.on_navigate:
            self.on_navigate("Orders")

    def _print_order(self, order_dict: Dict[str, Any]):
        try:
            dc_bill = {
                "invoice_no": order_dict.get("order_id", "ORD-NEW"),
                "invoice_date": order_dict.get("delivery_date") or datetime.now(),
                "customer_id": order_dict.get("customer_id", ""),
                "customer_name": order_dict.get("customer_name", ""),
                "items": order_dict.get("items", []),
                "total_amount": order_dict.get("total_amount", 0.0),
                "crates_issued": order_dict.get("crates_issued", 0),
                "crates_returned": order_dict.get("crates_returned", 0),
                "payment_mode": "ORDER",
            }
            comp = next((c for c in self.companies if c.get("name") == self.company_cbo.get()), None)
            cust = self.selected_customer
            temp_pdf = os.path.join(os.environ.get("TEMP", os.getcwd()), f"{dc_bill['invoice_no']}.pdf")
            generate_dc_pdf(dc_bill, temp_pdf, company=comp, customer=cust)
            show_print_preview(self, temp_pdf, title=f"Print Order - {dc_bill['invoice_no']}")
        except Exception as ex:
            messagebox.showerror("Printing Error", f"Failed to generate print preview: {ex}", parent=self)

    # ---------------- RESET & EDIT LOADER ----------------
    def reset_form(self):
        self.order_id = None
        self.is_edit = False
        self.selected_customer = None

        self.title_label.config(text="New Order")
        self.customer_var.set("Select Customer (F5)")
        self.customer_ent.config(fg="#94a3b8")
        self.date_var.set(date.today().strftime("%d - %m - %Y"))
        tomorrow = date.today() + timedelta(days=1)
        self.delivery_var.set(tomorrow.strftime("%d - %m - %Y"))

        self.status_container.pack_forget()
        self.crates_out_var.set("")
        self.crates_in_var.set("")

        self.save_fn_box.winfo_children()[1].config(text=" Save")
        self.save_print_fn_box.winfo_children()[1].config(text=" Save & Print")

        for r_idx in range(len(self.row_widgets)):
            self._clear_row(r_idx)

        self._recalculate()
        if self.row_widgets:
            self.row_widgets[0]["code"].focus_set()

    def load_order_for_edit(self, order_id: str):
        order = self.order_svc.get_order(order_id)
        if not order:
            messagebox.showerror("Error", f"Order {order_id} not found.", parent=self)
            return

        self.reset_form()
        self.order_id = order_id
        self.is_edit = True

        self.title_label.config(text=f"Edit Order: {order_id}")
        self.save_fn_box.winfo_children()[1].config(text=" Update")
        self.save_print_fn_box.winfo_children()[1].config(text=" Update & Print")

        cust_name = order.get("customer_name", "")
        self.customer_var.set(cust_name)
        self.customer_ent.config(fg="#0f172a")
        cust_id = order.get("customer_id")
        if cust_id:
            self.selected_customer = self.db.collection("customers").find_one({"cust_id": cust_id, "is_deleted": 0})

        ord_dt = order.get("order_date")
        if isinstance(ord_dt, datetime):
            self.date_var.set(ord_dt.strftime("%d - %m - %Y"))
        elif ord_dt:
            self.date_var.set(format_date(ord_dt))

        deliv_dt = order.get("delivery_date")
        if isinstance(deliv_dt, datetime):
            self.delivery_var.set(deliv_dt.strftime("%d - %m - %Y"))
        elif deliv_dt:
            self.delivery_var.set(format_date(deliv_dt))

        self.status_container.pack(side="left", padx=(0, 16))
        st = order.get("status", "pending").capitalize()
        for idx, s in enumerate(["Pending", "Confirmed", "Delivered", "Billed", "Cancelled"]):
            if s.lower() == st.lower():
                self.status_cbo.current(idx)
                break

        self.crates_out_var.set(str(order.get("crates_issued", "")))
        self.crates_in_var.set(str(order.get("crates_returned", "")))

        items = order.get("items", [])
        for idx, it in enumerate(items):
            if idx >= len(self.row_widgets):
                self._add_row()

            row = self.row_widgets[idx]
            row["item_id"] = it.get("item_id", "")
            row["code_var"].set(it.get("item_alias") or it.get("item_id", ""))
            row["item_var"].set(it.get("name", ""))
            row["qty_var"].set(f"{float(it.get('qty', 0)):g}")
            row["rate_var"].set(f"{float(it.get('rate', 0.0)):.2f}")
            row["unit"].set(it.get("unit") or "Kg")
            self._recalculate_row(idx)

        self._recalculate()

    def _bind_shortcuts(self):
        """The function keys are routed by the main window to whichever screen is showing (F3 save, F5 customer, F8 smart import,
        F10 save & print, Esc close). Binding them here with bind_all made them fire on every screen."""
        return None

    def _on_esc(self):
        if self._popup_window and self._popup_window.winfo_exists():
            self._close_dropdown()
            return
        self._on_close()

    def _on_close(self):
        self._close_dropdown()
        if self.on_navigate:
            self.on_navigate("Orders")
        else:
            top = self.winfo_toplevel()
            if isinstance(top, tk.Toplevel):
                top.destroy()
