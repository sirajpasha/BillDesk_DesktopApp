import logging
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, timezone
from app.utils.currency import format_inr


class DashboardFrame(ttk.Frame):
    """Authentic BillDesk Operations Dashboard matching 02-dashboard.png."""
    def __init__(self, parent, db, billing, user, on_navigate=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.billing = billing
        self.user = user
        self.on_navigate = on_navigate
        self.card_widgets = {}

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Scrollable container for full dashboard
        canvas = tk.Canvas(self, bg="#f8fafc", highlightthickness=0)
        v_scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f8fafc", padx=28, pady=20)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=v_scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")

        # Page Title
        tk.Label(
            scrollable_frame,
            text="Dashboard",
            font=("Segoe UI", 22, "bold"),
            fg="#0f172a",
            bg="#f8fafc"
        ).pack(anchor="w", pady=(0, 20))

        # ---------------- SECTION 1: Sales Analytics ----------------
        self._build_analytics_section(
            scrollable_frame,
            section_title="Sales Analytics",
            card_keys=[
                ("sales_today", "TODAY'S SALES", "₹", "#059669"),
                ("sales_yesterday", "YESTERDAY'S SALES", "↺", "#0284c7"),
                ("sales_this_week", "THIS WEEK SALES", "↗", "#10b981"),
                ("sales_last_week", "LAST WEEK SALES", "📊", "#0284c7"),
                ("sales_this_month", "THIS MONTH SALES", "📅", "#0d9488"),
                ("sales_last_month", "LAST MONTH SALES", "📋", "#64748b"),
            ]
        )

        # ---------------- SECTION 2: Order Analytics ----------------
        self._build_analytics_section(
            scrollable_frame,
            section_title="Order Analytics",
            card_keys=[
                ("orders_today", "TODAY'S ORDERS", "🛒", "#6366f1"),
                ("orders_yesterday", "YESTERDAY'S ORDERS", "↺", "#4f46e5"),
                ("orders_this_week", "THIS WEEK ORDERS", "📦", "#8b5cf6"),
                ("orders_last_week", "LAST WEEK ORDERS", "📊", "#6366f1"),
                ("orders_this_month", "THIS MONTH ORDERS", "📅", "#7c3aed"),
                ("orders_last_month", "LAST MONTH ORDERS", "📋", "#64748b"),
            ]
        )

        # ---------------- SECTION 3: Purchase Analytics ----------------
        self._build_analytics_section(
            scrollable_frame,
            section_title="Purchase Analytics",
            card_keys=[
                ("pur_today", "TODAY'S PURCHASES", "🚚", "#ea580c"),
                ("pur_this_week", "THIS WEEK PURCHASES", "↗", "#f59e0b"),
                ("pur_this_month", "THIS MONTH PURCHASES", "📅", "#d97706"),
                ("pur_last_month", "LAST MONTH PURCHASES", "📋", "#64748b"),
            ]
        )

    def _build_analytics_section(self, parent, section_title: str, card_keys: list):
        tk.Label(
            parent,
            text=section_title,
            font=("Segoe UI", 13, "bold"),
            fg="#1e293b",
            bg="#f8fafc"
        ).pack(anchor="w", pady=(14, 10))

        # Grid of cards: 4 columns wide
        grid_frame = tk.Frame(parent, bg="#f8fafc")
        grid_frame.pack(fill="x", pady=(0, 16))

        for idx, (key, title, icon_char, color) in enumerate(card_keys):
            row = idx // 4
            col = idx % 4

            card = tk.Frame(
                grid_frame,
                bg="#ffffff",
                highlightbackground="#e2e8f0",
                highlightthickness=1,
                padx=16,
                pady=14
            )
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            grid_frame.columnconfigure(col, weight=1)

            # Top Row: Icon + Header
            top_row = tk.Frame(card, bg="#ffffff")
            top_row.pack(fill="x")

            # Colored Icon Pill
            icon_lbl = tk.Label(
                top_row,
                text=icon_char,
                font=("Segoe UI", 10, "bold"),
                fg=color,
                bg="#f1f5f9",
                width=3,
                height=1
            )
            icon_lbl.pack(side="left", padx=(0, 8))

            title_lbl = tk.Label(
                top_row,
                text=title,
                font=("Segoe UI", 8, "bold"),
                fg="#64748b",
                bg="#ffffff"
            )
            title_lbl.pack(side="left")

            # Big Value Label
            val_lbl = tk.Label(
                card,
                text="₹0.00",
                font=("Segoe UI", 18, "bold"),
                fg="#0f172a",
                bg="#ffffff"
            )
            val_lbl.pack(anchor="w", pady=(8, 2))

            # Subtitle / Count
            sub_lbl = tk.Label(
                card,
                text="0 bills",
                font=("Segoe UI", 9),
                fg="#94a3b8",
                bg="#ffffff"
            )
            sub_lbl.pack(anchor="w")

            self.card_widgets[key] = (val_lbl, sub_lbl)

    def refresh(self):
        """Aggregate sales, orders, and procurement metrics for all date buckets."""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # Current week range (Monday to Sunday)
        start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=7)
        start_last_week = start_of_week - timedelta(days=7)

        # Month range
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Previous month
        first_this_month = now.replace(day=1)
        last_day_prev_month = first_this_month - timedelta(days=1)
        start_prev_month = last_day_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Sales Analytics
        try:
            bills = list(self.db.collection("bills").find({"status": {"$ne": "void"}, "is_deleted": 0}))
        except Exception:
            bills = []

        def _calc_sales(filter_fn):
            matched = [b for b in bills if filter_fn(b)]
            total = sum(float(b.get("total_amount", 0.0)) for b in matched)
            return total, len(matched)

        # Helpers for date matching
        def _to_dt(doc, field):
            val = doc.get(field)
            if isinstance(val, datetime):
                return val.replace(tzinfo=None)
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val[:10])
                except Exception:
                    logging.getLogger(__name__).warning("Ignored error", exc_info=True)
            return None

        # Sales Buckets
        s_today, c_today = _calc_sales(lambda b: b.get("invoice_date") == today_str)
        s_yest, c_yest = _calc_sales(lambda b: b.get("invoice_date") == yesterday_str)
        s_tweek, c_tweek = _calc_sales(lambda b: _to_dt(b, "invoice_date") and start_of_week <= _to_dt(b, "invoice_date") < end_of_week)
        s_lweek, c_lweek = _calc_sales(lambda b: _to_dt(b, "invoice_date") and start_last_week <= _to_dt(b, "invoice_date") < start_of_week)
        s_tmonth, c_tmonth = _calc_sales(lambda b: _to_dt(b, "invoice_date") and _to_dt(b, "invoice_date") >= start_of_month)
        s_lmonth, c_lmonth = _calc_sales(lambda b: _to_dt(b, "invoice_date") and start_prev_month <= _to_dt(b, "invoice_date") < start_of_month)

        self._set_card("sales_today", s_today, f"{c_today} bills")
        self._set_card("sales_yesterday", s_yest, f"{c_yest} bills")
        self._set_card("sales_this_week", s_tweek, f"{c_tweek} bills")
        self._set_card("sales_last_week", s_lweek, f"{c_lweek} bills")
        self._set_card("sales_this_month", s_tmonth, f"{c_tmonth} bills")
        self._set_card("sales_last_month", s_lmonth, f"{c_lmonth} bills")

        # 2. Orders Analytics
        try:
            orders = list(self.db.collection("orders").find({"is_deleted": 0}))
        except Exception:
            orders = []

        def _calc_orders(filter_fn):
            matched = [o for o in orders if filter_fn(o)]
            total = sum(float(o.get("total_amount", 0.0)) for o in matched)
            return total, len(matched)

        o_today, co_today = _calc_orders(lambda o: _to_dt(o, "order_date") and _to_dt(o, "order_date").strftime("%Y-%m-%d") == today_str)
        o_yest, co_yest = _calc_orders(lambda o: _to_dt(o, "order_date") and _to_dt(o, "order_date").strftime("%Y-%m-%d") == yesterday_str)
        o_tweek, co_tweek = _calc_orders(lambda o: _to_dt(o, "order_date") and start_of_week <= _to_dt(o, "order_date") < end_of_week)
        o_lweek, co_lweek = _calc_orders(lambda o: _to_dt(o, "order_date") and start_last_week <= _to_dt(o, "order_date") < start_of_week)
        o_tmonth, co_tmonth = _calc_orders(lambda o: _to_dt(o, "order_date") and _to_dt(o, "order_date") >= start_of_month)
        o_lmonth, co_lmonth = _calc_orders(lambda o: _to_dt(o, "order_date") and start_prev_month <= _to_dt(o, "order_date") < start_of_month)

        self._set_card("orders_today", o_today, f"{co_today} orders")
        self._set_card("orders_yesterday", o_yest, f"{co_yest} orders")
        self._set_card("orders_this_week", o_tweek, f"{co_tweek} orders")
        self._set_card("orders_last_week", o_lweek, f"{co_lweek} orders")
        self._set_card("orders_this_month", o_tmonth, f"{co_tmonth} orders")
        self._set_card("orders_last_month", o_lmonth, f"{co_lmonth} orders")

        # 3. Purchase Analytics
        try:
            purchases = list(self.db.collection("purchase_bills").find({"is_deleted": 0}))
        except Exception:
            purchases = []

        def _calc_purchases(filter_fn):
            matched = [p for p in purchases if filter_fn(p)]
            total = sum(float(p.get("total_amount", 0.0)) for p in matched)
            return total, len(matched)

        p_today, cp_today = _calc_purchases(lambda p: _to_dt(p, "bill_date") and _to_dt(p, "bill_date").strftime("%Y-%m-%d") == today_str)
        p_tweek, cp_tweek = _calc_purchases(lambda p: _to_dt(p, "bill_date") and start_of_week <= _to_dt(p, "bill_date") < end_of_week)
        p_tmonth, cp_tmonth = _calc_purchases(lambda p: _to_dt(p, "bill_date") and _to_dt(p, "bill_date") >= start_of_month)
        p_lmonth, cp_lmonth = _calc_purchases(lambda p: _to_dt(p, "bill_date") and start_prev_month <= _to_dt(p, "bill_date") < start_of_month)

        self._set_card("pur_today", p_today, f"{cp_today} purchases")
        self._set_card("pur_this_week", p_tweek, f"{cp_tweek} purchases")
        self._set_card("pur_this_month", p_tmonth, f"{cp_tmonth} purchases")
        self._set_card("pur_last_month", p_lmonth, f"{cp_lmonth} purchases")

    def _set_card(self, key: str, amount: float, subtitle: str):
        if key in self.card_widgets:
            val_lbl, sub_lbl = self.card_widgets[key]
            val_lbl.config(text=format_inr(amount))
            sub_lbl.config(text=subtitle)
