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
        scrollable_frame = tk.Frame(canvas, bg="#f8fafc", padx=28, pady=12)

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
            font=("Segoe UI", 18, "bold"),
            fg="#0f172a",
            bg="#f8fafc"
        ).pack(anchor="w", pady=(0, 8))

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
                ("pur_today", "TODAY'S PURCHASE", "🚚", "#ea580c"),
                ("pur_yesterday", "YESTERDAY'S PURCHASE", "↺", "#f59e0b"),
                ("pur_this_week", "THIS WEEK PURCHASE", "↗", "#f59e0b"),
                ("pur_last_week", "LAST WEEK PURCHASE", "📊", "#d97706"),
                ("pur_this_month", "THIS MONTH PURCHASE", "📅", "#d97706"),
                ("pur_last_month", "LAST MONTH PURCHASE", "📋", "#64748b"),
            ]
        )

        # ---------------- QUICK ACTIONS ----------------
        self._build_quick_actions(scrollable_frame)

        # ---------------- AT A GLANCE: what needs attention today (below the fold on a small screen) ----------------
        self._build_insights(scrollable_frame)

    def _build_insights(self, parent):
        tk.Label(parent, text="At a glance", font=("Segoe UI", 11, "bold"), fg="#1e293b", bg="#f8fafc").pack(anchor="w", pady=(0, 4))
        row = tk.Frame(parent, bg="#f8fafc")
        row.pack(fill="x", pady=(0, 4))
        self.insight_vals = {}
        for col, (key, title, color) in enumerate((
                ("receivable", "TO COLLECT (RECEIVABLES)", "#4f46e5"),
                ("overdue", "OVERDUE OVER 30 DAYS", "#dc2626"),
                ("collected", "COLLECTED TODAY", "#059669"),
                ("pending", "ORDERS WAITING", "#d97706"))):
            card = tk.Frame(row, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
            card.grid(row=0, column=col, sticky="nsew", padx=4)
            row.columnconfigure(col, weight=1, uniform="glance")
            tk.Label(card, text=title, font=("Segoe UI", 7, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
            val = tk.Label(card, text="0", font=("Segoe UI", 13, "bold"), fg=color, bg="#ffffff")
            val.pack(anchor="w", pady=(3, 0))
            sub = tk.Label(card, text="", font=("Segoe UI", 8), fg="#94a3b8", bg="#ffffff")
            sub.pack(anchor="w")
            self.insight_vals[key] = (val, sub)

        panels = tk.Frame(parent, bg="#f8fafc")
        panels.pack(fill="x", pady=(0, 4))
        panels.columnconfigure(0, weight=3)
        panels.columnconfigure(1, weight=2)
        left = tk.Frame(panels, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
        left.grid(row=0, column=0, sticky="nsew", padx=6)
        tk.Label(left, text="Sales - last 14 days", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")
        self.trend_canvas = tk.Canvas(left, height=100, bg="#ffffff", highlightthickness=0)
        self.trend_canvas.pack(fill="x", pady=(6, 0))
        self.trend_canvas.bind("<Configure>", lambda _e: self._draw_trend())
        self._trend_data = []
        right = tk.Frame(panels, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
        right.grid(row=0, column=1, sticky="nsew", padx=6)
        tk.Label(right, text="Customers who owe the most", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w")
        self.top_owing_box = tk.Frame(right, bg="#ffffff")
        self.top_owing_box.pack(fill="x", pady=(6, 0))

    def _draw_trend(self):
        c = self.trend_canvas
        c.delete("all")
        data = self._trend_data
        w, h = max(c.winfo_width(), 200), 100
        if not data or max(v for _d, v in data) <= 0:
            c.create_text(w // 2, h // 2, text="No sales in the last 14 days", fill="#94a3b8", font=("Segoe UI", 10))
            return
        top = max(v for _d, v in data)
        slot = (w - 20) / len(data)
        for i, (day, val) in enumerate(data):
            bar_h = int((h - 36) * val / top)
            x0 = 10 + i * slot + slot * 0.15
            x1 = 10 + (i + 1) * slot - slot * 0.15
            c.create_rectangle(x0, h - 22 - bar_h, x1, h - 22, fill="#4f46e5" if i == len(data) - 1 else "#818cf8", outline="")
            c.create_text((x0 + x1) / 2, h - 10, text=day.strftime("%d"), fill="#64748b", font=("Segoe UI", 8))
            if val > 0:
                c.create_text((x0 + x1) / 2, h - 28 - bar_h, text=f"{val / 1000:.0f}k" if val >= 1000 else f"{val:.0f}", fill="#334155", font=("Segoe UI", 7))

    def _refresh_insights(self, bills, to_dt):
        now = datetime.now()
        days = [(now - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0) for n in range(13, -1, -1)]
        per_day = {d.strftime("%Y-%m-%d"): 0.0 for d in days}
        for b in bills:
            dt = to_dt(b, "invoice_date")
            if dt:
                k = dt.strftime("%Y-%m-%d")
                if k in per_day:
                    per_day[k] += float(b.get("total_amount", 0.0) or 0.0)
        self._trend_data = [(d, per_day[d.strftime("%Y-%m-%d")]) for d in days]
        self._draw_trend()

        try:
            from app.services.payment_service import PaymentService
            ar = PaymentService(self.db).get_ar_aging()
        except Exception:
            logging.getLogger(__name__).warning("Dashboard receivables failed", exc_info=True)
            ar = {"summary": {}, "customers": []}
        summ = ar.get("summary", {})
        over = sum(summ.get(k, 0.0) for k in ("31_60", "61_90", "90_plus"))
        v, sub = self.insight_vals["receivable"]
        v.config(text=format_inr(summ.get("total", 0.0)))
        sub.config(text=f"{len(ar.get('customers', []))} customers" + (f"  |  advances held {format_inr(summ['advances'])}" if summ.get("advances") else ""))
        v, sub = self.insight_vals["overdue"]
        v.config(text=format_inr(over))
        sub.config(text="31+ days old" if over else "nothing overdue")

        collected, n_pay = 0.0, 0
        try:
            for p in self.db.collection("payments").find({"is_deleted": {"$ne": 1}}):
                dt = to_dt(p, "payment_date")
                if dt and dt.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d") and p.get("party_type") in (None, "customer"):
                    collected += float(p.get("amount", 0.0) or 0.0)
                    n_pay += 1
        except Exception:
            logging.getLogger(__name__).warning("Dashboard collections failed", exc_info=True)
        v, sub = self.insight_vals["collected"]
        v.config(text=format_inr(collected))
        sub.config(text=f"{n_pay} receipts")

        try:
            from app.services.order_service import OrderService
            pending = OrderService(self.db).order_stats()["pending"]
        except Exception:
            logging.getLogger(__name__).warning("Dashboard order count failed", exc_info=True)
            pending = 0
        v, sub = self.insight_vals["pending"]
        v.config(text=str(pending))
        sub.config(text="not yet billed" if pending else "all caught up")

        for w in self.top_owing_box.winfo_children():
            w.destroy()
        rows = ar.get("customers", [])[:4]
        if not rows:
            tk.Label(self.top_owing_box, text="Nobody owes anything.", font=("Segoe UI", 9), fg="#94a3b8", bg="#ffffff").pack(anchor="w")
        for r in rows:
            line = tk.Frame(self.top_owing_box, bg="#ffffff")
            line.pack(fill="x", pady=1)
            tk.Label(line, text=str(r["customer_name"])[:28], font=("Segoe UI", 9), fg="#334155", bg="#ffffff").pack(side="left")
            tk.Label(line, text=format_inr(r["total"]), font=("Segoe UI", 9, "bold"), fg="#0f172a", bg="#ffffff").pack(side="right")

    def _build_analytics_section(self, parent, section_title: str, card_keys: list):
        tk.Label(parent, text=section_title, font=("Segoe UI", 11, "bold"), fg="#1e293b", bg="#f8fafc").pack(anchor="w", pady=(8, 4))

        grid_frame = tk.Frame(parent, bg="#f8fafc")
        grid_frame.pack(fill="x", pady=(0, 4))

        per_row = 6
        for idx, (key, title, icon_char, color) in enumerate(card_keys):
            row, col = divmod(idx, per_row)
            card = tk.Frame(grid_frame, bg="#ffffff", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=6)
            card.grid(row=row, column=col, sticky="nsew", padx=4, pady=3)
            grid_frame.columnconfigure(col, weight=1, uniform=f"cards-{section_title}")

            top_row = tk.Frame(card, bg="#ffffff")
            top_row.pack(fill="x")
            tk.Label(top_row, text=icon_char, font=("Segoe UI", 8, "bold"), fg=color, bg="#ffffff").pack(side="left", padx=(0, 5))
            tk.Label(top_row, text=title, font=("Segoe UI", 7, "bold"), fg="#64748b", bg="#ffffff").pack(side="left")

            val_lbl = tk.Label(card, text="\u20b90.00", font=("Segoe UI", 13, "bold"), fg="#0f172a", bg="#ffffff")
            val_lbl.pack(anchor="w", pady=(3, 0))
            sub_lbl = tk.Label(card, text="0 bills", font=("Segoe UI", 8), fg="#94a3b8", bg="#ffffff")
            sub_lbl.pack(anchor="w")
            self.card_widgets[key] = (val_lbl, sub_lbl)

    def _build_quick_actions(self, parent):
        tk.Label(parent, text="Quick Actions", font=("Segoe UI", 11, "bold"), fg="#1e293b", bg="#f8fafc").pack(anchor="w", pady=(10, 4))
        row = tk.Frame(parent, bg="#f8fafc")
        row.pack(fill="x", pady=(0, 6))
        actions = (
            ("QUICK ACTION", "New Bill", "New Bill", "#6366f1", "\U0001f9fe"),
            ("MANAGE", "Items", "Item Master", "#10b981", "\U0001f4e6"),
            ("VIEW", "Customers", "Customer Master", "#f59e0b", "\U0001f465"),
            ("MANAGE", "Suppliers", "Supplier Master", "#8b5cf6", "\U0001f6d2"),
            ("HISTORY", "Existing Bills", "Bill History", "#f472b6", "\U0001f553"),
        )
        self.quick_buttons = {}
        for col, (kicker, label, page, color, icon) in enumerate(actions):
            btn = tk.Frame(row, bg=color, cursor="hand2", padx=12, pady=8)
            btn.grid(row=0, column=col, sticky="nsew", padx=4)
            row.columnconfigure(col, weight=1, uniform="quick")
            tk.Label(btn, text=icon, font=("Segoe UI", 12), bg=color, fg="#ffffff").pack(side="left", padx=(0, 10))
            box = tk.Frame(btn, bg=color)
            box.pack(side="left")
            tk.Label(box, text=kicker, font=("Segoe UI", 7, "bold"), bg=color, fg="#ffffff").pack(anchor="w")
            tk.Label(box, text=label, font=("Segoe UI", 10, "bold"), bg=color, fg="#ffffff").pack(anchor="w")
            for w in (btn, box, *btn.winfo_children(), *box.winfo_children()):
                w.bind("<Button-1>", lambda _e, p=page: self._go(p))
            self.quick_buttons[page] = btn

    def _go(self, page: str) -> None:
        if self.on_navigate:
            self.on_navigate(page)

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
        s_today, c_today = _calc_sales(lambda b: _to_dt(b, "invoice_date") and _to_dt(b, "invoice_date").strftime("%Y-%m-%d") == today_str)
        s_yest, c_yest = _calc_sales(lambda b: _to_dt(b, "invoice_date") and _to_dt(b, "invoice_date").strftime("%Y-%m-%d") == yesterday_str)
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
        self._refresh_insights(bills, _to_dt)

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
        p_yest, cp_yest = _calc_purchases(lambda p: _to_dt(p, "bill_date") and _to_dt(p, "bill_date").strftime("%Y-%m-%d") == yesterday_str)
        p_lweek, cp_lweek = _calc_purchases(lambda p: _to_dt(p, "bill_date") and start_last_week <= _to_dt(p, "bill_date") < start_of_week)
        p_tweek, cp_tweek = _calc_purchases(lambda p: _to_dt(p, "bill_date") and start_of_week <= _to_dt(p, "bill_date") < end_of_week)
        p_tmonth, cp_tmonth = _calc_purchases(lambda p: _to_dt(p, "bill_date") and _to_dt(p, "bill_date") >= start_of_month)
        p_lmonth, cp_lmonth = _calc_purchases(lambda p: _to_dt(p, "bill_date") and start_prev_month <= _to_dt(p, "bill_date") < start_of_month)

        self._set_card("pur_today", p_today, f"{cp_today} orders")
        self._set_card("pur_yesterday", p_yest, f"{cp_yest} orders")
        self._set_card("pur_last_week", p_lweek, f"{cp_lweek} orders")
        self._set_card("pur_this_week", p_tweek, f"{cp_tweek} orders")
        self._set_card("pur_this_month", p_tmonth, f"{cp_tmonth} orders")
        self._set_card("pur_last_month", p_lmonth, f"{cp_lmonth} orders")

    def _set_card(self, key: str, amount: float, subtitle: str):
        if key in self.card_widgets:
            val_lbl, sub_lbl = self.card_widgets[key]
            val_lbl.config(text=format_inr(amount))
            sub_lbl.config(text=subtitle)
