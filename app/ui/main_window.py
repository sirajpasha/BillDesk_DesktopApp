import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Optional, Dict, Any
from app.config.settings import settings

from app.ui.dashboard import DashboardFrame
from app.ui.billing import BillingFrame
from app.ui.history import BillHistoryFrame
from app.ui.masters_view import MastersView
from app.ui.orders_view import OrdersView
from app.ui.order_form_view import OrderFormView
from app.ui.inventory_view import InventoryView
from app.ui.procurement_view import ProcurementView
from app.ui.finance_view import FinanceView
from app.ui.admin_view import AdminView
from app.ui.database_settings import DatabaseSettingsFrame
from app.ui.consolidated_view import ConsolidatedReportFrame


class MainWindow:
    """Authentic BillDesk Native Desktop Main Window matching UI/UX screenshots."""

    # Menu-permission groups (values stored in role_permissions.menus). Admin roles bypass all checks.
    PERMISSION_GROUPS = {
        "masters": ("/items", "/customers", "/suppliers"),
        "finance": ("/finance", "/accounting", "/ledger"),
        "settings": ("/settings", "/users", "/admin"),
    }
    # Pages guarded by a group; every entry point (menu, F-keys, dashboard buttons) goes through show_page.
    PAGE_GROUPS = {
        "Item Master": "masters", "Customer Master": "masters", "Supplier Master": "masters",
        "Fixed Rates": "masters", "Master Data": "masters",
        "Finance": "finance", "Accounting Dashboard": "finance", "Trial Balance": "finance",
        "Profit & Loss": "finance", "Balance Sheet": "finance", "BRS": "finance",
        "Accounts Receivables": "finance", "Accounts Payables": "finance", "Handover & Settlement": "finance",
        "Administration": "settings", "User Management": "settings", "Company Settings": "settings",
        "System Audit Logs": "settings", "DB Connection": "settings",
    }

    def has_access(self, group: str) -> bool:
        """True when the signed-in user may use a permission group ('masters' | 'finance' | 'settings')."""
        permissions = self.auth.permissions_for(self.current_user)
        if "*" in permissions or any(r.lower() in ("admin", "super admin") for r in self.current_user.roles):
            return True
        return any(p in permissions for p in self.PERMISSION_GROUPS[group])

    def can_open(self, page: str) -> bool:
        group = self.PAGE_GROUPS.get(page)
        return group is None or self.has_access(group)

    def __init__(self, root, db, auth, billing, current_user, on_logout=None):
        self.root = root
        self.db = db
        self.auth = auth
        self.billing = billing
        self.current_user = current_user
        self.on_logout = on_logout
        self.frames = {}
        self.active_page = None
        self.company_name = self._get_company_name()

        root.title(f"BillDesk — {self.company_name}")
        root.geometry("1400x880")
        root.minsize(1120, 700)
        root.configure(bg="#f8fafc")

        # Set taskbar and window icon if available
        import os
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                self._icon_img = tk.PhotoImage(file=icon_path)
                root.iconphoto(False, self._icon_img)
            except Exception:
                pass

        self._configure_style()
        self._build_shell()
        self._bind_global_shortcuts()
        self._update_clock()

    def _get_company_name(self) -> str:
        try:
            comp = self.db.collection("companies").find_one()
            if comp and comp.get("name"):
                return comp["name"].upper()
        except Exception:
            pass
        return settings.default_company_name.upper()

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#f8fafc")
        style.configure("White.TFrame", background="#ffffff")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), background="#f8fafc", foreground="#0f172a")
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), background="#f8fafc", foreground="#1e293b")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 7))

    def _build_shell(self):
        shell = tk.Frame(self.root, bg="#f8fafc")
        shell.pack(fill="both", expand=True)

        # ---------------- 1. TOP HEADER BAR ----------------
        # Matches screenshots: Left has BillDesk logo + subtitle; Center has Company Name
        header_bar = tk.Frame(shell, bg="#ffffff", height=56, bd=0)
        header_bar.pack(fill="x", side="top")
        header_bar.pack_propagate(False)

        # Left Branding
        brand_frame = tk.Frame(header_bar, bg="#ffffff", padx=16)
        brand_frame.pack(side="left", fill="y", pady=6)

        # Small BillDesk emblem
        logo_canvas = tk.Canvas(brand_frame, width=32, height=32, bg="#ffffff", highlightthickness=0)
        logo_canvas.pack(side="left", padx=(0, 8))
        logo_canvas.create_oval(2, 2, 30, 30, fill="#0ea5e9", outline="#0284c7")
        logo_canvas.create_text(16, 16, text="B", font=("Segoe UI", 13, "bold"), fill="#ffffff")

        brand_text_box = tk.Frame(brand_frame, bg="#ffffff")
        brand_text_box.pack(side="left")
        tk.Label(
            brand_text_box,
            text="BillDesk",
            font=("Segoe UI", 13, "bold"),
            fg="#0f172a",
            bg="#ffffff"
        ).pack(anchor="w")
        tk.Label(
            brand_text_box,
            text="Your Digital Partner for Freshness & Quality",
            font=("Segoe UI", 8, "italic"),
            fg="#64748b",
            bg="#ffffff"
        ).pack(anchor="w")

        # Center Company Name (Bold Uppercase)
        center_box = tk.Frame(header_bar, bg="#ffffff")
        center_box.pack(side="left", expand=True, fill="both")
        tk.Label(
            center_box,
            text=self.company_name,
            font=("Segoe UI", 16, "bold"),
            fg="#1e293b",
            bg="#ffffff"
        ).pack(expand=True)

        # Right empty spacer to keep center aligned
        tk.Frame(header_bar, bg="#ffffff", width=200).pack(side="right")

        # ---------------- 2. HORIZONTAL MENUBAR (BELOW HEADER) ----------------
        # Matches 02-dashboard.png: File  Masters  Reports  Accounts  Settings
        menu_strip = tk.Frame(shell, bg="#ffffff", height=34, bd=0)
        menu_strip.pack(fill="x", side="top")

        # Subtle bottom line below menubar
        tk.Frame(shell, bg="#e2e8f0", height=1).pack(fill="x", side="top")

        # Horizontal Menu Buttons with Popups
        menu_container = tk.Frame(menu_strip, bg="#ffffff", padx=12)
        menu_container.pack(side="left", fill="y")

        self.menus_config = self._build_menu_structure()
        self._active_popup = None

        for menu_name, items in self.menus_config.items():
            btn = tk.Menubutton(
                menu_container,
                text=menu_name,
                font=("Segoe UI", 9, "bold"),
                bg="#ffffff",
                fg="#334155",
                activebackground="#f1f5f9",
                activeforeground="#0f172a",
                relief="flat",
                bd=0,
                padx=12,
                pady=6,
                cursor="hand2"
            )
            btn.pack(side="left")

            # Attach drop-down menu
            menu = tk.Menu(btn, tearoff=0, bg="#ffffff", fg="#0f172a", activebackground="#4f46e5", activeforeground="#ffffff", font=("Segoe UI", 9), bd=1, relief="solid")
            for item in items:
                if item == "---":
                    menu.add_separator()
                else:
                    label, target_page, shortcut = item
                    accel_text = f"    {shortcut}" if shortcut else ""
                    menu.add_command(
                        label=f"{label}{accel_text}",
                        command=lambda t=target_page: self.show_page(t)
                    )
            btn["menu"] = menu

        # ---------------- 3. MAIN WORKSPACE / CONTENT CONTAINER ----------------
        self.content = tk.Frame(shell, bg="#f8fafc")
        self.content.pack(fill="both", expand=True)

        # ---------------- 4. BOTTOM ACCENT STRIP & STATUS BAR ----------------
        # Matches 02-dashboard.png: Purple top accent strip + bottom shortcut guide
        bottom_box = tk.Frame(shell, bg="#ffffff")
        bottom_box.pack(side="bottom", fill="x")

        # Top purple accent border
        tk.Frame(bottom_box, bg="#5b54d6", height=3).pack(fill="x")

        status_bar = tk.Frame(bottom_box, bg="#ffffff", padx=14, pady=5)
        status_bar.pack(fill="x")

        self.shortcut_label = tk.Label(
            status_bar,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg="#475569",
            bg="#ffffff",
            anchor="w"
        )
        self.shortcut_label.pack(side="left")

        # Right status (User & real-time clock)
        self.clock_label = tk.Label(
            status_bar,
            text="",
            font=("Segoe UI", 8),
            fg="#475569",
            bg="#ffffff",
            anchor="e"
        )
        self.clock_label.pack(side="right")

        # Instantiate all module frames
        self._init_all_views()

        # Show Dashboard initially
        initial_page = "Dashboard" if "Dashboard" in self.frames else next(iter(self.frames), None)
        if initial_page:
            self.show_page(initial_page)

    def _build_menu_structure(self) -> Dict[str, list]:
        """Construct menu tree matching 03-menu-masters.png and User Guide."""
        menus = {}

        # 1. File Menu
        menus["File"] = [
            ("New Bill", "New Bill", "F2"),
            ("New Customer Order", "New Order", "Ctrl+N"),
            ("Ordering System", "Orders", "Ctrl+O"),
            ("Purchase system", "Procurement", "Ctrl+P"),
            ("---", "", ""),
            ("Logout", "Logout", "F12"),
            ("Exit", "Exit", "Alt+F4"),
        ]

        # 2. Masters Menu
        if self.has_access("masters"):
            menus["Masters"] = [
                ("Item Master", "Item Master", "F10"),
                ("Customer Master", "Customer Master", "F11"),
                ("Supplier Master", "Supplier Master", "F5"),
                ("Waste Management", "Waste Management", ""),
            ]

        # 3. Reports Menu
        menus["Reports"] = [
            ("Bills History", "Bill History", "F6"),
            ("Bills Consolidated Report", "Consolidated Billing", ""),
            ("Order Consolidation", "Order Matrix", ""),
            ("Fixed Rates Report", "Fixed Rates", ""),
            ("Profit & Loss", "Profit & Loss", ""),
            ("Balance Sheet", "Balance Sheet", ""),
            ("Dashboard", "Dashboard", "F1"),
        ]
        menus["Reports"] = [m for m in menus["Reports"] if m[1] == "" or self.can_open(m[1])]

        # 4. Accounts Menu
        if self.has_access("finance"):
            menus["Accounts"] = [
                ("Accounting Dashboard", "Finance", "Ctrl+D"),
                ("Trial Balance", "Trial Balance", ""),
                ("Profit & Loss", "Profit & Loss", ""),
                ("Balance Sheet", "Balance Sheet", ""),
                ("BRS", "BRS", ""),
                ("Handover & Settlement", "Handover & Settlement", ""),
                ("Accounts Receivables", "Accounts Receivables", ""),
                ("Accounts Payables", "Accounts Payables", ""),
            ]

        # 5. Settings Menu
        if self.has_access("settings"):
            menus["Settings"] = [
                ("User Management", "User Management", "F6"),
                ("Company Settings", "Company Settings", "F11"),
                ("Database Settings", "DB Connection", ""),
                ("System Audit Logs", "System Audit Logs", ""),
            ]

        return menus

    def _init_all_views(self):
        """Pre-mount all views for instantaneous sub-millisecond tab switching."""
        content = self.content

        # 1. Dashboard
        self.frames["Dashboard"] = DashboardFrame(
            content, self.db, self.billing, self.current_user, on_navigate=self.show_page
        )

        # 2. POS Billing Terminal
        self.frames["New Bill"] = BillingFrame(
            content, self.db, self.billing, self.current_user
        )

        # 3. Bill History
        self.frames["Bill History"] = BillHistoryFrame(
            content, self.db, self.billing, current_user=self.current_user, on_navigate=self.show_page
        )

        # 4. Master Data (Unified MastersView with tabs for Items, Customers, Suppliers, Fixed Pricing)
        self.masters_view = MastersView(content, self.db)
        self.frames["Master Data"] = self.masters_view
        self.frames["Item Master"] = self.masters_view
        self.frames["Customer Master"] = self.masters_view
        self.frames["Supplier Master"] = self.masters_view
        self.frames["Fixed Rates"] = self.masters_view

        # 5. Orders & Matrix
        self.order_form_view = OrderFormView(content, self.db, current_user=self.current_user, on_navigate=self.show_page)
        self.frames["New Order"] = self.order_form_view
        self.frames["Create New Order"] = self.order_form_view

        self.orders_view = OrdersView(content, self.db, current_user=self.current_user, on_navigate=self.show_page, order_form_view=self.order_form_view)
        self.frames["Orders"] = self.orders_view
        self.frames["Order Matrix"] = self.orders_view

        # 6. Inventory & Waste
        self.inventory_view = InventoryView(content, self.db, current_user=self.current_user)
        self.frames["Inventory"] = self.inventory_view
        self.frames["Waste Management"] = self.inventory_view

        # 7. Procurement
        self.procurement_view = ProcurementView(content, self.db, current_user=self.current_user)
        self.frames["Procurement"] = self.procurement_view

        # 8. Finance & Accounts
        self.finance_view = FinanceView(content, self.db, current_user=self.current_user)
        self.frames["Finance"] = self.finance_view
        self.frames["Accounting Dashboard"] = self.finance_view
        self.frames["Trial Balance"] = self.finance_view
        self.frames["Profit & Loss"] = self.finance_view
        self.frames["Balance Sheet"] = self.finance_view
        self.frames["BRS"] = self.finance_view
        self.frames["Accounts Receivables"] = self.finance_view
        self.frames["Accounts Payables"] = self.finance_view

        # 9. Administration
        self.admin_view = AdminView(content, self.db, current_user=self.current_user)
        self.frames["Administration"] = self.admin_view
        self.frames["Handover & Settlement"] = self.admin_view
        self.frames["User Management"] = self.admin_view
        self.frames["Company Settings"] = self.admin_view
        self.frames["System Audit Logs"] = self.admin_view

        # 10. Consolidated Billing Report
        self.consolidated_view = ConsolidatedReportFrame(
            content, self.db, self.billing, current_user=self.current_user, on_navigate=self.show_page
        )
        self.frames["Consolidated Billing"] = self.consolidated_view
        self.frames["Bills Consolidated Report"] = self.consolidated_view

        # 11. Database Settings
        self.frames["DB Connection"] = DatabaseSettingsFrame(
            content, self.db, billing=self.billing
        )

    def _bind_global_shortcuts(self):
        """Bind keyboard accelerators matching the User Guide."""
        self.root.bind_all("<F1>", lambda _e: self.show_page("Dashboard"))
        self.root.bind_all("<F2>", lambda _e: self._on_f2())
        self.root.bind_all("<F3>", lambda _e: self._on_f3())
        self.root.bind_all("<F4>", lambda _e: self.show_page("Customer Master"))
        self.root.bind_all("<F5>", lambda _e: self._on_f5())
        self.root.bind_all("<F6>", lambda _e: self._on_f6())
        self.root.bind_all("<F10>", lambda _e: self.show_page("Item Master"))
        self.root.bind_all("<F11>", lambda _e: self.show_page("Customer Master"))
        self.root.bind_all("<F12>", lambda _e: self._logout())

        self.root.bind_all("<Control-o>", lambda _e: self.show_page("Orders"))
        self.root.bind_all("<Control-p>", lambda _e: self.show_page("Procurement"))
        self.root.bind_all("<Control-d>", lambda _e: self.show_page("Finance"))

    def _on_f2(self):
        # If in billing, let billing handle F2 (Save Bill); otherwise switch to New Bill
        if self.active_page == "New Bill" and hasattr(self.frames["New Bill"], "_on_f2_save"):
            self.frames["New Bill"]._on_f2_save()
        else:
            self.show_page("New Bill")

    def _on_f3(self):
        if self.active_page == "New Bill" and hasattr(self.frames["New Bill"], "_on_f3_save_print"):
            self.frames["New Bill"]._on_f3_save_print()
        else:
            self.show_page("Item Master")

    def _on_f5(self):
        if self.active_page == "New Bill" and hasattr(self.frames["New Bill"], "_open_customer_search"):
            self.frames["New Bill"]._open_customer_search()
        elif self.active_page == "Dashboard":
            self.show_page("Supplier Master")
        else:
            # Refresh active page
            if self.active_page and self.active_page in self.frames:
                frame = self.frames[self.active_page]
                if hasattr(frame, "refresh"):
                    frame.refresh()

    def _on_f6(self):
        if self.active_page == "New Bill" and hasattr(self.frames["New Bill"], "park_bill"):
            self.frames["New Bill"].park_bill()
        else:
            self.show_page("Bill History")

    def _logout(self):
        if messagebox.askyesno("Sign Out", "Are you sure you want to sign out?", parent=self.root):
            if self.on_logout:
                self.on_logout()
            else:
                self.root.destroy()

    def _update_clock(self):
        now_str = datetime.now().strftime("%d/%m/%Y, %H:%M")
        self.clock_label.config(text=f"User: {self.current_user.username}    {now_str}")
        self.root.after(1000, self._update_clock)

    def show_page(self, name: str):
        """Navigate to target page and update contextual shortcut legend."""
        if name == "Logout":
            self._logout()
            return
        if name == "Exit":
            self.root.destroy()
            return

        target_frame = self.frames.get(name)
        if not target_frame:
            # Search case-insensitive
            for k in self.frames:
                if name.lower() == k.lower() or name.lower() in k.lower():
                    target_frame = self.frames[k]
                    name = k
                    break

        if not target_frame:
            return

        if not self.can_open(name):
            messagebox.showwarning(
                "Access Denied",
                f"Your role ({', '.join(self.current_user.roles) or 'none'}) does not have access to {name}.",
                parent=self.root,
            )
            return

        # Hide other frames
        for frame in set(self.frames.values()):
            frame.pack_forget()

        # Handle sub-tabs inside parent views
        if name == "Item Master" and hasattr(self.masters_view, "notebook"):
            self.masters_view.notebook.select(self.masters_view.items_tab)
        elif name == "Customer Master" and hasattr(self.masters_view, "notebook"):
            self.masters_view.notebook.select(self.masters_view.customers_tab)
        elif name == "Supplier Master" and hasattr(self.masters_view, "notebook"):
            self.masters_view.notebook.select(self.masters_view.suppliers_tab)
        elif name == "Fixed Rates" and hasattr(self.masters_view, "notebook"):
            self.masters_view.notebook.select(self.masters_view.pricing_tab)
        elif name == "Order Matrix" and hasattr(self.orders_view, "notebook"):
            self.orders_view.notebook.select(self.orders_view.matrix_tab)
        elif name == "Waste Management" and hasattr(self.inventory_view, "notebook"):
            self.inventory_view.notebook.select(self.inventory_view.waste_tab)
        elif hasattr(self, "finance_view") and hasattr(self.finance_view, "notebook"):
            if name in ("Finance", "Accounting Dashboard"):
                self.finance_view.notebook.select(self.finance_view.home_tab)
            elif name in ("Accounts Receivables", "AR"):
                self.finance_view.notebook.select(self.finance_view.ar_tab)
            elif name in ("Accounts Payables", "AP"):
                self.finance_view.notebook.select(self.finance_view.ap_tab)
            elif name in ("BRS", "Banking & BRS"):
                self.finance_view.notebook.select(self.finance_view.bank_tab)
            elif name in ("General Ledger", "Trial Balance", "Profit & Loss", "Balance Sheet"):
                self.finance_view.notebook.select(self.finance_view.gl_tab)
                if name == "Trial Balance":
                    self.root.after(100, self.finance_view._view_trial_balance)
                elif name == "Profit & Loss":
                    self.root.after(100, self.finance_view._view_pl)
                elif name == "Balance Sheet":
                    self.root.after(100, self.finance_view._view_balance_sheet)

        self.active_page = name
        target_frame.pack(fill="both", expand=True)

        if hasattr(target_frame, "refresh"):
            try:
                target_frame.refresh()
            except Exception:
                pass

        # Update contextual bottom function keys legend matching screenshots
        if name == "Dashboard":
            shortcuts_text = "F1: Refresh | F2: New Bill | F3: Items | F4: Customers | F5: Suppliers | F6: Bills History | F12: Logout"
        elif name == "New Bill":
            shortcuts_text = "F2: Save Bill | F3: Save & Print | F5: Customer Search | F6: Park Bill | F7: View Parked Bills | F8: Smart Loader | F12: Logout"
        elif "Master" in name or name in ("Customers", "Items", "Suppliers"):
            shortcuts_text = "F1: Search | F2: Add Record | F5: Refresh | F12: Back"
        elif name == "Bill History":
            shortcuts_text = "F1: Search | F2: New Bill | F5: Refresh | F12: Back"
        else:
            shortcuts_text = "F1: Dashboard | F2: New Bill | F5: Refresh | F12: Logout"

        self.shortcut_label.config(text=shortcuts_text)

    def show(self):
        self.root.deiconify()
