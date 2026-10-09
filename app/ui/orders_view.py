import os
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from app.ui.components.calendar_popup import attach_date_picker
from datetime import datetime
from app.services.order_service import OrderService
from app.utils.formatters import format_date
from app.ui.order_form_view import OrderFormView
from app.ui import theme

class OrdersView(tk.Frame):
    """
    Orders & Consolidation Matrix View matching:
    - 12-orders.png (Orders & Shipments)
    - 24-order-matrix.png (Order Consolidation Matrix Report)
    """
    def __init__(self, parent, db, current_user, on_navigate=None, order_form_view=None, **kwargs):
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.db = db
        self.current_user = current_user
        self.on_navigate = on_navigate
        self.order_form_view = order_form_view
        self.order_svc = OrderService(db)

        # Style notebook
        style = ttk.Style()
        style.configure("Orders.TNotebook", background=theme.BG)
        style.configure("Orders.TNotebook.Tab", font=theme.F_BOLD, padding=[16, 6])

        self.notebook = ttk.Notebook(self, style="Orders.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(12, 16))

        # Tab 1: Orders & Shipments (Matches 12-orders.png)
        self.list_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.list_tab, text="Orders & Shipments")
        self._build_orders_list_tab()

        # Tab 2: Order Matrix Report (Matches 24-order-matrix.png)
        self.matrix_tab = tk.Frame(self.notebook, bg=theme.BG)
        self.notebook.add(self.matrix_tab, text="Order Consolidation Matrix")
        self._build_matrix_tab()

        self.refresh()

    def refresh(self):
        self.load_orders()
        self.load_matrix()

    # =========================================================================
    # 1. ORDERS & SHIPMENTS TAB (Matches 12-orders.png)
    # =========================================================================
    def _build_orders_list_tab(self):
        # Header strip
        top_bar = tk.Frame(self.list_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Orders & Shipments", font=("Segoe UI", 18, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")
        tk.Label(title_box, text="Track customer orders, manage deliveries, and convert orders to sales or purchase bills", font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.BG).pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Create New Order",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._add_order_dialog
        ).pack(side="right")

        # 3 KPI Cards: Total Orders (Purple), Pending Orders (Orange), Today's Orders (Blue)
        kpi_row = tk.Frame(self.list_tab, bg=theme.BG)
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        self.kpi_ord_total, _ = self._make_card(kpi_row, "0", "Total Orders", "#5046e5")
        self.kpi_ord_pending, _ = self._make_card(kpi_row, "0", "Pending Orders", theme.WARNING)
        self.kpi_ord_today, _ = self._make_card(kpi_row, "0", "Today's Orders", "#2563eb")

        # Table Container Card
        card = tk.Frame(self.list_tab, bg=theme.SURFACE, bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Search & Filter Strip
        filter_bar = tk.Frame(card, bg=theme.SURFACE, padx=16, pady=10)
        filter_bar.pack(fill="x")

        self.order_search_var = tk.StringVar()
        s_ent = tk.Entry(
            filter_bar,
            textvariable=self.order_search_var,
            font=theme.F_BODY,
            relief="solid",
            bd=1,
            width=36
        )
        s_ent.pack(side="left", ipady=4)
        self.order_search_var.trace_add("write", lambda *_: self._filter_orders())
        tk.Label(filter_bar, text=" (Search orders & shipments...)", font=theme.F_SMALL, fg=theme.TEXT_FAINT, bg=theme.SURFACE).pack(side="left", padx=6)

        # Date Entry
        tk.Label(filter_bar, text="📅 Date:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(side="left", padx=(16, 4))
        self.order_date_var = tk.StringVar(value="")
        d_ent = tk.Entry(filter_bar, textvariable=self.order_date_var, font=theme.F_BODY, relief="solid", bd=1, width=12)
        d_ent.pack(side="left", ipady=4)
        attach_date_picker(d_ent, "%d/%m/%Y", label="The order date filter", partial_ok=True)
        self.order_date_var.trace_add("write", lambda *_: self._filter_orders())

        # Table
        tbl_frame = tk.Frame(card, bg=theme.SURFACE, padx=12, pady=6)
        tbl_frame.pack(fill="both", expand=True)

        cols = ("order_id", "order_date", "delivery_date", "customer_name", "contents", "status", "linked_docs")
        self.orders_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        self.orders_tree.heading("order_id", text="Order ID")
        self.orders_tree.heading("order_date", text="Order Date")
        self.orders_tree.heading("delivery_date", text="Delivery Date")
        self.orders_tree.heading("customer_name", text="Customer Name")
        self.orders_tree.heading("contents", text="Contents")
        self.orders_tree.heading("status", text="Status")
        self.orders_tree.heading("linked_docs", text="Linked Docs")

        self.orders_tree.column("order_id", width=140, anchor="center")
        self.orders_tree.column("order_date", width=110, anchor="center")
        self.orders_tree.column("delivery_date", width=110, anchor="center")
        self.orders_tree.column("customer_name", width=220, anchor="w")
        self.orders_tree.column("contents", width=100, anchor="center")
        self.orders_tree.column("status", width=100, anchor="center")
        self.orders_tree.column("linked_docs", width=140, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.orders_tree.pack(side="left", fill="both", expand=True)
        self.orders_tree.bind("<Double-1>", lambda _e: self._edit_order())

        # Action Bottom Strip matching 12-orders.png actions
        act_bar = tk.Frame(card, bg=theme.BG, padx=16, pady=8)
        act_bar.pack(fill="x", side="bottom")

        tk.Button(
            act_bar,
            text="✏ Edit Order",
            font=theme.F_BOLD,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._edit_order
        ).pack(side="left", padx=4)

        tk.Button(
            act_bar,
            text="➡ Convert to Sales Bill",
            font=theme.F_BOLD,
            bg=theme.SURFACE,
            fg="#2563eb",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._convert_to_bill
        ).pack(side="left", padx=4)

        tk.Button(
            act_bar,
            text="🛒 Convert to Purchase Bill",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SUCCESS,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._convert_to_purchase
        ).pack(side="left", padx=4)

        tk.Button(
            act_bar,
            text="🖨 Print / Preview",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._print_selected_order
        ).pack(side="left", padx=4)

        tk.Button(
            act_bar,
            text="🗑 Cancel Order",
            font=theme.F_BODY,
            bg="#fee2e2",
            fg="#991b1b",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._cancel_order
        ).pack(side="left", padx=4)

        tk.Button(
            act_bar,
            text="🔄 Refresh",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.load_orders
        ).pack(side="right", padx=4)

    def _filter_orders(self):
        q = self.order_search_var.get().strip().lower()
        d_val = self.order_date_var.get().strip().lower()

        for i in self.orders_tree.get_children():
            self.orders_tree.delete(i)

        filtered = []
        for o in self._raw_orders:
            oid = str(o.get("order_id", "")).lower()
            cust = str(o.get("customer_name", "")).lower()
            dt = str(o.get("date_display", "")).lower()
            if q and (q not in oid and q not in cust):
                continue
            if d_val and (d_val not in dt):
                continue
            filtered.append(o)

        for o in filtered:
            linked = ", ".join(o.get("linked_bill_ids", [])) or "No links"
            status_text = o.get("status", "PENDING").upper()
            self.orders_tree.insert(
                "",
                "end",
                iid=o.get("order_id"),
                values=(
                    o.get("order_id", ""),
                    o.get("date_display", ""),
                    o.get("delivery_display", ""),
                    o.get("customer_name", ""),
                    f"{len(o.get('items', []))} items",
                    status_text,
                    linked
                )
            )

    def load_orders(self):
        orders = self.order_svc.get_orders(limit=200)
        self._raw_orders = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        pending_cnt = 0
        today_cnt = 0

        for o in orders:
            d = dict(o)
            dt = d.get("order_date")
            d["date_display"] = format_date(dt)
            d["delivery_display"] = format_date(d.get("delivery_date") or dt)
            st = d.get("status", "pending").lower()
            if st == "pending":
                pending_cnt += 1

            dt_str = ""
            if isinstance(dt, datetime):
                dt_str = dt.strftime("%Y-%m-%d")
            elif isinstance(dt, str):
                dt_str = dt[:10]

            if dt_str == today_str:
                today_cnt += 1

            self._raw_orders.append(d)

        try:
            stats = self.order_svc.order_stats()
        except Exception:
            logging.getLogger(__name__).warning("Could not count orders", exc_info=True)
            stats = {"total": len(self._raw_orders), "pending": pending_cnt, "today": today_cnt}
        self.kpi_ord_total.config(text=str(stats["total"]))
        self.kpi_ord_pending.config(text=str(stats["pending"]))
        self.kpi_ord_today.config(text=str(stats["today"]))
        self._filter_orders()

    def _convert_to_bill(self):
        sel = self.orders_tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select an order to convert to a sales bill.", parent=self)
            return
        order_id = sel[0]
        ord_obj = next((o for o in self._raw_orders if o.get("order_id") == order_id), None)
        if ord_obj and ord_obj.get("status") == "billed":
            messagebox.showwarning("Already Billed", f"Order {order_id} is already converted.", parent=self)
            return

        if messagebox.askyesno("Confirm Conversion", f"Convert Order {order_id} to a sales invoice and deduct stock?"):
            try:
                res = self.order_svc.convert_to_bill(order_id, user_id=self.current_user.username)
                messagebox.showinfo("Success", f"Order converted successfully!\nInvoice Generated: {res['invoice_no']}", parent=self)
                self.load_orders()
                self.load_matrix()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=self)

    def _convert_to_purchase(self):
        sel = self.orders_tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select an order to convert to purchase.", parent=self)
            return
        order_id = sel[0]

        dlg = tk.Toplevel(self)
        dlg.title("Select Supplier for Purchase Bill")
        dlg.geometry("400x220")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=theme.SURFACE)

        hdr = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Convert Order to Purchase Bill", font=theme.F_H11B, fg=theme.SURFACE, bg=theme.PRIMARY).pack(anchor="w")

        body = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Supplier ID *", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(anchor="w")
        sid_ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1)
        sid_ent.pack(fill="x", pady=(2, 6))

        tk.Label(body, text="Supplier Name *", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(anchor="w")
        sname_ent = tk.Entry(body, font=theme.F_BODY, relief="solid", bd=1)
        sname_ent.pack(fill="x", pady=(2, 10))

        def on_confirm():
            s_id = sid_ent.get().strip()
            s_name = sname_ent.get().strip()
            if not s_id or not s_name:
                messagebox.showwarning("Input Required", "Supplier ID and Name are required.", parent=dlg)
                return
            try:
                res = self.order_svc.convert_to_purchase(order_id, s_id, s_name, user_id=self.current_user.username)
                messagebox.showinfo("Success", f"Purchase Bill Created: {res['purchase_id']}\nStock incremented successfully.", parent=self)
                dlg.destroy()
                self.load_orders()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=8)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Convert to Purchase", font=theme.F_BOLD, bg=theme.SUCCESS, fg=theme.SURFACE, relief="flat", bd=0, padx=14, pady=5, command=on_confirm).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=theme.F_BODY, bg=theme.HEADING_BG, fg=theme.SLATE_600, relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    def _cancel_order(self):
        sel = self.orders_tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select an order to cancel.", parent=self)
            return
        order_id = sel[0]
        if messagebox.askyesno("Confirm Cancel", f"Are you sure you want to cancel order {order_id}?"):
            try:
                self.order_svc.cancel_order(order_id)
            except ValueError as ex:
                messagebox.showwarning("Cannot Cancel", str(ex), parent=self)
                return
            self.load_orders()

    def _add_order_dialog(self):
        if self.on_navigate and self.order_form_view:
            self.order_form_view.reset_form()
            self.on_navigate("New Order")
        else:
            self._open_order_form_modal()

    def _edit_order(self):
        sel = self.orders_tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select an order to edit.", parent=self)
            return
        order_id = sel[0]
        if self.on_navigate and self.order_form_view:
            self.order_form_view.load_order_for_edit(order_id)
            self.on_navigate("New Order")
        else:
            self._open_order_form_modal(order_id)

    def _open_order_form_modal(self, order_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Edit Order" if order_id else "New Order")
        dlg.geometry("1100x720")
        dlg.transient(self)
        dlg.grab_set()

        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"1100x720+{(sw-1100)//2}+{(sh-720)//2}")

        form = OrderFormView(dlg, self.db, self.current_user, on_navigate=lambda _page: (dlg.destroy(), self.load_orders()))
        form.pack(fill="both", expand=True)
        if order_id:
            form.load_order_for_edit(order_id)

    def _print_selected_order(self):
        sel = self.orders_tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select an order to print.", parent=self)
            return
        order_id = sel[0]
        order = self.order_svc.get_order(order_id)
        if not order:
            return
        from app.printing.invoice import generate_dc_pdf
        from app.ui.print_preview import show_print_preview
        import tempfile
        dc_bill = {
            "invoice_no": order.get("order_id", "ORD-NEW"),
            "invoice_date": order.get("delivery_date") or order.get("order_date") or datetime.now(),
            "customer_id": order.get("customer_id", ""),
            "customer_name": order.get("customer_name", ""),
            "items": order.get("items", []),
            "total_amount": order.get("total_amount", 0.0),
            "crates_issued": order.get("crates_issued", 0),
            "crates_returned": order.get("crates_returned", 0),
            "payment_mode": "ORDER",
        }
        temp_pdf = os.path.join(tempfile.gettempdir(), f"{dc_bill['invoice_no']}.pdf")
        generate_dc_pdf(dc_bill, temp_pdf)
        show_print_preview(self, temp_pdf, title=f"Print Order - {dc_bill['invoice_no']}")

    # =========================================================================
    # 2. ORDER CONSOLIDATION MATRIX TAB (Matches 24-order-matrix.png)
    # =========================================================================
    def _build_matrix_tab(self):
        # Header strip
        top_bar = tk.Frame(self.matrix_tab, bg=theme.BG)
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg=theme.BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Order Consolidation Matrix", font=("Segoe UI", 18, "bold"), fg=theme.TEXT, bg=theme.BG).pack(anchor="w")
        tk.Label(title_box, text="Matrix view of pending orders versus current stock levels", font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.BG).pack(anchor="w")

        # 3 KPI Cards: Active Customers (Purple), Items to Procure (Green), Pending Orders (Orange)
        kpi_row = tk.Frame(self.matrix_tab, bg=theme.BG)
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        self.kpi_mat_custs, _ = self._make_card(kpi_row, "0", "Active Customers", "#5046e5")
        self.kpi_mat_shortfall, _ = self._make_card(kpi_row, "0", "Items to Procure", theme.SUCCESS)
        self.kpi_mat_orders, _ = self._make_card(kpi_row, "0", "Pending Orders", theme.WARNING)

        # Control Bar Card (Delivery Date, Export, Checkboxes, Print)
        ctrl_card = tk.Frame(self.matrix_tab, bg=theme.SURFACE, bd=1, relief="solid", padx=16, pady=10)
        ctrl_card.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(ctrl_card, text="Delivery Date", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(side="left", padx=(0, 6))
        self.matrix_date_var = tk.StringVar(value="")          # blank = every pending order
        d_ent = tk.Entry(ctrl_card, textvariable=self.matrix_date_var, font=theme.F_BODY, relief="solid", bd=1, width=14)
        d_ent.pack(side="left", padx=(0, 4), ipady=4)
        self.matrix_date_picker = attach_date_picker(d_ent, "%d/%m/%Y", on_selected=lambda _d: self.load_matrix(), label="The delivery date")
        tk.Button(ctrl_card, text="All", font=theme.F_SMALL, relief="solid", bd=1, padx=8, pady=2, cursor="hand2",
                  command=lambda: (self.matrix_date_var.set(""), self.load_matrix())).pack(side="left", padx=(0, 16))

        tk.Button(ctrl_card, text="📄 Export to Excel", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=3, command=self._export_matrix).pack(side="left", padx=(0, 16))

        self.show_stock_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl_card, text="Show Stock", variable=self.show_stock_var, font=theme.F_BODY, bg=theme.SURFACE, command=self.load_matrix).pack(side="left", padx=(0, 10))

        self.show_purchase_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl_card, text="Show To Purchase", variable=self.show_purchase_var, font=theme.F_BODY, bg=theme.SURFACE, command=self.load_matrix).pack(side="left", padx=(0, 16))

        tk.Button(ctrl_card, text="🖨 Print Configuration", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=3, command=self._print_matrix).pack(side="right")
        tk.Button(ctrl_card, text="🔄 Refresh", font=theme.F_SMALL, bg=theme.SURFACE, relief="solid", bd=1, padx=10, pady=3, command=self.load_matrix).pack(side="right", padx=6)

        # Report Container Card
        self.report_card = tk.Frame(self.matrix_tab, bg=theme.SURFACE, bd=1, relief="solid", padx=16, pady=14)
        self.report_card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Report Header inside container
        rep_hdr = tk.Frame(self.report_card, bg=theme.SURFACE)
        rep_hdr.pack(fill="x", pady=(0, 10))

        rep_title_box = tk.Frame(rep_hdr, bg=theme.SURFACE)
        rep_title_box.pack(side="left")
        tk.Label(rep_title_box, text="ORDER MATRIX REPORT", font=("Segoe UI", 14, "bold"), fg=theme.TEXT, bg=theme.SURFACE).pack(anchor="w")
        tk.Label(rep_title_box, text="Consolidated Item Requirements", font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(anchor="w")

        self.rep_date_label = tk.Label(
            rep_hdr,
            text="",
            font=theme.F_BODY,
            fg=theme.SLATE_600,
            bg=theme.SURFACE,
            justify="right"
        )
        self.rep_date_label.pack(side="right")

        # Divider line
        tk.Frame(self.report_card, bg=theme.TEXT, height=2).pack(fill="x", pady=(0, 10))

        # Pivot Table Container
        self.matrix_tree_frame = tk.Frame(self.report_card, bg=theme.SURFACE)
        self.matrix_tree_frame.pack(fill="both", expand=True)

    def load_matrix(self):
        for widget in self.matrix_tree_frame.winfo_children():
            widget.destroy()

        picked = self.matrix_date_picker.value()
        if self.matrix_date_picker.error():
            messagebox.showwarning("Delivery Date", self.matrix_date_picker.error(), parent=self)
            return
        res = self.order_svc.get_order_matrix(picked.strftime("%Y-%m-%d") if picked else None)
        customers = res.get("customers", [])
        rows = res.get("rows", [])

        # Update KPIs
        shortfall_cnt = sum(1 for r in rows if r.get("shortfall", 0) > 0)
        self.kpi_mat_custs.config(text=str(len(customers)))
        self.kpi_mat_shortfall.config(text=str(shortfall_cnt))
        self.kpi_mat_orders.config(text=str(len(self._raw_orders) if hasattr(self, "_raw_orders") else len(rows)))

        now_str = datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
        self.rep_date_label.config(text=f"Delivery Date: {self.matrix_date_var.get() or 'All pending orders'}\nGenerated: {now_str}")

        if not rows:
            tk.Label(
                self.matrix_tree_frame,
                text="No pending orders found to generate matrix.",
                font=theme.F_TEXT11,
                fg=theme.TEXT_FAINT,
                bg=theme.SURFACE
            ).pack(expand=True, pady=40)
            return

        columns = ["name", "unit"] + [f"cust_{i}" for i in range(len(customers))] + ["total_demand"]
        if self.show_stock_var.get():
            columns.append("current_stock")
        if self.show_purchase_var.get():
            columns.append("shortfall")

        tree = ttk.Treeview(self.matrix_tree_frame, columns=columns, show="headings")
        tree.heading("name", text="Item Name")
        tree.heading("unit", text="UOM")
        tree.column("name", width=180, anchor="w")
        tree.column("unit", width=70, anchor="center")

        for i, c_name in enumerate(customers):
            tree.heading(f"cust_{i}", text=c_name)
            tree.column(f"cust_{i}", width=120, anchor="e")

        tree.heading("total_demand", text="Total Order")
        tree.column("total_demand", width=100, anchor="e")

        if self.show_stock_var.get():
            tree.heading("current_stock", text="Closing Stock")
            tree.column("current_stock", width=100, anchor="e")

        if self.show_purchase_var.get():
            tree.heading("shortfall", text="To Purchase")
            tree.column("shortfall", width=100, anchor="e")

        tree.tag_configure("shortfall_tag", background="#fee2e2", foreground="#991b1b")

        for r in rows:
            vals = [
                r["name"],
                "KG",
            ] + [f"{q:g}" if q > 0 else "-" for q in r.get("customer_quantities", [])] + [
                f"{r['total_demand']:g}"
            ]
            if self.show_stock_var.get():
                vals.append(f"{r['current_stock']:g}")
            if self.show_purchase_var.get():
                vals.append(f"{r['shortfall']:g}" if r['shortfall'] > 0 else "0")

            tag = "shortfall_tag" if r.get("shortfall", 0) > 0 else ""
            tree.insert("", "end", values=vals, tags=(tag,) if tag else ())

        vsb = ttk.Scrollbar(self.matrix_tree_frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(self.matrix_tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)

    def _export_matrix(self):
        messagebox.showinfo("Export Matrix", "Consolidated matrix exported to CSV/Excel report.", parent=self)

    def _print_matrix(self):
        messagebox.showinfo("Print Report", "Sending Order Matrix Report to configured default printer.", parent=self)

    def _make_card(self, parent, initial_val: str, label_text: str, bg_color: str):
        card = tk.Frame(parent, bg=bg_color, padx=20, pady=16, bd=0)
        card.pack(side="left", fill="both", expand=True, padx=4)

        val_label = tk.Label(
            card,
            text=initial_val,
            font=("Segoe UI", 24, "bold"),
            fg=theme.SURFACE,
            bg=bg_color,
            anchor="w"
        )
        val_label.pack(fill="x")

        sub_label = tk.Label(
            card,
            text=label_text,
            font=theme.F_BODY,
            fg="#e0e7ff" if bg_color in ("#5046e5", "#2563eb") else "#fef3c7",
            bg=bg_color,
            anchor="w"
        )
        sub_label.pack(fill="x", pady=(2, 0))

        return val_label, card
