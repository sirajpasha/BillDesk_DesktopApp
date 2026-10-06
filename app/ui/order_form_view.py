import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.models.order import OrderCreate, OrderItem
from app.services.order_service import OrderService
from app.services.master_service import MasterService
from app.printing.invoice import generate_dc_pdf
from app.ui.print_preview import show_print_preview
from app.utils.currency import format_inr
from app.utils.formatters import format_date


class OrderFormView(tk.Frame):
    """
    Create New Customer Order / Edit Order View.
    Matches exact UI/UX from:
    - 13-order-new.png (New Order Form)
    - 49-order-detail.png (Edit Order Form)
    """

    NUM_ROWS = 15

    ITEM_UNITS = ["Unit", "kg", "dz", "box", "pcs", "crates", "bags", "gm", "bunch", "pk"]

    def __init__(self, parent, db, current_user, on_navigate=None, **kwargs):
        super().__init__(parent, bg="#ffffff", **kwargs)
        self.db = db
        self.current_user = current_user
        self.on_navigate = on_navigate
        self.order_svc = OrderService(db)
        self.master_svc = MasterService(db)

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
        # Matches 13-order-new.png: "New Order" with Smart (F8) and Close (Esc)
        title_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=12)
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
        # Company | Customer (F5) | Date | (Status) | Delivery
        meta_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=12)
        meta_bar.grid(row=1, column=0, sticky="ew")

        # Company
        tk.Label(meta_bar, text="Company:", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        comp_names = [c.get("name", settings.default_company_name) for c in self.companies]
        self.company_cbo = ttk.Combobox(meta_bar, values=comp_names, width=24, state="readonly")
        if comp_names:
            self.company_cbo.current(0)
        self.company_cbo.pack(side="left", padx=(0, 24))

        # Customer (F5)
        tk.Label(meta_bar, text="Customer (F5):", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left", padx=(0, 6))
        cust_box = tk.Frame(meta_bar, bg="#cbd5e1", padx=1, pady=1)
        cust_box.pack(side="left", padx=(0, 24))
        self.customer_var = tk.StringVar(value="")
        self.customer_ent = tk.Entry(
            cust_box,
            textvariable=self.customer_var,
            font=("Segoe UI", 9),
            width=28,
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
        tk.Label(date_box, text="📅", bg="#ffffff", fg="#64748b", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 4))

        # Status Combobox (visible in edit mode)
        self.status_container = tk.Frame(meta_bar, bg="#ffffff")
        tk.Label(self.status_container, text="Status:", font=("Segoe UI", 9), fg="#64748b", bg="#ffffff").pack(side="left", padx=(12, 4))
        self.status_cbo = ttk.Combobox(self.status_container, values=["Pending", "Confirmed", "Delivered", "Billed", "Cancelled"], width=12, state="readonly")
        self.status_cbo.current(0)
        self.status_cbo.pack(side="left", padx=(0, 12))

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
        tk.Label(deliv_box, text="📅", bg="#ffffff", fg="#64748b", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 4))

        # ---------------- 3. SPREADSHEET TABLE GRID (15 ROWS) ----------------
        grid_container = tk.Frame(self, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1)
        grid_container.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))

        # Table Header
        th = tk.Frame(grid_container, bg="#eef2f6", height=32)
        th.pack(fill="x")

        th_sno = tk.Label(th, text="Sno", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#eef2f6", width=5, anchor="center")
        th_sno.pack(side="left")

        th_code = tk.Label(th, text="Code", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#eef2f6", width=16, anchor="w", padx=8)
        th_code.pack(side="left")

        th_item = tk.Label(th, text="Item", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#eef2f6", anchor="w", padx=8)
        th_item.pack(side="left", fill="x", expand=True)

        th_del = tk.Label(th, text="", bg="#eef2f6", width=5)
        th_del.pack(side="right")

        th_unit = tk.Label(th, text="Unit", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#eef2f6", width=12, anchor="center")
        th_unit.pack(side="right", padx=(0, 4))

        th_qty = tk.Label(th, text="Qty", font=("Segoe UI", 9, "bold"), fg="#1e293b", bg="#eef2f6", width=10, anchor="center")
        th_qty.pack(side="right", padx=(0, 8))

        # Canvas with scrollable body so 15 rows fill the screen nicely
        self.canvas = tk.Canvas(grid_container, bg="#ffffff", highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.rows_frame = tk.Frame(self.canvas, bg="#ffffff")

        self.rows_frame.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=None, yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.bind("<Configure>", self._on_resize)

        # Build 15 spreadsheet rows
        self._build_table_rows()

        # ---------------- 4. TOTAL ITEMS SUMMARY ----------------
        summary_bar = tk.Frame(self, bg="#ffffff", padx=20, pady=4)
        summary_bar.grid(row=3, column=0, sticky="ew")

        self.total_items_lbl = tk.Label(
            summary_bar,
            text="Total Items: 0",
            font=("Segoe UI", 16, "bold"),
            fg="#1b5e20",
            bg="#ffffff"
        )
        self.total_items_lbl.pack(side="right", padx=10)

        # ---------------- 5. OPERATIONS BAR (CRATES OUT / IN / Comm / Mandi Fee) ----------------
        ops_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=20, pady=8)
        ops_bar.grid(row=4, column=0, sticky="ew")

        # Left: Crates Out / Crates In
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

        # Right: Comm / Mandi Fee
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
                w.bind("<Button-1>", lambda _e: cmd())
            return box

        self.save_fn_box = _make_key_btn(fn_bar, "F2", "Save", self._on_f2_save)
        _make_key_btn(fn_bar, "F5", "Customer", self._open_customer_search)
        self.smart_fn_box = _make_key_btn(fn_bar, "F8", "Smart", self._open_smart_importer)
        self.save_print_fn_box = _make_key_btn(fn_bar, "F10", "Save & Print", self._on_f10_save_print)
        _make_key_btn(fn_bar, "Esc", "Close", self._on_close)

    def _on_resize(self, event):
        # Keep rows frame expanded to canvas width
        if event.widget == self:
            canvas_width = max(600, self.canvas.winfo_width())
            self.canvas.itemconfig(self.canvas_window, width=canvas_width)

    def _build_table_rows(self):
        for idx in range(self.NUM_ROWS):
            bg_color = "#ffffff" if idx % 2 == 0 else "#fbfcfd"
            row_frame = tk.Frame(self.rows_frame, bg=bg_color, height=30)
            row_frame.pack(fill="x", expand=True)

            # Sno
            sno_lbl = tk.Label(
                row_frame,
                text="",
                font=("Segoe UI", 9),
                fg="#64748b",
                bg=bg_color,
                width=5,
                anchor="center",
                bd=1,
                relief="solid",
                highlightthickness=0
            )
            sno_lbl.pack(side="left", fill="y")

            # Code
            code_var = tk.StringVar()
            code_ent = tk.Entry(
                row_frame,
                textvariable=code_var,
                font=("Segoe UI", 9),
                width=16,
                relief="solid",
                bd=1,
                highlightthickness=0
            )
            code_ent.pack(side="left", fill="y")

            # Item Description
            item_var = tk.StringVar()
            item_ent = tk.Entry(
                row_frame,
                textvariable=item_var,
                font=("Segoe UI", 9),
                relief="solid",
                bd=1,
                highlightthickness=0
            )
            item_ent.pack(side="left", fill="both", expand=True)

            # Delete button (🗑)
            del_btn = tk.Button(
                row_frame,
                text="🗑",
                font=("Segoe UI", 9),
                fg="#dc2626",
                bg=bg_color,
                activeforeground="#b91c1c",
                activebackground="#fee2e2",
                relief="solid",
                bd=1,
                width=4,
                cursor="hand2",
                command=lambda r=idx: self._clear_row(r)
            )
            del_btn.pack(side="right", fill="y")

            # Unit
            unit_cbo = ttk.Combobox(
                row_frame,
                values=self.ITEM_UNITS,
                width=10,
                state="readonly"
            )
            unit_cbo.current(0)
            unit_cbo.pack(side="right", fill="y", padx=(0, 2))

            # Qty
            qty_var = tk.StringVar()
            qty_ent = tk.Entry(
                row_frame,
                textvariable=qty_var,
                font=("Segoe UI", 9),
                width=10,
                relief="solid",
                bd=1,
                justify="center",
                highlightthickness=0
            )
            qty_ent.pack(side="right", fill="y", padx=(0, 6))

            # Store row references
            row_data = {
                "idx": idx,
                "frame": row_frame,
                "sno": sno_lbl,
                "code": code_ent,
                "code_var": code_var,
                "item": item_ent,
                "item_var": item_var,
                "qty": qty_ent,
                "qty_var": qty_var,
                "unit": unit_cbo,
                "del_btn": del_btn,
                "item_id": "",
                "rate": 0.0,
            }
            self.row_widgets.append(row_data)

            # Bindings for keyboard navigation and live search
            code_ent.bind("<KeyRelease>", lambda e, r=idx: self._on_code_key(e, r))
            code_ent.bind("<Return>", lambda e, r=idx: self._focus_next_field(r, "code"))
            code_ent.bind("<Down>", lambda e, r=idx: self._navigate_dropdown(e, 1))
            code_ent.bind("<Up>", lambda e, r=idx: self._navigate_dropdown(e, -1))
            code_ent.bind("<FocusOut>", lambda e, r=idx: self._on_cell_focus_out())

            item_ent.bind("<KeyRelease>", lambda e, r=idx: self._on_item_key(e, r))
            item_ent.bind("<Return>", lambda e, r=idx: self._focus_next_field(r, "item"))
            item_ent.bind("<Down>", lambda e, r=idx: self._navigate_dropdown(e, 1))
            item_ent.bind("<Up>", lambda e, r=idx: self._navigate_dropdown(e, -1))
            item_ent.bind("<FocusOut>", lambda e, r=idx: self._on_cell_focus_out())

            qty_ent.bind("<KeyRelease>", lambda _e, r=idx: self._recalculate())
            qty_ent.bind("<Return>", lambda e, r=idx: self._focus_next_field(r, "qty"))

            unit_cbo.bind("<<ComboboxSelected>>", lambda _e, r=idx: self._recalculate())
            unit_cbo.bind("<Return>", lambda e, r=idx: self._focus_next_field(r, "unit"))

    def _bind_shortcuts(self):
        self.bind_all("<F2>", lambda _e: self._on_f2_save())
        self.bind_all("<F5>", lambda _e: self._open_customer_search())
        self.bind_all("<F8>", lambda _e: self._open_smart_importer())
        self.bind_all("<F10>", lambda _e: self._on_f10_save_print())
        self.bind_all("<Escape>", lambda _e: self._on_esc())

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

    # ---------------- DROPDOWN AUTOCOMPLETE ----------------
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
        self._show_dropdown(row_idx, self.row_widgets[row_idx]["item"], matches)

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
            unit = it.get("unit") or "kg"
            self._popup_listbox.insert(tk.END, f"{name.ljust(26)} [{code}] ({unit})")

        self._popup_listbox.selection_set(0)

        # Position popup directly beneath the entry widget
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height()
        w = max(320, widget.winfo_width())
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

    def _on_dropdown_select(self):
        if not self._popup_listbox or not self._popup_listbox.curselection():
            self._close_dropdown()
            return
        sel_idx = self._popup_listbox.curselection()[0]
        if sel_idx < len(self._active_dropdown_items):
            chosen = self._active_dropdown_items[sel_idx]
            self._assign_item_to_row(self._active_row_idx, chosen)
        self._close_dropdown()

    def _assign_item_to_row(self, row_idx: int, item: Dict[str, Any]):
        if row_idx is None or row_idx >= len(self.row_widgets):
            return

        # Duplicate check: check if already entered in another row
        item_id = item.get("item_id")
        item_alias = item.get("item_alias")
        for idx, r in enumerate(self.row_widgets):
            if idx != row_idx and r.get("item_id") and (r["item_id"] == item_id or (item_alias and r["item_id"] == item_alias)):
                messagebox.showinfo("Duplicate Item", f"Item '{item.get('name')}' is already entered on row {idx + 1}.", parent=self)
                r["qty"].focus_set()
                return

        row = self.row_widgets[row_idx]
        code = item.get("item_alias") or item.get("item_id") or ""
        name = item.get("name") or ""
        unit = (item.get("unit") or "kg").lower()

        row["item_id"] = item.get("item_id")
        row["code_var"].set(code)
        row["item_var"].set(name)
        row["rate"] = float(item.get("standard_rate", 0.0))

        # Set unit dropdown
        matched_unit = False
        for u_idx, u in enumerate(self.ITEM_UNITS):
            if u.lower() == unit:
                row["unit"].current(u_idx)
                matched_unit = True
                break
        if not matched_unit:
            row["unit"].current(1)  # Default "kg"

        self._recalculate()

        # Automatically advance focus to Qty field
        row["qty"].focus_set()
        row["qty"].select_range(0, tk.END)

    def _close_dropdown(self):
        if self._popup_window and self._popup_window.winfo_exists():
            self._popup_window.destroy()
        self._popup_window = None
        self._popup_listbox = None

    def _on_cell_focus_out(self):
        # Grace period to allow mouse clicks on popup listbox
        self.after(200, self._close_dropdown)

    def _focus_next_field(self, row_idx: int, field: str):
        if self._popup_window and self._popup_window.winfo_exists():
            self._on_dropdown_select()
            return "break"

        row = self.row_widgets[row_idx]
        if field == "code":
            row["item"].focus_set()
        elif field == "item":
            row["qty"].focus_set()
        elif field == "qty":
            # Advance to unit or to next row code
            if row_idx + 1 < len(self.row_widgets):
                next_row = self.row_widgets[row_idx + 1]
                next_row["code"].focus_set()
            else:
                self.save_fn_box.focus_set()
        elif field == "unit":
            if row_idx + 1 < len(self.row_widgets):
                next_row = self.row_widgets[row_idx + 1]
                next_row["code"].focus_set()
        return "break"

    def _clear_row(self, row_idx: int):
        row = self.row_widgets[row_idx]
        row["item_id"] = ""
        row["code_var"].set("")
        row["item_var"].set("")
        row["qty_var"].set("")
        row["unit"].current(0)
        row["rate"] = 0.0
        self._recalculate()

    def _recalculate(self):
        filled_count = 0
        sno_counter = 1
        total_amount = 0.0

        for row in self.row_widgets:
            code = row["code_var"].get().strip()
            item = row["item_var"].get().strip()
            qty_str = row["qty_var"].get().strip()

            if code or item:
                row["sno"].config(text=str(sno_counter))
                sno_counter += 1
                try:
                    qty = float(qty_str) if qty_str else 0.0
                except ValueError:
                    qty = 0.0
                if qty > 0:
                    filled_count += 1
                    rate = float(row.get("rate", 0.0))
                    total_amount += (qty * rate)
            else:
                row["sno"].config(text="")

        self.total_items_lbl.config(text=f"Total Items: {filled_count}")

        # Commission and Mandi Fee calculations if rates apply
        comm = total_amount * 0.05 if total_amount > 0 else 0.0
        mandi = total_amount * 0.01 if total_amount > 0 else 0.0
        self.comm_lbl.config(text=f"Comm: ₹ {comm:.2f}")
        self.mandi_fee_lbl.config(text=f"Mandi Fee: ₹ {mandi:.2f}")

    # ---------------- CUSTOMER (F5) MODAL ----------------
    def _on_cust_focus_in(self):
        if self.customer_var.get() == "Select Customer (F5)":
            self.customer_var.set("")
            self.customer_ent.config(fg="#0f172a")

    def _on_cust_focus_out(self):
        if not self.customer_var.get().strip():
            self.customer_var.set("Select Customer (F5)")
            self.customer_ent.config(fg="#94a3b8")

    def _open_customer_search(self):
        modal = tk.Toplevel(self)
        modal.title("Select Customer (F5)")
        modal.geometry("540x480")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        sw = modal.winfo_screenwidth()
        sh = modal.winfo_screenheight()
        modal.geometry(f"540x480+{(sw-540)//2}+{(sh-480)//2}")

        frame = tk.Frame(modal, bg="#ffffff", padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Select Customer", font=("Segoe UI", 13, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w", pady=(0, 10))

        s_box = tk.Frame(frame, bg="#e2e8f0", padx=1, pady=1)
        s_box.pack(fill="x", pady=(0, 10))
        search_ent = tk.Entry(s_box, font=("Segoe UI", 10), relief="flat", bd=0)
        search_ent.pack(fill="both", ipady=4, padx=6)
        search_ent.focus_set()

        canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        cards_box = tk.Frame(canvas, bg="#ffffff")
        cards_box.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        c_win = canvas.create_window((0, 0), window=cards_box, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(c_win, width=e.width))

        customers = list(self.db.collection("customers").find({"is_deleted": 0}))

        def _pick_customer(cust):
            self.selected_customer = cust
            if cust:
                name = cust.get("name") or cust.get("bill_to_name") or "Cash"
                self.customer_var.set(name)
                self.customer_ent.config(fg="#0f172a")

                # Match company
                target_comp_id = cust.get("company_id")
                if target_comp_id:
                    for idx, c in enumerate(self.companies):
                        if c.get("company_id") == target_comp_id:
                            self.company_cbo.current(idx)
                            break
            modal.destroy()
            # Advance to first row code
            self.row_widgets[0]["code"].focus_set()

        def _render(query=""):
            for w in cards_box.winfo_children():
                w.destroy()

            q_lower = query.lower()
            matched = [
                c for c in customers
                if not q_lower
                or q_lower in str(c.get("name", "")).lower()
                or q_lower in str(c.get("bill_to_name", "")).lower()
                or query in str(c.get("phone", ""))
                or query in str(c.get("contact_person_phone", ""))
            ]

            for cust in matched:
                card = tk.Frame(cards_box, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=8, cursor="hand2")
                card.pack(fill="x", pady=2, padx=2)
                tk.Label(card, text=cust.get("name", ""), font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")

                bname = cust.get("bill_to_name")
                bname_str = f"Bill To: {bname}  |  " if (bname and bname != cust.get("name")) else ""
                phone = cust.get("contact_person_phone") or cust.get("phone") or "-"
                tk.Label(card, text=f"{bname_str}Ph: {phone}", font=("Segoe UI", 8), fg="#64748b", bg="#ffffff").pack(anchor="w")

                card.bind("<Button-1>", lambda _e, cu=cust: _pick_customer(cu))

        search_ent.bind("<KeyRelease>", lambda _e: _render(search_ent.get().strip()))
        _render()

    # ---------------- SMART ORDER IMPORTER (F8) ----------------
    def _open_smart_importer(self):
        dlg = tk.Toplevel(self)
        dlg.title("Smart Order Importer (F8)")
        dlg.geometry("620x540")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"620x540+{(sw-620)//2}+{(sh-540)//2}")

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Smart Order Importer", font=("Segoe UI", 14, "bold"), fg="#0f172a", bg="#ffffff").pack(anchor="w")
        tk.Label(
            body,
            text="Paste WhatsApp/SMS order lines or upload text sheet.\nFormat examples: 'Mango 30 kg', 'ITM0012 30', '10 dz Banana'",
            font=("Segoe UI", 9),
            fg="#64748b",
            bg="#ffffff",
            justify="left"
        ).pack(anchor="w", pady=(4, 12))

        txt_frame = tk.Frame(body, bg="#cbd5e1", padx=1, pady=1)
        txt_frame.pack(fill="both", expand=True, pady=(0, 12))
        text_area = tk.Text(txt_frame, font=("Consolas", 10), relief="flat", bd=0, padx=8, pady=8)
        text_area.pack(fill="both", expand=True)
        text_area.insert("1.0", "Mango 30 kg\nBanana 10 dz\nTomato 25 kg\nPotato 50 kg")
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
            dlg.destroy()
            messagebox.showinfo("Smart Importer", f"Smart Importer: {imported_count} items imported successfully.", parent=self)

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
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        imported = 0

        # Find first empty row
        start_idx = 0
        for i, r in enumerate(self.row_widgets):
            if not r["code_var"].get().strip() and not r["item_var"].get().strip():
                start_idx = i
                break

        for line in lines:
            if start_idx >= len(self.row_widgets):
                break

            # Parse lines like "Mango 30 kg", "30 kg Mango", "ITM0012 30"
            tokens = line.split()
            qty = 0.0
            unit = "kg"
            name_parts = []

            for tok in tokens:
                # check if token is pure number
                try:
                    val = float(tok)
                    if qty == 0.0:
                        qty = val
                        continue
                except ValueError:
                    pass

                # check if token ends with unit e.g. "30kg"
                m = re.match(r"^(\d+(?:\.\d+)?)([a-zA-Z]+)$", tok)
                if m:
                    qty = float(m.group(1))
                    unit = m.group(2).lower()
                    continue

                if tok.lower() in [u.lower() for u in self.ITEM_UNITS]:
                    unit = tok.lower()
                    continue

                name_parts.append(tok)

            item_query = " ".join(name_parts).strip()
            if not item_query and not qty:
                continue

            # Match against items cache
            matched_item = None
            for it in self.items_cache:
                if (
                    it.get("item_id", "").lower() == item_query.lower()
                    or it.get("item_alias", "").lower() == item_query.lower()
                    or it.get("name", "").lower() == item_query.lower()
                    or item_query.lower() in it.get("name", "").lower()
                ):
                    matched_item = it
                    break

            row = self.row_widgets[start_idx]
            if matched_item:
                row["item_id"] = matched_item.get("item_id")
                row["code_var"].set(matched_item.get("item_alias") or matched_item.get("item_id"))
                row["item_var"].set(matched_item.get("name"))
                row["rate"] = float(matched_item.get("standard_rate", 0.0))
                unit = matched_item.get("unit") or unit
            else:
                row["item_id"] = item_query
                row["code_var"].set(item_query)
                row["item_var"].set(item_query)

            if qty > 0:
                row["qty_var"].set(f"{qty:g}")

            for u_idx, u in enumerate(self.ITEM_UNITS):
                if u.lower() == unit.lower():
                    row["unit"].current(u_idx)
                    break

            start_idx += 1
            imported += 1

        self._recalculate()
        return imported

    # ---------------- SAVE & VALIDATION (F2 / F10) ----------------
    def _on_f2_save(self):
        self._save_order(print_pdf=False)

    def _on_f10_save_print(self):
        self._save_order(print_pdf=True)

    def _save_order(self, print_pdf: bool = False):
        # 1. Validate Customer
        cust_name = self.customer_var.get().strip()
        if not cust_name or cust_name == "Select Customer (F5)":
            messagebox.showwarning("Customer Required", "Please select a valid customer (F5).", parent=self)
            self._open_customer_search()
            return

        cust_id = self.selected_customer.get("cust_id") if self.selected_customer else cust_name

        # 2. Validate Items
        order_items: List[OrderItem] = []
        for idx, row in enumerate(self.row_widgets):
            code = row["code_var"].get().strip()
            name = row["item_var"].get().strip()
            qty_str = row["qty_var"].get().strip()

            if code or name:
                try:
                    qty = float(qty_str)
                    if qty <= 0:
                        raise ValueError()
                except ValueError:
                    messagebox.showwarning("Invalid Quantity", f"Please enter a valid quantity for row {idx + 1} ({name or code}).", parent=self)
                    row["qty"].focus_set()
                    return

                unit = row["unit"].get()
                if unit == "Unit" or not unit:
                    unit = "kg"

                rate = float(row.get("rate", 0.0))
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

        # 3. Delivery Date Validation
        deliv_str = self.delivery_var.get().strip()
        order_date_str = self.date_var.get().strip()

        try:
            deliv_dt = datetime.strptime(deliv_str.replace(" ", ""), "%d-%m-%Y")
        except ValueError:
            messagebox.showwarning("Invalid Delivery Date", "Please enter a valid delivery date (DD - MM - YYYY).", parent=self)
            self.delivery_ent.focus_set()
            return

        try:
            ord_dt = datetime.strptime(order_date_str.replace(" ", ""), "%d-%m-%Y")
        except ValueError:
            ord_dt = datetime.now()

        if deliv_dt.date() < ord_dt.date():
            messagebox.showwarning("Invalid Date Range", f"Delivery date ({deliv_str}) cannot be before order date ({order_date_str}).", parent=self)
            return

        # 4. Confirmation Dialog (Matches OrderForm.tsx "Schedule for Delivery?")
        deliv_formatted = deliv_dt.strftime("%A, %d %B %Y")
        confirm = messagebox.askyesno(
            "Confirm Delivery Schedule",
            f"Schedule order for delivery on:\n{deliv_formatted}?\n\nCustomer: {cust_name}\nTotal Items: {len(order_items)}",
            parent=self
        )
        if not confirm:
            return

        # 5. Save to Database
        try:
            c_out = int(self.crates_out_var.get().strip() or 0)
        except ValueError:
            c_out = 0

        try:
            c_in = int(self.crates_in_var.get().strip() or 0)
        except ValueError:
            c_in = 0

        selected_comp_name = self.company_cbo.get()
        selected_comp = next((c for c in self.companies if c.get("name") == selected_comp_name), self.companies[0] if self.companies else {})
        company_id = selected_comp.get("company_id", "COMP-001")

        total_amount = sum(i.amount for i in order_items)
        comm = total_amount * 0.05
        mandi = total_amount * 0.01

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

        # 6. Print Preview if F10
        if print_pdf:
            self._print_order(saved_order or {"order_id": final_id, "customer_name": cust_name, "items": [i.model_dump() for i in order_items], "delivery_date": deliv_dt})

        # Return to orders list
        self.reset_form()
        if self.on_navigate:
            self.on_navigate("Orders")

    def _print_order(self, order_dict: Dict[str, Any]):
        try:
            # Build mock bill document for Delivery Challan format
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

    def load_order_for_edit(self, order_id: str):
        """Loads an existing order into the form matching 49-order-detail.png."""
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

        # Load Customer
        cust_name = order.get("customer_name", "")
        self.customer_var.set(cust_name)
        self.customer_ent.config(fg="#0f172a")
        cust_id = order.get("customer_id")
        if cust_id:
            self.selected_customer = self.db.collection("customers").find_one({"cust_id": cust_id, "is_deleted": 0})

        # Load Dates
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

        # Show Status Combobox (Edit mode requirement from 49-order-detail.png)
        self.status_container.pack(side="left", padx=(0, 16))
        st = order.get("status", "pending").capitalize()
        for idx, s in enumerate(["Pending", "Confirmed", "Delivered", "Billed", "Cancelled"]):
            if s.lower() == st.lower():
                self.status_cbo.current(idx)
                break

        # Load Crates & Mandi ops
        self.crates_out_var.set(str(order.get("crates_issued", "")))
        self.crates_in_var.set(str(order.get("crates_returned", "")))

        # Load Rows
        items = order.get("items", [])
        for idx, it in enumerate(items):
            if idx >= len(self.row_widgets):
                break
            row = self.row_widgets[idx]
            row["item_id"] = it.get("item_id", "")
            row["code_var"].set(it.get("item_id", ""))
            row["item_var"].set(it.get("name", ""))
            row["qty_var"].set(f"{float(it.get('qty', 0)):g}")
            row["rate"] = float(it.get("rate", 0.0))

            unit = (it.get("unit") or "kg").lower()
            matched = False
            for u_idx, u in enumerate(self.ITEM_UNITS):
                if u.lower() == unit:
                    row["unit"].current(u_idx)
                    matched = True
                    break
            if not matched:
                row["unit"].current(1)

        self._recalculate()
