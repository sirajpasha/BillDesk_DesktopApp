import tkinter as tk
from app.utils import validation as V
from tkinter import ttk, messagebox
from app.ui.components.data_table import DataTable
from app.services.procurement_service import ProcurementService
from app.utils.currency import format_inr
from app.utils.formatters import format_date

class ProcurementView(ttk.Frame):
    """Procurement & Vendor Workflow: PO, GRN, and Purchase Bills with TDS."""
    def __init__(self, parent, db, current_user, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.current_user = current_user
        self.proc_svc = ProcurementService(db)

        from app.ui import theme
        theme.page_header(self, "Procurement & Vendor Management", "Vendor bills, purchase orders, goods received and returns").pack(fill="x", padx=28, pady=(20, 10))

        self.notebook = notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=28, pady=(0, 16))

        # Tab 1: Purchase Bills
        self.bills_tab = ttk.Frame(notebook)
        notebook.add(self.bills_tab, text="Vendor Purchase Bills")
        self._build_bills_tab()

        # Tab 2: Purchase Orders
        self.po_tab = ttk.Frame(notebook)
        notebook.add(self.po_tab, text="Purchase Orders (PO)")
        self._build_po_tab()

        # Tab 3: GRN
        self.grn_tab = ttk.Frame(notebook)
        notebook.add(self.grn_tab, text="Goods Receipt Notes (GRN)")
        self._build_grn_tab()

        # Tab 4: Returns to suppliers (debit notes)
        self.returns_tab = ttk.Frame(notebook)
        notebook.add(self.returns_tab, text="Returns to Suppliers")
        self._build_returns_tab()

        self.refresh()

    def refresh(self):
        self.load_bills()
        self.load_pos()
        self.load_grns()
        self.load_returns()

    # ---------------- PURCHASE BILLS TAB ----------------
    def _build_bills_tab(self):
        bar = ttk.Frame(self.bills_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="+ Enter Vendor Bill", command=self._add_vendor_bill_dialog).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh Bills", command=self.load_bills).pack(side="left", padx=4)
        ttk.Button(bar, text="↩ Return Goods to Supplier", command=self._return_selected_bill).pack(side="left", padx=4)

        cols = [
            ("purchase_id", "Purchase ID", 140),
            ("bill_date", "Date", 110),
            ("supplier_name", "Supplier", 200),
            ("supplier_bill_no", "Vendor Inv #", 130),
            ("total_amount", "Subtotal (₹)", 120),
            ("tds_amount", "TDS Deducted (₹)", 130),
            ("payable_amount", "Net Payable (₹)", 130),
            ("balance_due", "Balance Due (₹)", 130),
            ("status", "Status", 90),
        ]
        self.bills_table = DataTable(self.bills_tab, columns=cols, empty_text="No vendor bills yet. Use + Enter Vendor Bill when a supplier invoice arrives.")
        self.bills_table.pack(fill="both", expand=True)

    def load_bills(self):
        bills = self.proc_svc.get_purchase_bills(limit=100)
        formatted = []
        for b in bills:
            d = dict(b)
            d["bill_date"] = format_date(d.get("bill_date"))
            d["total_amount"] = format_inr(d.get("total_amount", 0.0), symbol=False)
            d["tds_amount"] = format_inr(d.get("tds_amount", 0.0), symbol=False)
            d["payable_amount"] = format_inr(d.get("payable_amount", 0.0), symbol=False)
            d["balance_due"] = format_inr(d.get("balance_due", 0.0), symbol=False)
            formatted.append(d)
        self.bills_table.set_data(formatted)

    def _add_vendor_bill_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Enter Vendor Purchase Bill")
        dlg.geometry("450x360")
        dlg.transient(self)
        dlg.grab_set()

        entries = {}
        fields = [
            ("Supplier ID *", "supplier_id", ""),
            ("Vendor Invoice No *", "supplier_bill_no", ""),
            ("Produce Item ID *", "item_id", ""),
            ("Produce Name *", "name", ""),
            ("Quantity Received *", "qty", ""),
            ("Purchase Rate *", "rate", ""),
        ]

        for idx, (label, key, val) in enumerate(fields):
            ttk.Label(dlg, text=label).grid(row=idx, column=0, padx=12, pady=6, sticky="w")
            ent = ttk.Entry(dlg, width=24)
            ent.insert(0, val)
            ent.grid(row=idx, column=1, padx=12, pady=6, sticky="ew")
            entries[key] = ent

        def on_save():
            try:
                s_id = entries["supplier_id"].get().strip()
                b_no = entries["supplier_bill_no"].get().strip()
                i_id = entries["item_id"].get().strip()
                name = entries["name"].get().strip()
                qty = V.number(entries["qty"].get(), "Quantity received", greater_than=0, maximum=10_000_000)
                rate = V.number(entries["rate"].get(), "Purchase rate", greater_than=0, maximum=1_000_000)
                if not s_id or not b_no or not i_id:
                    messagebox.showwarning("Required", "Supplier, Invoice #, and Item ID are required", parent=dlg)
                    return
                items = [{"item_id": i_id, "name": name, "qty": qty, "unit": "kg", "rate": rate, "amount": qty * rate}]
                res = self.proc_svc.create_purchase_bill(
                    supplier_id=s_id,
                    supplier_bill_no=b_no,
                    items=items,
                    user_id=self.current_user.username
                )
                messagebox.showinfo(
                    "Success",
                    f"Purchase Bill Created: {res['purchase_id']}\n"
                    f"Subtotal: ₹{res['total_amount']:,.2f}\n"
                    f"TDS Deducted: ₹{res['tds_amount']:,.2f}\n"
                    f"Net Payable: ₹{res['payable_amount']:,.2f}"
                )
                self.load_bills()
                dlg.destroy()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dlg)

        btn_box = ttk.Frame(dlg)
        btn_box.grid(row=len(fields), column=0, columnspan=2, pady=16)
        ttk.Button(btn_box, text="Record Bill", command=on_save).pack(side="left", padx=8)
        ttk.Button(btn_box, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)

    def _return_selected_bill(self):
        row = self.bills_table.get_selected()
        if not row:
            messagebox.showinfo("Select Bill", "Select the vendor bill the goods came on.", parent=self)
            return
        from app.ui.return_dialog import PurchaseReturnDialog
        dlg = PurchaseReturnDialog(self, self.db, row["purchase_id"], row.get("supplier_name", ""), walk_in=False,
                                   user=self.current_user.username)
        self.wait_window(dlg)
        if dlg.result:
            self.refresh()

    # ---------------- RETURNS TO SUPPLIERS TAB ----------------
    def _build_returns_tab(self):
        bar = ttk.Frame(self.returns_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="🖨 Print Debit Note", command=self._print_selected_return).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh", command=self.load_returns).pack(side="left", padx=4)
        cols = [
            ("return_id", "Debit Note", 170),
            ("return_date", "Date", 110),
            ("supplier_name", "Supplier", 200),
            ("purchase_id", "Vendor Bill", 190),
            ("gross_amount", "Goods (₹)", 110),
            ("tds_amount", "TDS back (₹)", 110),
            ("net_amount", "Debit Note (₹)", 120),
        ]
        self.returns_table = DataTable(self.returns_tab, columns=cols,
                                       empty_text="No goods sent back yet. Select a vendor bill and use Return Goods to Supplier.")
        self.returns_table.pack(fill="both", expand=True)

    def load_returns(self):
        rets = self.proc_svc.proc_repo.returns.find({"is_deleted": 0}, sort=[("return_date", -1)], limit=200)
        self._returns_raw = {r["return_id"]: r for r in rets}
        formatted = []
        for r in rets:
            d = dict(r)
            d["return_date"] = format_date(d.get("return_date"))
            for k in ("gross_amount", "tds_amount", "net_amount"):
                d[k] = format_inr(d.get(k, 0.0), symbol=False)
            formatted.append(d)
        self.returns_table.set_data(formatted)

    def _print_selected_return(self):
        row = self.returns_table.get_selected()
        if not row:
            messagebox.showinfo("Select", "Select a debit note first.", parent=self)
            return
        from app.ui.return_dialog import open_note_pdf
        open_note_pdf(self, self.db, "purchase", self._returns_raw[row["return_id"]])

    # ---------------- PURCHASE ORDERS TAB ----------------
    def _build_po_tab(self):
        bar = ttk.Frame(self.po_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Refresh Orders", command=self.load_pos).pack(side="left", padx=4)

        cols = [
            ("po_id", "PO ID", 140),
            ("date", "Date", 110),
            ("supplier_name", "Supplier", 220),
            ("items_count", "Items", 80),
            ("total_amount", "Total (₹)", 130),
            ("status", "Status", 110),
        ]
        self.po_table = DataTable(self.po_tab, columns=cols, empty_text="No purchase orders yet. Orders you convert to a purchase appear here.")
        self.po_table.pack(fill="both", expand=True)

    def load_pos(self):
        pos = self.proc_svc.get_purchase_orders(limit=100)
        formatted = []
        for p in pos:
            d = dict(p)
            d["date"] = format_date(d.get("date"))
            d["items_count"] = len(d.get("items", []))
            d["total_amount"] = format_inr(d.get("total_amount", 0.0), symbol=False)
            formatted.append(d)
        self.po_table.set_data(formatted)

    # ---------------- GOODS RECEIPT NOTES (GRN) TAB ----------------
    def _build_grn_tab(self):
        bar = ttk.Frame(self.grn_tab)
        bar.pack(fill="x", pady=6)
        ttk.Button(bar, text="Refresh GRN Logs", command=self.load_grns).pack(side="left", padx=4)

        cols = [
            ("grn_id", "GRN ID", 140),
            ("date", "Date", 110),
            ("po_id", "Linked PO", 140),
            ("supplier_name", "Supplier", 220),
            ("received_by", "Received By", 130),
            ("status", "Status", 90),
        ]
        self.grn_table = DataTable(self.grn_tab, columns=cols, empty_text="No goods receipts yet. A receipt records the produce actually received against a purchase order and adds it to stock.")
        self.grn_table.pack(fill="both", expand=True)

    def load_grns(self):
        grns = self.proc_svc.get_grns(limit=100)
        formatted = []
        for g in grns:
            d = dict(g)
            d["date"] = format_date(d.get("date"))
            formatted.append(d)
        self.grn_table.set_data(formatted)
