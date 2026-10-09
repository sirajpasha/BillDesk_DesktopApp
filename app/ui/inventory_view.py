import tkinter as tk
from tkinter import ttk, messagebox
from app.ui.components.data_table import DataTable
from app.services.inventory_service import InventoryService
from app.utils.formatters import format_date

class InventoryView(ttk.Frame):
    """Inventory Management: Live Stock, Adjustments, Waste Logs, and Crates."""
    def __init__(self, parent, db, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.current_user = current_user
        self.inv_svc = InventoryService(db)

        from app.ui import theme
        theme.page_header(self, "Inventory & Mandi Operations", "Stock on hand, movements, spoilage and crates").pack(fill="x", padx=28, pady=(20, 10))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=28, pady=(0, 16))

        # Tab 1: Live Stock
        self.stock_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.stock_tab, text="Live Stock Overview")
        self._build_stock_tab()

        # Tab 2: Stock Transactions
        self.txns_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.txns_tab, text="Stock Movement History")
        self._build_txns_tab()

        # Tab 3: Waste & Spoilage
        self.waste_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.waste_tab, text="Produce Waste Logs")
        self._build_waste_tab()

        # Tab 4: Crate Transactions
        self.crates_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.crates_tab, text="Crate Balances & Movement")
        self._build_crates_tab()

        self.refresh()

    def refresh(self):
        self.load_stock()
        self.load_txns()
        self.load_waste()
        self.load_crates()

    # ---------------- LIVE STOCK TAB ----------------
    def _build_stock_tab(self):
        bar = ttk.Frame(self.stock_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Manual Adjustment (+/-)", command=self._adjustment_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Record Waste / Spoilage", command=self._waste_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh Stock", command=self.load_stock).pack(side="left", padx=4)

        cols = [
            ("item_id", "Item ID", 110),
            ("item_alias", "Alias", 110),
            ("name", "Produce Name", 240),
            ("unit", "Unit", 80),
            ("category", "Category", 130),
            ("stock", "Current Live Stock", 130),
            ("status", "Status", 90),
        ]
        self.stock_table = DataTable(self.stock_tab, columns=cols, empty_text="No stock recorded yet. Stock rises when goods are received (Procurement > Goods Receipt Notes) or adjusted here.")
        self.stock_table.pack(fill="both", expand=True)

    def load_stock(self):
        items = self.inv_svc.get_stock_overview()
        self.stock_table.set_data(items)

    def _adjustment_dialog(self):
        sel = self.stock_table.get_selected()
        item_id_init = sel.get("item_id", "") if sel else ""

        dlg = tk.Toplevel(self)
        dlg.title("Manual Stock Count Adjustment")
        dlg.geometry("400x260")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Item ID:").grid(row=0, column=0, padx=12, pady=10, sticky="w")
        id_ent = ttk.Entry(dlg, width=24)
        id_ent.insert(0, item_id_init)
        id_ent.grid(row=0, column=1, padx=12, pady=10)

        ttk.Label(dlg, text="Adjustment Qty (+ / -):").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        qty_ent = ttk.Entry(dlg, width=24)
        qty_ent.grid(row=1, column=1, padx=12, pady=10)

        ttk.Label(dlg, text="Reason (Audit):").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        reason_ent = ttk.Entry(dlg, width=24)
        reason_ent.grid(row=2, column=1, padx=12, pady=10)

        def on_adjust():
            try:
                i_id = id_ent.get().strip()
                delta = float(qty_ent.get().strip())
                reason = reason_ent.get().strip()
                if not i_id or not reason:
                    messagebox.showwarning("Input Required", "Item ID and Reason are required", parent=dlg)
                    return
                res = self.inv_svc.adjust_stock(i_id, delta, reason, user_id=self.current_user.username)
                messagebox.showinfo("Success", f"Stock adjusted!\nNew Live Stock: {res['new_stock']:.2f}")
                dlg.destroy()
                self.load_stock()
                self.load_txns()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        btn_box = ttk.Frame(dlg)
        btn_box.grid(row=3, column=0, columnspan=2, pady=16)
        ttk.Button(btn_box, text="Commit Adjustment", command=on_adjust).pack(side="left", padx=8)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)

    def _waste_dialog(self):
        sel = self.stock_table.get_selected()
        item_id_init = sel.get("item_id", "") if sel else ""

        dlg = tk.Toplevel(self)
        dlg.title("Record Produce Spoilage / Waste")
        dlg.geometry("400x280")
        dlg.transient(self)
        dlg.grab_set()

        ttk.Label(dlg, text="Item ID:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        id_ent = ttk.Entry(dlg, width=24)
        id_ent.insert(0, item_id_init)
        id_ent.grid(row=0, column=1, padx=12, pady=8)

        ttk.Label(dlg, text="Waste Qty:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        qty_ent = ttk.Entry(dlg, width=24)
        qty_ent.grid(row=1, column=1, padx=12, pady=8)

        ttk.Label(dlg, text="Estimated Cost Rate:").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        rate_ent = ttk.Entry(dlg, width=24)
        rate_ent.insert(0, "0.0")
        rate_ent.grid(row=2, column=1, padx=12, pady=8)

        ttk.Label(dlg, text="Reason (Rotten/Crushed):").grid(row=3, column=0, padx=12, pady=8, sticky="w")
        reason_ent = ttk.Entry(dlg, width=24)
        reason_ent.grid(row=3, column=1, padx=12, pady=8)

        def on_waste():
            try:
                i_id = id_ent.get().strip()
                qty = float(qty_ent.get().strip())
                rate = float(rate_ent.get().strip())
                reason = reason_ent.get().strip()
                if not i_id or not reason:
                    messagebox.showwarning("Input Required", "Item ID and Reason are required", parent=dlg)
                    return
                self.inv_svc.record_waste(i_id, qty, rate, reason, user_id=self.current_user.username)
                messagebox.showinfo("Success", "Waste recorded and stock decremented successfully.")
                dlg.destroy()
                self.load_stock()
                self.load_waste()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        btn_box = ttk.Frame(dlg)
        btn_box.grid(row=4, column=0, columnspan=2, pady=14)
        ttk.Button(btn_box, text="Record Waste", command=on_waste).pack(side="left", padx=8)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)

    # ---------------- TRANSACTIONS TAB ----------------
    def _build_txns_tab(self):
        bar = ttk.Frame(self.txns_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Refresh Movements", command=self.load_txns).pack(side="left", padx=4)

        cols = [
            ("transaction_id", "Txn ID", 130),
            ("date", "Date & Time", 150),
            ("item_name", "Produce Name", 180),
            ("type", "Type (Sale/Purchase/Adj/Waste)", 140),
            ("qty", "Qty Movement", 110),
            ("reference_id", "Reference Doc", 150),
            ("notes", "Notes", 200),
        ]
        self.txns_table = DataTable(self.txns_tab, columns=cols, empty_text="No stock movements yet. Every sale, return, goods receipt and adjustment is listed here.")
        self.txns_table.pack(fill="both", expand=True)

    def load_txns(self):
        txns = self.inv_svc.get_stock_transactions(limit=100)
        formatted = []
        for t in txns:
            d = dict(t)
            d["date"] = format_date(d.get("date"))
            formatted.append(d)
        self.txns_table.set_data(formatted)

    # ---------------- WASTE LOGS TAB ----------------
    def _build_waste_tab(self):
        bar = ttk.Frame(self.waste_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Refresh Waste Logs", command=self.load_waste).pack(side="left", padx=4)

        cols = [
            ("waste_id", "Waste ID", 130),
            ("date", "Date", 120),
            ("item_name", "Produce Name", 180),
            ("qty", "Spoiled Qty", 100),
            ("rate", "Cost Rate (₹)", 110),
            ("amount", "Financial Loss (₹)", 140),
            ("reason", "Reason", 220),
        ]
        self.waste_table = DataTable(self.waste_tab, columns=cols, empty_text="No spoilage logged. Record waste here so it reaches your profit and loss.")
        self.waste_table.pack(fill="both", expand=True)

    def load_waste(self):
        logs = self.inv_svc.get_waste_logs(limit=100)
        formatted = []
        for w in logs:
            d = dict(w)
            d["date"] = format_date(d.get("date"))
            formatted.append(d)
        self.waste_table.set_data(formatted)

    # ---------------- CRATES TAB ----------------
    def _build_crates_tab(self):
        bar = ttk.Frame(self.crates_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Refresh Crates", command=self.load_crates).pack(side="left", padx=4)

        cols = [
            ("txn_id", "Crate Txn ID", 130),
            ("date", "Date", 120),
            ("party_id", "Party ID", 130),
            ("party_type", "Party Type", 110),
            ("issued_qty", "Crates Issued", 110),
            ("returned_qty", "Crates Returned", 110),
            ("reference_id", "Ref Doc", 150),
        ]
        self.crates_table = DataTable(self.crates_tab, columns=cols, empty_text="No crate balances yet. Crates issued and returned on bills appear here.")
        self.crates_table.pack(fill="both", expand=True)

    def load_crates(self):
        txns = self.inv_svc.get_crate_transactions(limit=100)
        formatted = []
        for c in txns:
            d = dict(c)
            d["date"] = format_date(d.get("date"))
            formatted.append(d)
        self.crates_table.set_data(formatted)
