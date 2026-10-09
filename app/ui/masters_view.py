import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timezone, timedelta
from app.config.settings import settings
from app.services.master_service import MasterService
from app.utils.currency import format_inr, format_balance
from app.utils.formatters import format_date

class MastersView(tk.Frame):
    """
    Unified Master Data View matching screenshots:
    - 09-customers.png (Customer Master)
    - 10-items.png (Item Master)
    - 11-suppliers.png (Supplier Master)
    - 16-fixed-rates.png (Customer Fixed Pricing)
    - 18-add-customer.png (Add New Customer Modal)
    - 19-add-item.png (Add New Item Modal)
    """
    def __init__(self, parent, db, **kwargs):
        super().__init__(parent, bg="#f8fafc", **kwargs)
        self.db = db
        self.master_svc = MasterService(db)

        # Style notebook
        style = ttk.Style()
        style.configure("Masters.TNotebook", background="#f8fafc")
        style.configure("Masters.TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=[16, 6])

        self.notebook = ttk.Notebook(self, style="Masters.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(12, 16))

        # Tab 1: Item Master (Matches 10-items.png)
        self.items_tab = tk.Frame(self.notebook, bg="#f8fafc")
        self.notebook.add(self.items_tab, text="Item Master")
        self._build_items_tab()

        # Tab 2: Customer Master (Matches 09-customers.png)
        self.customers_tab = tk.Frame(self.notebook, bg="#f8fafc")
        self.notebook.add(self.customers_tab, text="Customer Master")
        self._build_customers_tab()

        # Tab 3: Supplier Master (Matches 11-suppliers.png)
        self.suppliers_tab = tk.Frame(self.notebook, bg="#f8fafc")
        self.notebook.add(self.suppliers_tab, text="Supplier Master")
        self._build_suppliers_tab()

        # Tab 4: Fixed Pricing
        self.pricing_tab = tk.Frame(self.notebook, bg="#f8fafc")
        self.notebook.add(self.pricing_tab, text="Fixed Pricing")
        self._build_pricing_tab()

        self.refresh()

    def refresh(self):
        self.load_items()
        self.load_customers()
        self.load_suppliers()
        self.load_fixed_prices()

    # =========================================================================
    # 1. ITEM MASTER (Matches 10-items.png & 19-add-item.png)
    # =========================================================================
    def _build_items_tab(self):
        # Header strip
        top_bar = tk.Frame(self.items_tab, bg="#f8fafc")
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg="#f8fafc")
        title_box.pack(side="left")
        tk.Label(title_box, text="Item Master", font=("Segoe UI", 18, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w")
        tk.Label(title_box, text="Manage your product catalog with pricing, categories, and inventory details", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(anchor="w")

        btn_box = tk.Frame(top_bar, bg="#f8fafc")
        btn_box.pack(side="right")

        tk.Button(
            btn_box,
            text="📦 Manual Stock",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
            relief="solid",
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._on_manual_stock
        ).pack(side="left", padx=4)

        tk.Button(
            btn_box,
            text="⚙ Fixed Pricing",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#334155",
            relief="solid",
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=lambda: self.notebook.select(self.pricing_tab)
        ).pack(side="left", padx=4)

        tk.Button(
            btn_box,
            text="+ Add Item",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            activebackground="#4338ca",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._add_item_dialog
        ).pack(side="left", padx=4)

        # 3 KPI Cards: Total Items (Purple), Active Items (Green), Categories (Orange)
        kpi_row = tk.Frame(self.items_tab, bg="#f8fafc")
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        self.kpi_item_total, _ = self._make_card(kpi_row, "0", "Total Items", "#5046e5")
        self.kpi_item_active, _ = self._make_card(kpi_row, "0", "Active Items", "#059669")
        self.kpi_item_cats, _ = self._make_card(kpi_row, "0", "Categories", "#d97706")

        # Table Container
        card = tk.Frame(self.items_tab, bg="#ffffff", bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Search Bar
        search_bar = tk.Frame(card, bg="#ffffff", padx=16, pady=10)
        search_bar.pack(fill="x")

        self.item_search_var = tk.StringVar()
        s_ent = tk.Entry(
            search_bar,
            textvariable=self.item_search_var,
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            width=40
        )
        s_ent.pack(side="left", ipady=4)
        s_ent.insert(0, "")
        self.item_search_var.trace_add("write", lambda *_: self._filter_items())

        tk.Label(search_bar, text=" (Search: Item name, alias, category...)", font=("Segoe UI", 8), fg="#94a3b8", bg="#ffffff").pack(side="left", padx=6)

        sub_strip = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        sub_strip.pack(fill="x")
        self.item_count_label = tk.Label(sub_strip, text="Showing 0 items", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc")
        self.item_count_label.pack(side="left")

        # Table
        tbl_frame = tk.Frame(card, bg="#ffffff", padx=12, pady=6)
        tbl_frame.pack(fill="both", expand=True)

        cols = ("alias", "name", "category", "unit", "rate", "stock", "status")
        self.items_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        self.items_tree.heading("alias", text="Alias")
        self.items_tree.heading("name", text="Item Name")
        self.items_tree.heading("category", text="Category")
        self.items_tree.heading("unit", text="Unit")
        self.items_tree.heading("rate", text="Rate")
        self.items_tree.heading("stock", text="Live Stock")
        self.items_tree.heading("status", text="Status")

        self.items_tree.column("alias", width=90, anchor="center")
        self.items_tree.column("name", width=220, anchor="w")
        self.items_tree.column("category", width=120, anchor="center")
        self.items_tree.column("unit", width=80, anchor="center")
        self.items_tree.column("rate", width=100, anchor="e")
        self.items_tree.column("stock", width=100, anchor="e")
        self.items_tree.column("status", width=90, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.items_tree.yview)
        self.items_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.items_tree.pack(side="left", fill="both", expand=True)
        self.items_tree.bind("<Double-1>", lambda _e: self._on_edit_item())

        # Action bottom strip
        act_bar = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        act_bar.pack(fill="x", side="bottom")
        tk.Button(act_bar, text="✏ Edit Selected", font=("Segoe UI", 8, "bold"), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self._on_edit_item).pack(side="left", padx=4)
        tk.Button(act_bar, text="🗑 Delete Item", font=("Segoe UI", 8), bg="#fee2e2", fg="#991b1b", relief="solid", bd=1, padx=10, pady=3, command=self._delete_item).pack(side="left", padx=4)
        tk.Button(act_bar, text="🔄 Refresh", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self.load_items).pack(side="right", padx=4)

    def _filter_items(self):
        q = self.item_search_var.get().strip().lower()
        for i in self.items_tree.get_children():
            self.items_tree.delete(i)

        filtered = []
        for itm in self._raw_items:
            alias = str(itm.get("item_alias", itm.get("item_id", ""))).lower()
            name = str(itm.get("name", "")).lower()
            cat = str(itm.get("category", "")).lower()
            if q and (q not in alias and q not in name and q not in cat):
                continue
            filtered.append(itm)

        for itm in filtered:
            rate_val = itm.get("standard_rate") or itm.get("rate") or 0.0
            rate_str = format_inr(rate_val) if rate_val else "not set"
            stock_val = f"{itm.get('stock', 0.0):g}"
            self.items_tree.insert(
                "",
                "end",
                iid=itm.get("item_id"),
                values=(
                    itm.get("item_alias", itm.get("item_id", "")),
                    itm.get("name", ""),
                    itm.get("category", "Vegetables"),
                    itm.get("unit", "kg"),
                    rate_str,
                    stock_val,
                    "ACTIVE"
                )
            )
        self.item_count_label.config(text=f"Showing 1 to {len(filtered)} of {len(self._raw_items)} items")

    def load_items(self):
        self._raw_items = self.master_svc.search_items(limit=300)
        categories = set(i.get("category", "Vegetables") for i in self._raw_items if i.get("category"))
        self.kpi_item_total.config(text=str(len(self._raw_items)))
        self.kpi_item_active.config(text=str(len(self._raw_items)))
        self.kpi_item_cats.config(text=str(len(categories)))
        self._filter_items()

    def _on_manual_stock(self):
        messagebox.showinfo("Manual Stock", "Stock count adjustments can be executed via the Inventory & Stock module.", parent=self)

    def _add_item_dialog(self):
        self._item_modal(title="Add New Item", is_new=True)

    def _on_edit_item(self):
        sel = self.items_tree.selection()
        if not sel:
            messagebox.showinfo("Select Item", "Please select an item to edit.", parent=self)
            return
        item_id = sel[0]
        itm = next((i for i in self._raw_items if i.get("item_id") == item_id), None)
        if itm:
            self._item_modal(title="Edit Item", is_new=False, item_data=itm)

    def _item_modal(self, title: str, is_new: bool, item_data: dict | None = None):
        """Matches 19-add-item.png."""
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("460x520")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg="#ffffff")

        # Header with purple gradient feel
        hdr = tk.Frame(dlg, bg="#4f46e5", padx=20, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, font=("Segoe UI", 14, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")
        tk.Label(hdr, text="Manage product catalog with pricing and inventory details", font=("Segoe UI", 8), fg="#c7d2fe", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=14)
        body.pack(fill="both", expand=True)

        item = item_data or {}

        # Section 1: Basic Information
        tk.Label(body, text="📦 Basic Information", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w", pady=(0, 6))

        tk.Label(body, text="Alias (Fast Code) *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        alias_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        alias_ent.pack(fill="x", pady=(2, 8))
        alias_ent.insert(0, str(item.get("item_alias", item.get("item_id", ""))))

        tk.Label(body, text="Item Name *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        name_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        name_ent.pack(fill="x", pady=(2, 12))
        name_ent.insert(0, str(item.get("name", "")))

        # Section 2: Classification
        tk.Label(body, text="🏷 Classification", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w", pady=(0, 6))

        tk.Label(body, text="Category", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        cat_cb = ttk.Combobox(body, values=["Vegetables", "Fruit", "Greens", "Herbs", "Exotic", "Other"], state="readonly")
        cat_cb.pack(fill="x", pady=(2, 8))
        cat_cb.set(item.get("category", "Vegetables"))

        tk.Label(body, text="Unit of Measure", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        unit_cb = ttk.Combobox(body, values=["kg", "bunch", "box", "no", "crate"], state="readonly")
        unit_cb.pack(fill="x", pady=(2, 12))
        unit_cb.set(item.get("unit", "kg"))

        # Section 3: Pricing & Stock
        tk.Label(body, text="Standard Rate (₹)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        rate_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        rate_ent.pack(fill="x", pady=(2, 8))
        rate_ent.insert(0, str(item.get("standard_rate", item.get("rate", 0.0))))

        tk.Label(body, text="Initial Stock Quantity", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        stock_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        stock_ent.pack(fill="x", pady=(2, 14))
        stock_ent.insert(0, str(item.get("stock", 0.0)))

        def on_save():
            alias = alias_ent.get().strip()
            name = name_ent.get().strip()
            cat = cat_cb.get().strip()
            unit = unit_cb.get().strip()
            if not alias or not name:
                messagebox.showwarning("Validation Error", "Alias and Item Name are required.", parent=dlg)
                return
            try:
                rate_f = float(rate_ent.get().strip() or 0.0)
                stock_f = float(stock_ent.get().strip() or 0.0)
                item_id = item.get("item_id") if not is_new else f"ITEM_{alias}"
                data = {
                    "item_id": item_id,
                    "item_alias": alias,
                    "name": name,
                    "category": cat,
                    "unit": unit,
                    "standard_rate": rate_f,
                    "rate": rate_f,
                    "stock": stock_f,
                }
                self.master_svc.save_item(data, is_new=is_new)
                self.load_items()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        # Footer Buttons
        ftr = tk.Frame(dlg, bg="#ffffff", padx=20, pady=10)
        ftr.pack(fill="x", side="bottom")

        tk.Button(
            ftr,
            text="Save Item",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=on_save
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            ftr,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#475569",
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=dlg.destroy
        ).pack(side="right")

    def _delete_item(self):
        sel = self.items_tree.selection()
        if not sel:
            messagebox.showinfo("Select Item", "Please select an item to delete.", parent=self)
            return
        item_id = sel[0]
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete item {item_id}?"):
            self.master_svc.delete_item(item_id)
            self.load_items()

    # =========================================================================
    # 2. CUSTOMER MASTER (Matches 09-customers.png & 18-add-customer.png)
    # =========================================================================
    def _build_customers_tab(self):
        # Header strip
        top_bar = tk.Frame(self.customers_tab, bg="#f8fafc")
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg="#f8fafc")
        title_box.pack(side="left")
        tk.Label(title_box, text="Customer Master", font=("Segoe UI", 18, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w")
        tk.Label(title_box, text="Manage your customer database with comprehensive contact and billing information", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Add Customer",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            activebackground="#4338ca",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._add_customer_dialog
        ).pack(side="right")

        # 3 KPI Cards: Total Customers (Purple), Active Customers (Green), Inactive (Orange)
        kpi_row = tk.Frame(self.customers_tab, bg="#f8fafc")
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        self.kpi_cust_total, _ = self._make_card(kpi_row, "0", "Total Customers", "#5046e5")
        self.kpi_cust_active, _ = self._make_card(kpi_row, "0", "Active Customers", "#059669")
        self.kpi_cust_inactive, _ = self._make_card(kpi_row, "0", "Inactive", "#d97706")

        # Table Container
        card = tk.Frame(self.customers_tab, bg="#ffffff", bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Search Bar
        search_bar = tk.Frame(card, bg="#ffffff", padx=16, pady=10)
        search_bar.pack(fill="x")

        self.cust_search_var = tk.StringVar()
        c_ent = tk.Entry(
            search_bar,
            textvariable=self.cust_search_var,
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            width=40
        )
        c_ent.pack(side="left", ipady=4)
        self.cust_search_var.trace_add("write", lambda *_: self._filter_customers())

        tk.Label(search_bar, text=" (Search customer master...)", font=("Segoe UI", 8), fg="#94a3b8", bg="#ffffff").pack(side="left", padx=6)

        sub_strip = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        sub_strip.pack(fill="x")
        self.cust_count_label = tk.Label(sub_strip, text="Total: 0 customers", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc")
        self.cust_count_label.pack(side="left")

        # Table
        tbl_frame = tk.Frame(card, bg="#ffffff", padx=12, pady=6)
        tbl_frame.pack(fill="both", expand=True)

        cols = ("company", "dc_company", "name", "phone", "address", "balance", "status")
        self.cust_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        self.cust_tree.heading("company", text="Invoice Company")
        self.cust_tree.heading("dc_company", text="Bill To (DC)")
        self.cust_tree.heading("name", text="Customer Name")
        self.cust_tree.heading("phone", text="Contact Number")
        self.cust_tree.heading("address", text="Address")
        self.cust_tree.heading("balance", text="Balance")
        self.cust_tree.heading("status", text="Status")

        self.cust_tree.column("company", width=140, anchor="w")
        self.cust_tree.column("dc_company", width=130, anchor="w")
        self.cust_tree.column("name", width=200, anchor="w")
        self.cust_tree.column("phone", width=120, anchor="center")
        self.cust_tree.column("address", width=180, anchor="w")
        self.cust_tree.column("balance", width=110, anchor="e")
        self.cust_tree.column("status", width=90, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.cust_tree.pack(side="left", fill="both", expand=True)
        self.cust_tree.bind("<Double-1>", lambda _e: self._on_edit_customer())

        # Action bottom strip
        act_bar = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        act_bar.pack(fill="x", side="bottom")
        tk.Button(act_bar, text="✏ Edit Customer", font=("Segoe UI", 8, "bold"), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self._on_edit_customer).pack(side="left", padx=4)
        tk.Button(act_bar, text="📒 Statement", font=("Segoe UI", 8, "bold"), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self._on_customer_statement).pack(side="left", padx=4)
        tk.Button(act_bar, text="🔄 Refresh", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self.load_customers).pack(side="right", padx=4)

    def _filter_customers(self):
        q = self.cust_search_var.get().strip().lower()
        for i in self.cust_tree.get_children():
            self.cust_tree.delete(i)

        filtered = []
        for c in self._raw_customers:
            name = str(c.get("name", "")).lower()
            cid = str(c.get("cust_id", "")).lower()
            bname = str(c.get("bill_to_name", "")).lower()
            phone = str(c.get("phone", "") or c.get("contact_person_phone", "")).lower()
            if q and (q not in name and q not in cid and q not in phone and q not in bname):
                continue
            filtered.append(c)

        comp_map = getattr(self, "_companies_map", {})
        for c in filtered:
            comp_name = comp_map.get(c.get("company_id"), c.get("company_name", settings.default_company_name))
            dc_comp_name = c.get("bill_to_name") or comp_map.get(c.get("dc_company_id"), "-")
            phone = c.get("contact_person_phone") or c.get("phone") or c.get("bill_to_phone") or "-"
            addr = c.get("address") or c.get("bill_to_address") or "-"

            self.cust_tree.insert(
                "",
                "end",
                iid=c.get("cust_id"),
                values=(
                    comp_name,
                    dc_comp_name,
                    c.get("name", ""),
                    phone,
                    addr,
                    format_balance(c.get("current_balance", 0.0)),
                    "ACTIVE"
                )
            )
        self.cust_count_label.config(text=f"Total: {len(filtered)} customers")

    def load_customers(self):
        try:
            comps = self.master_svc.get_all_companies()
            self._companies_map = {c["company_id"]: c.get("name", "") for c in comps}
        except Exception:
            self._companies_map = {}
        self._raw_customers = self.master_svc.search_customers(limit=300)
        self.kpi_cust_total.config(text=str(len(self._raw_customers)))
        self.kpi_cust_active.config(text=str(len(self._raw_customers)))
        self.kpi_cust_inactive.config(text="0")
        self._filter_customers()

    def _add_customer_dialog(self):
        self._customer_modal("Add New Customer", is_new=True)

    def _on_customer_statement(self):
        sel = self.cust_tree.selection()
        if not sel:
            messagebox.showinfo("Select Customer", "Please select a customer to open the statement.", parent=self)
            return
        from app.ui.statement_view import StatementWindow
        cust = next((c for c in self._raw_customers if c.get("cust_id") == sel[0]), {})
        StatementWindow(self, self.db, sel[0], cust.get("name", ""))

    def _on_edit_customer(self):
        sel = self.cust_tree.selection()
        if not sel:
            messagebox.showinfo("Select Customer", "Please select a customer to edit.", parent=self)
            return
        cid = sel[0]
        cust = next((c for c in self._raw_customers if c.get("cust_id") == cid), None)
        if cust:
            self._customer_modal("Edit Customer", is_new=False, cust_data=cust)

    def _customer_modal(self, title: str, is_new: bool, cust_data: dict | None = None):
        """Matches 18-add-customer.png with Ship To / Bill To 2-column layout."""
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("740x670")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg="#ffffff")

        # Header with purple gradient feel
        hdr = tk.Frame(dlg, bg="#4f46e5", padx=20, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, font=("Segoe UI", 14, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")
        tk.Label(hdr, text="Manage customer database with comprehensive contact and billing information", font=("Segoe UI", 8), fg="#c7d2fe", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=12)
        body.pack(fill="both", expand=True)

        cust = cust_data or {}

        # Company Selection Row (Billing Company & DC Company)
        comp_row = tk.Frame(body, bg="#ffffff")
        comp_row.pack(fill="x", pady=(0, 8))

        all_companies = self.master_svc.get_all_companies() or []
        company_options = [f"{c.get('company_id')}: {c.get('name')}" for c in all_companies]
        if not company_options:
            company_options = [f"Company0001: {settings.default_company_name}"]

        # Left: Billing Company
        col_bcomp = tk.Frame(comp_row, bg="#ffffff")
        col_bcomp.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(col_bcomp, text="Billing Company *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bcomp_cbo = ttk.Combobox(col_bcomp, values=company_options, state="readonly", font=("Segoe UI", 9))
        bcomp_cbo.pack(fill="x", pady=(2, 4))
        curr_bcomp_id = cust.get("company_id", "Company0001")
        bcomp_idx = 0
        for idx, opt in enumerate(company_options):
            if opt.startswith(f"{curr_bcomp_id}:"):
                bcomp_idx = idx
                break
        bcomp_cbo.current(bcomp_idx)

        # Right: DC Company
        col_dcomp = tk.Frame(comp_row, bg="#ffffff")
        col_dcomp.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(col_dcomp, text="DC Company (Challan Header)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        dc_options = ["None (Same as Billing Company)"] + company_options
        dcomp_cbo = ttk.Combobox(col_dcomp, values=dc_options, state="readonly", font=("Segoe UI", 9))
        dcomp_cbo.pack(fill="x", pady=(2, 4))
        curr_dcomp_id = cust.get("dc_company_id", "")
        dcomp_idx = 0
        for idx, opt in enumerate(dc_options):
            if curr_dcomp_id and opt.startswith(f"{curr_dcomp_id}:"):
                dcomp_idx = idx
                break
        dcomp_cbo.current(dcomp_idx)

        # 2 Columns Frame
        two_col = tk.Frame(body, bg="#ffffff")
        two_col.pack(fill="x", pady=(0, 10))

        # Left Column: Ship To
        col_left = tk.Frame(two_col, bg="#ffffff")
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(col_left, text="🚚 Ship To", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w", pady=(0, 4))

        tk.Label(col_left, text="Customer Name *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        name_ent = tk.Entry(col_left, font=("Segoe UI", 9), relief="solid", bd=1)
        name_ent.pack(fill="x", pady=(2, 6))
        name_ent.insert(0, str(cust.get("name", "")))

        tk.Label(col_left, text="Contact Person", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        person_ent = tk.Entry(col_left, font=("Segoe UI", 9), relief="solid", bd=1)
        person_ent.pack(fill="x", pady=(2, 6))
        person_ent.insert(0, str(cust.get("contact_person") or cust.get("contact_person_name", "")))

        tk.Label(col_left, text="Address", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        addr_ent = tk.Entry(col_left, font=("Segoe UI", 9), relief="solid", bd=1)
        addr_ent.pack(fill="x", pady=(2, 6))
        addr_ent.insert(0, str(cust.get("address", "")))

        tk.Label(col_left, text="Phone / WhatsApp", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        phone_ent = tk.Entry(col_left, font=("Segoe UI", 9), relief="solid", bd=1)
        phone_ent.pack(fill="x", pady=(2, 6))
        phone_ent.insert(0, str(cust.get("phone") or cust.get("contact_person_phone", "")))

        tk.Label(col_left, text="Email", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        email_ent = tk.Entry(col_left, font=("Segoe UI", 9), relief="solid", bd=1)
        email_ent.pack(fill="x", pady=(2, 6))
        email_ent.insert(0, str(cust.get("email") or cust.get("contact_person_email", "")))

        # Right Column: Bill To with "Same as Ship To" button
        col_right = tk.Frame(two_col, bg="#ffffff")
        col_right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        bill_hdr = tk.Frame(col_right, bg="#ffffff")
        bill_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(bill_hdr, text="📄 Bill To", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(side="left")

        def copy_ship_to_bill():
            bill_name_ent.delete(0, "end")
            bill_name_ent.insert(0, name_ent.get())
            bill_phone_ent.delete(0, "end")
            bill_phone_ent.insert(0, phone_ent.get())
            bill_addr_ent.delete(0, "end")
            bill_addr_ent.insert(0, addr_ent.get())
            bill_email_ent.delete(0, "end")
            bill_email_ent.insert(0, email_ent.get())

        tk.Button(
            bill_hdr,
            text="📄 Same as Ship To",
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            cursor="hand2",
            command=copy_ship_to_bill
        ).pack(side="right")

        tk.Label(col_right, text="DC Company Name (bill_to_name) *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bill_name_ent = tk.Entry(col_right, font=("Segoe UI", 9), relief="solid", bd=1)
        bill_name_ent.pack(fill="x", pady=(2, 6))
        bill_name_ent.insert(0, str(cust.get("bill_to_name") or cust.get("name", "")))

        def _on_dc_comp_selected(event=None):
            val = dcomp_cbo.get()
            if val and ":" in val:
                cname = val.split(":", 1)[1].strip()
                if not bill_name_ent.get().strip() or bill_name_ent.get().strip() == name_ent.get().strip():
                    bill_name_ent.delete(0, "end")
                    bill_name_ent.insert(0, cname)

        dcomp_cbo.bind("<<ComboboxSelected>>", _on_dc_comp_selected)

        tk.Label(col_right, text="Bill To Phone", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bill_phone_ent = tk.Entry(col_right, font=("Segoe UI", 9), relief="solid", bd=1)
        bill_phone_ent.pack(fill="x", pady=(2, 6))
        bill_phone_ent.insert(0, str(cust.get("bill_to_phone") or cust.get("phone") or cust.get("contact_person_phone", "")))

        tk.Label(col_right, text="Bill To Address", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bill_addr_ent = tk.Entry(col_right, font=("Segoe UI", 9), relief="solid", bd=1)
        bill_addr_ent.pack(fill="x", pady=(2, 6))
        bill_addr_ent.insert(0, str(cust.get("bill_to_address") or cust.get("address", "")))

        tk.Label(col_right, text="Bill To Email", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bill_email_ent = tk.Entry(col_right, font=("Segoe UI", 9), relief="solid", bd=1)
        bill_email_ent.pack(fill="x", pady=(2, 6))
        bill_email_ent.insert(0, str(cust.get("bill_to_email") or cust.get("email", "")))

        # Section 3: Additional Information
        tk.Label(body, text="Additional Information", font=("Segoe UI", 10, "bold"), fg="#1e293b", bg="#ffffff").pack(anchor="w", pady=(6, 4))

        extra_row = tk.Frame(body, bg="#ffffff")
        extra_row.pack(fill="x")

        # Credit Limit
        col_c1 = tk.Frame(extra_row, bg="#ffffff")
        col_c1.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(col_c1, text="Credit Limit (₹)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        credit_ent = tk.Entry(col_c1, font=("Segoe UI", 9), relief="solid", bd=1)
        credit_ent.pack(fill="x", pady=(2, 6))
        credit_ent.insert(0, str(cust.get("credit_limit", 0.0)))

        # GST Number
        col_c2 = tk.Frame(extra_row, bg="#ffffff")
        col_c2.pack(side="left", fill="x", expand=True, padx=6)
        tk.Label(col_c2, text="GSTIN / Tax ID", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        gst_ent = tk.Entry(col_c2, font=("Segoe UI", 9), relief="solid", bd=1)
        gst_ent.pack(fill="x", pady=(2, 6))
        gst_ent.insert(0, str(cust.get("gst_number", "")))

        # Opening Balance
        col_c3 = tk.Frame(extra_row, bg="#ffffff")
        col_c3.pack(side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(col_c3, text="Opening Balance (₹)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        bal_ent = tk.Entry(col_c3, font=("Segoe UI", 9), relief="solid", bd=1)
        bal_ent.pack(fill="x", pady=(2, 6))
        bal_ent.insert(0, str(cust.get("current_balance", 0.0)))

        def on_save():
            name = name_ent.get().strip()
            if not name:
                messagebox.showwarning("Validation Error", "Customer Name is required.", parent=dlg)
                return
            try:
                cid = cust.get("cust_id") if not is_new else f"CUST_{int(datetime.now().timestamp())}"

                b_val = bcomp_cbo.get()
                sel_bcomp_id = b_val.split(":")[0].strip() if ":" in b_val else "Company0001"
                sel_bcomp_name = b_val.split(":", 1)[1].strip() if ":" in b_val else settings.default_company_name

                d_val = dcomp_cbo.get()
                sel_dcomp_id = d_val.split(":")[0].strip() if (":" in d_val and not d_val.startswith("None")) else None

                bill_name = bill_name_ent.get().strip() or name

                data = dict(cust)
                data.update({
                    "cust_id": cid,
                    "name": name,
                    "company_id": sel_bcomp_id,
                    "company_name": sel_bcomp_name,
                    "dc_company_id": sel_dcomp_id,
                    "contact_person": person_ent.get().strip(),
                    "contact_person_name": person_ent.get().strip(),
                    "address": addr_ent.get().strip(),
                    "phone": phone_ent.get().strip(),
                    "contact_person_phone": phone_ent.get().strip(),
                    "email": email_ent.get().strip(),
                    "bill_to_name": bill_name,
                    "bill_to_phone": bill_phone_ent.get().strip() or phone_ent.get().strip(),
                    "bill_to_address": bill_addr_ent.get().strip() or addr_ent.get().strip(),
                    "bill_to_email": bill_email_ent.get().strip() or email_ent.get().strip(),
                    "credit_limit": float(credit_ent.get().strip() or 0.0),
                    "gst_number": gst_ent.get().strip(),
                    "current_balance": float(bal_ent.get().strip() or 0.0),
                    "status": "active"
                })
                self.master_svc.save_customer(data, is_new=is_new)
                self.load_customers()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        # Footer Buttons
        ftr = tk.Frame(dlg, bg="#ffffff", padx=20, pady=10)
        ftr.pack(fill="x", side="bottom")

        tk.Button(
            ftr,
            text="Save Customer",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=on_save
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            ftr,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#475569",
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=dlg.destroy
        ).pack(side="right")

    # =========================================================================
    # 3. SUPPLIER MASTER (Matches 11-suppliers.png)
    # =========================================================================
    def _build_suppliers_tab(self):
        # Header strip
        top_bar = tk.Frame(self.suppliers_tab, bg="#f8fafc")
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg="#f8fafc")
        title_box.pack(side="left")
        tk.Label(title_box, text="Supplier Master", font=("Segoe UI", 18, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w")
        tk.Label(title_box, text="Manage your vendor database with contact information and business details", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Add Supplier",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._add_supplier_dialog
        ).pack(side="right")

        # 3 KPI Cards: Total Suppliers (Purple), Active Suppliers (Green), GST Registered (Orange)
        kpi_row = tk.Frame(self.suppliers_tab, bg="#f8fafc")
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        self.kpi_supp_total, _ = self._make_card(kpi_row, "0", "Total Suppliers", "#5046e5")
        self.kpi_supp_active, _ = self._make_card(kpi_row, "0", "Active Suppliers", "#059669")
        self.kpi_supp_gst, _ = self._make_card(kpi_row, "0", "GST Registered", "#d97706")

        # Table Container
        card = tk.Frame(self.suppliers_tab, bg="#ffffff", bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Search Bar
        search_bar = tk.Frame(card, bg="#ffffff", padx=16, pady=10)
        search_bar.pack(fill="x")

        self.supp_search_var = tk.StringVar()
        sp_ent = tk.Entry(
            search_bar,
            textvariable=self.supp_search_var,
            font=("Segoe UI", 9),
            relief="solid",
            bd=1,
            width=40
        )
        sp_ent.pack(side="left", ipady=4)
        self.supp_search_var.trace_add("write", lambda *_: self._filter_suppliers())

        tk.Label(search_bar, text=" (Search supplier master...)", font=("Segoe UI", 8), fg="#94a3b8", bg="#ffffff").pack(side="left", padx=6)

        sub_strip = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        sub_strip.pack(fill="x")
        self.supp_count_label = tk.Label(sub_strip, text="Total: 0 suppliers", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc")
        self.supp_count_label.pack(side="left")

        # Table
        tbl_frame = tk.Frame(card, bg="#ffffff", padx=12, pady=6)
        tbl_frame.pack(fill="both", expand=True)

        cols = ("supplier_id", "company", "contact", "address", "gst", "status")
        self.supp_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        self.supp_tree.heading("supplier_id", text="Supplier ID")
        self.supp_tree.heading("company", text="Company Name")
        self.supp_tree.heading("contact", text="Contact")
        self.supp_tree.heading("address", text="Address")
        self.supp_tree.heading("gst", text="GST Number")
        self.supp_tree.heading("status", text="Status")

        self.supp_tree.column("supplier_id", width=110, anchor="center")
        self.supp_tree.column("company", width=220, anchor="w")
        self.supp_tree.column("contact", width=140, anchor="center")
        self.supp_tree.column("address", width=200, anchor="w")
        self.supp_tree.column("gst", width=150, anchor="center")
        self.supp_tree.column("status", width=90, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.supp_tree.yview)
        self.supp_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.supp_tree.pack(side="left", fill="both", expand=True)
        self.supp_tree.bind("<Double-1>", lambda _e: self._on_edit_supplier())

        # Action bottom strip
        act_bar = tk.Frame(card, bg="#f8fafc", padx=16, pady=6)
        act_bar.pack(fill="x", side="bottom")
        tk.Button(act_bar, text="✏ Edit Supplier", font=("Segoe UI", 8, "bold"), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self._on_edit_supplier).pack(side="left", padx=4)
        tk.Button(act_bar, text="🔄 Refresh", font=("Segoe UI", 8), bg="#ffffff", relief="solid", bd=1, padx=10, pady=3, command=self.load_suppliers).pack(side="right", padx=4)

    def _filter_suppliers(self):
        q = self.supp_search_var.get().strip().lower()
        for i in self.supp_tree.get_children():
            self.supp_tree.delete(i)

        filtered = []
        for s in self._raw_suppliers:
            name = str(s.get("name", "")).lower()
            sid = str(s.get("supplier_id", "")).lower()
            if q and (q not in name and q not in sid):
                continue
            filtered.append(s)

        for s in filtered:
            self.supp_tree.insert(
                "",
                "end",
                iid=s.get("supplier_id"),
                values=(
                    s.get("supplier_id", ""),
                    s.get("name", ""),
                    s.get("phone", "-"),
                    s.get("address", "-"),
                    s.get("gst_number") or "-",
                    "ACTIVE"
                )
            )
        self.supp_count_label.config(text=f"Total: {len(filtered)} suppliers")

    def load_suppliers(self):
        self._raw_suppliers = self.master_svc.search_suppliers(limit=300)
        gst_cnt = sum(1 for s in self._raw_suppliers if s.get("gst_number"))
        self.kpi_supp_total.config(text=str(len(self._raw_suppliers)))
        self.kpi_supp_active.config(text=str(len(self._raw_suppliers)))
        self.kpi_supp_gst.config(text=str(gst_cnt))
        self._filter_suppliers()

    def _add_supplier_dialog(self):
        self._supplier_modal("Add New Supplier", is_new=True)

    def _on_edit_supplier(self):
        sel = self.supp_tree.selection()
        if not sel:
            messagebox.showinfo("Select Supplier", "Please select a supplier to edit.", parent=self)
            return
        sid = sel[0]
        supp = next((s for s in self._raw_suppliers if s.get("supplier_id") == sid), None)
        if supp:
            self._supplier_modal("Edit Supplier", is_new=False, supp_data=supp)

    def _supplier_modal(self, title: str, is_new: bool, supp_data: dict | None = None):
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("480x520")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg="#ffffff")

        hdr = tk.Frame(dlg, bg="#4f46e5", padx=20, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, font=("Segoe UI", 14, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")
        tk.Label(hdr, text="Manage vendor database with contact information and tax details", font=("Segoe UI", 8), fg="#c7d2fe", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=14)
        body.pack(fill="both", expand=True)

        supp = supp_data or {}

        tk.Label(body, text="Supplier ID *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        sid_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        sid_ent.pack(fill="x", pady=(2, 8))
        sid_ent.insert(0, str(supp.get("supplier_id", "")))
        if not is_new:
            sid_ent.config(state="disabled")

        tk.Label(body, text="Company / Vendor Name *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        name_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        name_ent.pack(fill="x", pady=(2, 8))
        name_ent.insert(0, str(supp.get("name", "")))

        tk.Label(body, text="Contact Phone", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        phone_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        phone_ent.pack(fill="x", pady=(2, 8))
        phone_ent.insert(0, str(supp.get("phone", "")))

        tk.Label(body, text="Address / Market Location", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        addr_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        addr_ent.pack(fill="x", pady=(2, 8))
        addr_ent.insert(0, str(supp.get("address", "")))

        tk.Label(body, text="GSTIN (Tax ID)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        gst_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        gst_ent.pack(fill="x", pady=(2, 8))
        gst_ent.insert(0, str(supp.get("gst_number", "")))

        def on_save():
            s_id = sid_ent.get().strip() or f"SUP_{int(datetime.now().timestamp())}"
            name = name_ent.get().strip()
            if not name:
                messagebox.showwarning("Validation Error", "Supplier Name is required.", parent=dlg)
                return
            try:
                data = {
                    "supplier_id": s_id,
                    "name": name,
                    "phone": phone_ent.get().strip(),
                    "address": addr_ent.get().strip(),
                    "gst_number": gst_ent.get().strip(),
                    "status": "active"
                }
                self.master_svc.save_supplier(data, is_new=is_new)
                self.load_suppliers()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg="#ffffff", padx=20, pady=10)
        ftr.pack(fill="x", side="bottom")

        tk.Button(
            ftr,
            text="Save Supplier",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=on_save
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            ftr,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#475569",
            relief="solid",
            bd=1,
            padx=14,
            pady=5,
            command=dlg.destroy
        ).pack(side="right")

    # =========================================================================
    # 4. FIXED PRICING TAB (Matches 16-fixed-rates.png)
    # =========================================================================
    def _build_pricing_tab(self):
        top_bar = tk.Frame(self.pricing_tab, bg="#f8fafc")
        top_bar.pack(fill="x", padx=12, pady=(14, 10))

        title_box = tk.Frame(top_bar, bg="#f8fafc")
        title_box.pack(side="left")
        tk.Label(title_box, text="Customer Fixed Pricing", font=("Segoe UI", 18, "bold"), fg="#0f172a", bg="#f8fafc").pack(anchor="w")
        tk.Label(title_box, text="Manage customer-specific negotiated contract produce rates and validity", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(anchor="w")

        tk.Button(
            top_bar,
            text="+ Add Contract Price",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._add_fixed_price_dialog
        ).pack(side="right")

        card = tk.Frame(self.pricing_tab, bg="#ffffff", bd=1, relief="solid")
        card.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        tbl_frame = tk.Frame(card, bg="#ffffff", padx=12, pady=10)
        tbl_frame.pack(fill="both", expand=True)

        cols = ("customer_id", "item_id", "rate", "start_date", "end_date", "is_active")
        self.pricing_tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        self.pricing_tree.heading("customer_id", text="Customer ID")
        self.pricing_tree.heading("item_id", text="Item ID")
        self.pricing_tree.heading("rate", text="Contract Rate")
        self.pricing_tree.heading("start_date", text="Start Date")
        self.pricing_tree.heading("end_date", text="End Date")
        self.pricing_tree.heading("is_active", text="Status")

        self.pricing_tree.column("customer_id", width=140, anchor="center")
        self.pricing_tree.column("item_id", width=140, anchor="center")
        self.pricing_tree.column("rate", width=120, anchor="e")
        self.pricing_tree.column("start_date", width=130, anchor="center")
        self.pricing_tree.column("end_date", width=130, anchor="center")
        self.pricing_tree.column("is_active", width=90, anchor="center")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self.pricing_tree.yview)
        self.pricing_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.pricing_tree.pack(side="left", fill="both", expand=True)

    def load_fixed_prices(self):
        prices = self.master_svc.get_fixed_prices()
        for i in self.pricing_tree.get_children():
            self.pricing_tree.delete(i)

        for p in prices:
            s_dt = format_date(p.get("start_date"))
            e_dt = format_date(p.get("end_date"))
            self.pricing_tree.insert(
                "",
                "end",
                values=(
                    p.get("customer_id", ""),
                    p.get("item_id", ""),
                    format_inr(p.get("rate", 0.0)),
                    s_dt,
                    e_dt,
                    "ACTIVE"
                )
            )

    def _add_fixed_price_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Fixed Contract Price")
        dlg.geometry("420x360")
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg="#ffffff")

        hdr = tk.Frame(dlg, bg="#4f46e5", padx=16, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Add Fixed Contract Price", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#4f46e5").pack(anchor="w")

        body = tk.Frame(dlg, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Customer ID *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        cust_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        cust_ent.pack(fill="x", pady=(2, 6))

        tk.Label(body, text="Item ID *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        item_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        item_ent.pack(fill="x", pady=(2, 6))

        tk.Label(body, text="Contract Rate (₹) *", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        rate_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        rate_ent.pack(fill="x", pady=(2, 6))

        now = datetime.now()
        tk.Label(body, text="Start Date (YYYY-MM-DD)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        sdate_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        sdate_ent.pack(fill="x", pady=(2, 6))
        sdate_ent.insert(0, now.strftime("%Y-%m-%d"))

        tk.Label(body, text="End Date (YYYY-MM-DD)", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#ffffff").pack(anchor="w")
        edate_ent = tk.Entry(body, font=("Segoe UI", 9), relief="solid", bd=1)
        edate_ent.pack(fill="x", pady=(2, 10))
        edate_ent.insert(0, (now + timedelta(days=30)).strftime("%Y-%m-%d"))

        def on_save():
            try:
                c_id = cust_ent.get().strip()
                i_id = item_ent.get().strip()
                r_val = float(rate_ent.get().strip())
                s_dt = datetime.strptime(sdate_ent.get().strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                e_dt = datetime.strptime(edate_ent.get().strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                self.master_svc.save_fixed_price(c_id, i_id, r_val, s_dt, e_dt)
                self.load_fixed_prices()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        ftr = tk.Frame(dlg, bg="#ffffff", padx=16, pady=10)
        ftr.pack(fill="x", side="bottom")
        tk.Button(ftr, text="Save Price", font=("Segoe UI", 9, "bold"), bg="#4f46e5", fg="#ffffff", relief="flat", bd=0, padx=14, pady=5, command=on_save).pack(side="right", padx=(6, 0))
        tk.Button(ftr, text="Cancel", font=("Segoe UI", 9), bg="#f1f5f9", fg="#475569", relief="solid", bd=1, padx=12, pady=4, command=dlg.destroy).pack(side="right")

    # =========================================================================
    # Helpers
    # =========================================================================
    def _make_card(self, parent, initial_val: str, label_text: str, bg_color: str):
        card = tk.Frame(parent, bg=bg_color, padx=20, pady=16, bd=0)
        card.pack(side="left", fill="both", expand=True, padx=4)

        val_label = tk.Label(
            card,
            text=initial_val,
            font=("Segoe UI", 24, "bold"),
            fg="#ffffff",
            bg=bg_color,
            anchor="w"
        )
        val_label.pack(fill="x")

        sub_label = tk.Label(
            card,
            text=label_text,
            font=("Segoe UI", 9),
            fg="#e0e7ff" if bg_color == "#5046e5" else "#dcfce7" if bg_color == "#059669" else "#fef3c7",
            bg=bg_color,
            anchor="w"
        )
        sub_label.pack(fill="x", pady=(2, 0))

        return val_label, card
