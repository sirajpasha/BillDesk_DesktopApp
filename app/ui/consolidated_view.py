from __future__ import annotations
import os
from app import paths
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from app.utils.currency import format_inr
from app.utils.formatters import format_date
from app.printing.consolidated import generate_consolidated_report_pdf
from app.ui.print_preview import show_print_preview


def _normalize_date_to_iso(date_str: str) -> str:
    """Normalize DD-MM-YYYY or YYYY-MM-DD into YYYY-MM-DD."""
    s = date_str.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def _format_iso_to_display(date_str: str) -> str:
    """Format YYYY-MM-DD to DD-MM-YYYY for display."""
    s = date_str.strip()
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return s


class CustomerSearchModal(tk.Toplevel):
    """Search dialog to select a Bill-To entity matching 06-customer-search-modal."""
    def __init__(self, parent, entities: List[Dict[str, Any]], on_select):
        super().__init__(parent)
        self.title("Select Bill To Entity")
        self.geometry("640x480")
        self.minsize(500, 350)
        self.configure(bg="#f8fafc")
        self.transient(parent)
        self.grab_set()

        self.entities = entities
        self.filtered = list(entities)
        self.on_select = on_select

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 640
        h = 480
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Header
        top = tk.Frame(self, bg="#ffffff", padx=16, pady=12, bd=1, relief="solid")
        top.pack(fill="x")
        tk.Label(
            top,
            text="🔍 Select Bill To Customer",
            font=("Segoe UI", 12, "bold"),
            fg="#0f172a",
            bg="#ffffff"
        ).pack(side="left")

        # Search box
        search_bar = tk.Frame(self, bg="#f8fafc", padx=16, pady=10)
        search_bar.pack(fill="x")

        tk.Label(search_bar, text="Search Entity:", font=("Segoe UI", 9, "bold"), fg="#475569", bg="#f8fafc").pack(anchor="w", pady=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_filter)
        self.search_entry = tk.Entry(
            search_bar,
            textvariable=self.search_var,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightcolor="#4f46e5"
        )
        self.search_entry.pack(fill="x", ipady=4)
        self.search_entry.focus_set()

        # Treeview
        tree_frame = tk.Frame(self, bg="#ffffff", padx=16, pady=6)
        tree_frame.pack(fill="both", expand=True)

        cols = ("name", "phone", "address")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="Bill To / Customer Name")
        self.tree.heading("phone", text="Phone")
        self.tree.heading("address", text="Address")

        self.tree.column("name", width=260, anchor="w")
        self.tree.column("phone", width=110, anchor="w")
        self.tree.column("address", width=220, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_choose)
        self.tree.bind("<Return>", self._on_choose)
        self.bind("<Escape>", lambda _e: self.destroy())

        # Buttons
        btn_bar = tk.Frame(self, bg="#f8fafc", padx=16, pady=10)
        btn_bar.pack(fill="x")

        tk.Button(
            btn_bar,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#f1f5f9",
            fg="#334155",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            command=self.destroy
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_bar,
            text="Select Entity",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            relief="flat",
            bd=0,
            padx=16,
            pady=5,
            cursor="hand2",
            command=self._on_choose
        ).pack(side="right")

        self._populate_tree()

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, ent in enumerate(self.filtered):
            tag = "even" if i % 2 == 0 else "odd"
            addr = ent.get("bill_to_address", "").replace("\n", " ").strip()
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(ent.get("name", ""), ent.get("bill_to_phone", ""), addr),
                tags=(tag,)
            )
        self.tree.tag_configure("even", background="#ffffff")
        self.tree.tag_configure("odd", background="#f8fafc")
        if self.filtered:
            self.tree.selection_set("0")

    def _on_filter(self, *_args):
        q = self.search_var.get().strip().lower()
        if not q:
            self.filtered = list(self.entities)
        else:
            self.filtered = [
                e for e in self.entities
                if q in e.get("name", "").lower()
                or q in e.get("bill_to_address", "").lower()
                or q in e.get("bill_to_phone", "").lower()
            ]
        self._populate_tree()

    def _on_choose(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.filtered):
            chosen = self.filtered[idx]
            self.on_select(chosen)
            self.destroy()


class ConsolidatedReportFrame(tk.Frame):
    """
    Consolidated Billing View matching:
    - 4 user UI screenshots (Bills Consolidated report)
    - 7-page PDF output artifact (SV Vegetables & Fruits Consolidated Bills)
    """
    def __init__(self, parent, db, billing_service, current_user=None, on_navigate=None, **kwargs):
        super().__init__(parent, bg="#f8fafc", **kwargs)
        self.db = db
        self.billing = billing_service
        self.current_user = current_user
        self.on_navigate = on_navigate

        self.selected_entity: Optional[Dict[str, Any]] = None
        self.current_report_data: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._load_default_entities()

    def _build_ui(self):
        # 1. Top accent strip
        tk.Frame(self, bg="#4f46e5", height=4).pack(fill="x")

        # 2. Main Scrollable Container (Canvas + Scrollbar)
        self.canvas = tk.Canvas(self, bg="#f8fafc", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#f8fafc")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Keep frame full width on canvas resize
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )

        # Mouse wheel support
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.scrollable_frame)

        # ---------------- CONTENT CONTAINER ----------------
        content = tk.Frame(self.scrollable_frame, bg="#f8fafc", padx=28, pady=16)
        content.pack(fill="both", expand=True)

        # 3. Header Title & Subtitle
        header_bar = tk.Frame(content, bg="#f8fafc")
        header_bar.pack(fill="x", pady=(0, 14))

        tk.Label(
            header_bar,
            text="Bills Consolidated report",
            font=("Segoe UI", 20, "bold"),
            fg="#0f172a",
            bg="#f8fafc"
        ).pack(anchor="w")

        tk.Label(
            header_bar,
            text="Item-wise consolidation for Bill To entities across multiple shipping locations",
            font=("Segoe UI", 9),
            fg="#64748b",
            bg="#f8fafc"
        ).pack(anchor="w", pady=(2, 0))

        # 4. KPI Cards Row (Indigo + Emerald Green, matching Screenshot 1)
        kpi_row = tk.Frame(content, bg="#f8fafc")
        kpi_row.pack(fill="x", pady=(0, 16))

        # Left KPI Card (Indigo #4f46e5)
        self.kpi_locs_card = tk.Frame(kpi_row, bg="#4f46e5", padx=20, pady=14, bd=0)
        self.kpi_locs_card.pack(side="left", fill="both", expand=True, padx=(0, 12))

        self.kpi_locs_val = tk.Label(
            self.kpi_locs_card,
            text="0",
            font=("Segoe UI", 26, "bold"),
            fg="#ffffff",
            bg="#4f46e5",
            anchor="w"
        )
        self.kpi_locs_val.pack(anchor="w")

        tk.Label(
            self.kpi_locs_card,
            text="Total Ship To Locations",
            font=("Segoe UI", 9, "bold"),
            fg="#e0e7ff",
            bg="#4f46e5",
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        # Right KPI Card (Emerald Green #10b981)
        self.kpi_amt_card = tk.Frame(kpi_row, bg="#10b981", padx=20, pady=14, bd=0)
        self.kpi_amt_card.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.kpi_amt_val = tk.Label(
            self.kpi_amt_card,
            text="₹0.00",
            font=("Segoe UI", 26, "bold"),
            fg="#ffffff",
            bg="#10b981",
            anchor="w"
        )
        self.kpi_amt_val.pack(anchor="w")

        tk.Label(
            self.kpi_amt_card,
            text="Grand Total Amount",
            font=("Segoe UI", 9, "bold"),
            fg="#d1fae5",
            bg="#10b981",
            anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        # 5. Filter Toolbar Container (White card with subtle border #e2e8f0)
        filter_card = tk.Frame(content, bg="#ffffff", bd=1, relief="solid", highlightthickness=0)
        filter_card.pack(fill="x", pady=(0, 20))

        filter_inner = tk.Frame(filter_card, bg="#ffffff", padx=16, pady=14)
        filter_inner.pack(fill="x")

        # A. Bill To Input / Selector
        bill_to_box = tk.Frame(filter_inner, bg="#f8fafc", bd=1, relief="solid", padx=10, pady=6)
        bill_to_box.pack(side="left", padx=(0, 14))

        tk.Label(
            bill_to_box,
            text="Bill To:",
            font=("Segoe UI", 8, "bold"),
            fg="#64748b",
            bg="#f8fafc"
        ).pack(side="left", padx=(0, 6))

        self.bill_to_lbl = tk.Label(
            bill_to_box,
            text="Select Billing Entity...",
            font=("Segoe UI", 9, "bold"),
            fg="#1e293b",
            bg="#f8fafc",
            width=32,
            anchor="w",
            cursor="hand2"
        )
        self.bill_to_lbl.pack(side="left", padx=(0, 8))
        self.bill_to_lbl.bind("<Button-1>", lambda _e: self._open_customer_search())
        bill_to_box.bind("<Button-1>", lambda _e: self._open_customer_search())

        search_btn = tk.Button(
            bill_to_box,
            text="🔍",
            font=("Segoe UI", 8),
            bg="#f8fafc",
            fg="#475569",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._open_customer_search
        )
        search_btn.pack(side="right")

        # B. From Date
        from_box = tk.Frame(filter_inner, bg="#f8fafc", bd=1, relief="solid", padx=10, pady=6)
        from_box.pack(side="left", padx=(0, 10))

        tk.Label(from_box, text="📅 From:", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left", padx=(0, 4))
        self.from_date_var = tk.StringVar(value="30-08-2026")
        self.from_date_ent = tk.Entry(
            from_box,
            textvariable=self.from_date_var,
            font=("Segoe UI", 9, "bold"),
            fg="#1e293b",
            bg="#f8fafc",
            relief="flat",
            bd=0,
            width=11
        )
        self.from_date_ent.pack(side="left")

        # C. To Date
        to_box = tk.Frame(filter_inner, bg="#f8fafc", bd=1, relief="solid", padx=10, pady=6)
        to_box.pack(side="left", padx=(0, 14))

        tk.Label(to_box, text="📅 To:", font=("Segoe UI", 8, "bold"), fg="#64748b", bg="#f8fafc").pack(side="left", padx=(0, 4))
        self.to_date_var = tk.StringVar(value="05-10-2026")
        self.to_date_ent = tk.Entry(
            to_box,
            textvariable=self.to_date_var,
            font=("Segoe UI", 9, "bold"),
            fg="#1e293b",
            bg="#f8fafc",
            relief="flat",
            bd=0,
            width=11
        )
        self.to_date_ent.pack(side="left")

        # D. Actions: Generate & PDF buttons
        actions_bar = tk.Frame(filter_inner, bg="#ffffff")
        actions_bar.pack(side="right")

        self.generate_btn = tk.Button(
            actions_bar,
            text="Generate",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            activebackground="#4338ca",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=18,
            pady=6,
            cursor="hand2",
            command=self._generate_report
        )
        self.generate_btn.pack(side="left", padx=(0, 6))

        self.preview_btn = tk.Button(
            actions_bar,
            text="👁️ Print Preview",
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg="#ffffff",
            activebackground="#047857",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._preview_pdf
        )
        self.preview_btn.pack(side="left", padx=(0, 6))

        self.pdf_btn = tk.Button(
            actions_bar,
            text="💾 Save PDF",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#334155",
            activebackground="#f1f5f9",
            relief="solid",
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            command=self._export_pdf
        )
        self.pdf_btn.pack(side="left")

        # 6. Report Container Area (Dynamic content)
        self.report_container = tk.Frame(content, bg="#f8fafc")
        self.report_container.pack(fill="both", expand=True)

        self._show_empty_placeholder()

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _show_empty_placeholder(self):
        for w in self.report_container.winfo_children():
            w.destroy()

        ph = tk.Frame(self.report_container, bg="#ffffff", bd=1, relief="solid", padx=40, pady=60)
        ph.pack(fill="both", expand=True)

        tk.Label(
            ph,
            text="📊",
            font=("Segoe UI", 48),
            bg="#ffffff",
            fg="#94a3b8"
        ).pack(pady=(0, 12))

        tk.Label(
            ph,
            text="NO REPORT GENERATED YET",
            font=("Segoe UI", 12, "bold"),
            fg="#475569",
            bg="#ffffff"
        ).pack()

        tk.Label(
            ph,
            text="Select a billing entity and date range, then click 'Generate' to view the consolidated report.",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#ffffff"
        ).pack(pady=(4, 0))

    def _load_default_entities(self):
        try:
            self.entities = self.billing.get_unique_bill_to_entities()
            # If Generational Southside Hospitality exists, default to it
            default_ent = None
            for e in self.entities:
                if "generational" in e.get("name", "").lower():
                    default_ent = e
                    break
            if not default_ent and self.entities:
                default_ent = self.entities[0]

            if default_ent:
                self.selected_entity = default_ent
                self.bill_to_lbl.config(text=default_ent.get("name", "")[:35])
        except Exception:
            self.entities = []

    def _open_customer_search(self):
        if not hasattr(self, "entities") or not self.entities:
            self.entities = self.billing.get_unique_bill_to_entities()

        def on_pick(ent):
            self.selected_entity = ent
            disp = ent.get("name", "")
            if len(disp) > 35:
                disp = disp[:33] + "..."
            self.bill_to_lbl.config(text=disp)

        CustomerSearchModal(self, self.entities, on_pick)

    def _generate_report(self):
        if not self.selected_entity:
            messagebox.showwarning("Select Entity", "Please select a Bill To entity first.", parent=self)
            return

        from_date = _normalize_date_to_iso(self.from_date_var.get())
        to_date = _normalize_date_to_iso(self.to_date_var.get())

        if not from_date or not to_date:
            messagebox.showwarning("Invalid Dates", "Please provide valid From and To dates.", parent=self)
            return

        try:
            report = self.billing.get_consolidated_report(
                customer_id_or_name=self.selected_entity.get("name") or self.selected_entity.get("cust_id"),
                start_date=from_date,
                end_date=to_date
            )
            self.current_report_data = report
            self._render_report(report)
            self.preview_btn.config(state="normal")
            self.pdf_btn.config(state="normal")
        except Exception as ex:
            messagebox.showerror("Report Error", f"Failed to generate consolidated report:\n{ex}", parent=self)

    def _render_report(self, report: Dict[str, Any]):
        for w in self.report_container.winfo_children():
            w.destroy()

        # Update KPI cards
        ship_reports = report.get("ship_to_reports", [])
        total_amt = float(report.get("total_bill_amount", 0.0))
        self.kpi_locs_val.config(text=str(len(ship_reports)))
        self.kpi_amt_val.config(text=format_inr(total_amt))

        # ---------------- 1. BILL SUMMARY CARD ----------------
        summary_card = tk.Frame(self.report_container, bg="#ffffff", bd=1, relief="solid")
        summary_card.pack(fill="x", pady=(0, 20))

        sum_header = tk.Frame(summary_card, bg="#f8fafc", padx=16, pady=12, bd=0)
        sum_header.pack(fill="x")
        tk.Label(
            sum_header,
            text="📅  BILL SUMMARY",
            font=("Segoe UI", 9, "bold"),
            fg="#475569",
            bg="#f8fafc"
        ).pack(side="left")

        sum_count = len(report.get("bill_summary", []))
        tk.Label(
            sum_header,
            text=f"{sum_count} Invoices",
            font=("Segoe UI", 8, "bold"),
            fg="#6366f1",
            bg="#e0e7ff",
            padx=8,
            pady=2
        ).pack(side="right")

        # Treeview for summary
        tree_frame = tk.Frame(summary_card, bg="#ffffff", padx=1, pady=1)
        tree_frame.pack(fill="x")

        s_cols = ("date", "invoice_no", "ship_to", "amount")
        s_tree = ttk.Treeview(tree_frame, columns=s_cols, show="headings", height=min(14, max(4, sum_count)))
        s_tree.heading("date", text="Inv. Date")
        s_tree.heading("invoice_no", text="Inv. Number")
        s_tree.heading("ship_to", text="Ship TO: (Customer Name)")
        s_tree.heading("amount", text="Amount")

        s_tree.column("date", width=120, anchor="center")
        s_tree.column("invoice_no", width=150, anchor="center")
        s_tree.column("ship_to", width=380, anchor="w")
        s_tree.column("amount", width=160, anchor="e")

        for i, b in enumerate(report.get("bill_summary", [])):
            d_disp = _format_iso_to_display(b.get("date", ""))
            amt_disp = format_inr(b.get("amount", 0.0))
            tag = "even" if i % 2 == 0 else "odd"
            s_tree.insert(
                "",
                "end",
                values=(d_disp, b.get("invoice_no", ""), f"📍  {b.get('ship_to', '')}", amt_disp),
                tags=(tag,)
            )

        s_tree.tag_configure("even", background="#ffffff")
        s_tree.tag_configure("odd", background="#f8fafc")
        s_tree.pack(fill="x")

        # ---------------- 2. ITEMIZED SHIP-TO SECTIONS ----------------
        for ship_to in ship_reports:
            st_name = ship_to.get("ship_to", "Location")
            st_total = float(ship_to.get("total_amount", 0.0))
            items = ship_to.get("items", [])

            loc_card = tk.Frame(self.report_container, bg="#ffffff", bd=1, relief="solid")
            loc_card.pack(fill="x", pady=(0, 20))

            # Header with Location Name and Section Total
            loc_hdr = tk.Frame(loc_card, bg="#f8fafc", padx=16, pady=12, bd=0)
            loc_hdr.pack(fill="x")

            # Left side
            l_box = tk.Frame(loc_hdr, bg="#f8fafc")
            l_box.pack(side="left")
            tk.Label(
                l_box,
                text="SHIP TO LOCATION",
                font=("Segoe UI", 8, "bold"),
                fg="#94a3b8",
                bg="#f8fafc"
            ).pack(anchor="w")
            tk.Label(
                l_box,
                text=st_name,
                font=("Segoe UI", 13, "bold"),
                fg="#1e293b",
                bg="#f8fafc"
            ).pack(anchor="w")

            # Right side
            r_box = tk.Frame(loc_hdr, bg="#f8fafc")
            r_box.pack(side="right")
            tk.Label(
                r_box,
                text="SECTION TOTAL",
                font=("Segoe UI", 8, "bold"),
                fg="#94a3b8",
                bg="#f8fafc"
            ).pack(anchor="e")
            tk.Label(
                r_box,
                text=format_inr(st_total),
                font=("Segoe UI", 15, "bold"),
                fg="#0f172a",
                bg="#f8fafc"
            ).pack(anchor="e")

            # Items Treeview
            it_frame = tk.Frame(loc_card, bg="#ffffff")
            it_frame.pack(fill="x")

            it_cols = ("desc", "qty", "unit", "rate", "amount")
            it_tree = ttk.Treeview(it_frame, columns=it_cols, show="headings", height=min(18, max(3, len(items))))
            it_tree.heading("desc", text="Item Description")
            it_tree.heading("qty", text="Qty")
            it_tree.heading("unit", text="Unit")
            it_tree.heading("rate", text="Avg. Rate")
            it_tree.heading("amount", text="Amount")

            it_tree.column("desc", width=340, anchor="w")
            it_tree.column("qty", width=110, anchor="e")
            it_tree.column("unit", width=80, anchor="center")
            it_tree.column("rate", width=120, anchor="e")
            it_tree.column("amount", width=150, anchor="e")

            for idx, itm in enumerate(items):
                tag = "even" if idx % 2 == 0 else "odd"
                it_tree.insert(
                    "",
                    "end",
                    values=(
                        itm.get("name", ""),
                        f"{float(itm.get('qty', 0.0)):.3f}",
                        itm.get("unit", "kg"),
                        format_inr(itm.get("rate", 0.0)),
                        format_inr(itm.get("amount", 0.0))
                    ),
                    tags=(tag,)
                )

            it_tree.tag_configure("even", background="#ffffff")
            it_tree.tag_configure("odd", background="#f8fafc")
            it_tree.pack(fill="x")

        # ---------------- 3. GRAND TOTAL CONSOLIDATION CARD ----------------
        grand_card = tk.Frame(self.report_container, bg="#ffffff", bd=1, relief="solid")
        grand_card.pack(fill="x", pady=(0, 24))

        # Bottom accent strip (Emerald Green)
        tk.Frame(grand_card, bg="#10b981", height=4).pack(fill="x", side="bottom")

        gt_hdr = tk.Frame(grand_card, bg="#f8fafc", padx=16, pady=12, bd=0)
        gt_hdr.pack(fill="x")

        tk.Label(
            gt_hdr,
            text="GRAND TOTAL CONSOLIDATION",
            font=("Segoe UI", 10, "bold"),
            fg="#475569",
            bg="#f8fafc"
        ).pack(anchor="w")

        tk.Label(
            gt_hdr,
            text=report.get("bill_to", ""),
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg="#f8fafc"
        ).pack(anchor="w")

        gt_items = report.get("grand_total_consolidation", [])
        gt_frame = tk.Frame(grand_card, bg="#ffffff")
        gt_frame.pack(fill="x")

        gt_cols = ("item", "total_qty", "unit", "rate", "amount")
        gt_tree = ttk.Treeview(gt_frame, columns=gt_cols, show="headings", height=min(20, max(4, len(gt_items))))
        gt_tree.heading("item", text="Consolidated Item")
        gt_tree.heading("total_qty", text="Total Qty")
        gt_tree.heading("unit", text="Unit")
        gt_tree.heading("rate", text="Rate")
        gt_tree.heading("amount", text="Total Amount")

        gt_tree.column("item", width=340, anchor="w")
        gt_tree.column("total_qty", width=110, anchor="e")
        gt_tree.column("unit", width=80, anchor="center")
        gt_tree.column("rate", width=120, anchor="e")
        gt_tree.column("amount", width=150, anchor="e")

        for idx, itm in enumerate(gt_items):
            tag = "even" if idx % 2 == 0 else "odd"
            gt_tree.insert(
                "",
                "end",
                values=(
                    itm.get("name", ""),
                    f"{float(itm.get('qty', 0.0)):.3f}",
                    itm.get("unit", "kg"),
                    format_inr(itm.get("rate", 0.0)),
                    format_inr(itm.get("amount", 0.0))
                ),
                tags=(tag,)
            )

        gt_tree.tag_configure("even", background="#ffffff")
        gt_tree.tag_configure("odd", background="#f8fafc")
        gt_tree.pack(fill="x")

        # Footer Net Total Bar (#ecfdf5)
        foot = tk.Frame(grand_card, bg="#ecfdf5", padx=20, pady=16)
        foot.pack(fill="x")

        tk.Label(
            foot,
            text="NET TOTAL",
            font=("Segoe UI", 10, "bold"),
            fg="#065f46",
            bg="#ecfdf5"
        ).pack(side="left")

        tk.Label(
            foot,
            text=format_inr(total_amt),
            font=("Segoe UI", 20, "bold"),
            fg="#059669",
            bg="#ecfdf5"
        ).pack(side="right")

        # Update canvas scroll region after UI layout
        self.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _preview_pdf(self):
        if not self.current_report_data:
            messagebox.showwarning("No Report", "Please generate a report first.", parent=self)
            return

        bill_to_safe = "".join(c for c in self.current_report_data.get("bill_to", "Report") if c.isalnum() or c in (" ", "_", "-")).strip()
        default_name = f"Consolidated_Bills_{bill_to_safe}_{self.from_date_var.get()}_to_{self.to_date_var.get()}.pdf"

        out_dir = str(paths.output_dir())
        os.makedirs(out_dir, exist_ok=True)
        temp_path = os.path.join(out_dir, default_name)

        try:
            comp = self.db.collection("companies").find_one()
            generate_consolidated_report_pdf(
                self.current_report_data,
                temp_path,
                company=comp,
                customer=self.current_report_data.get("customer")
            )
            show_print_preview(
                self,
                temp_path,
                title=f"Consolidated Bills — {bill_to_safe}",
                default_filename=default_name
            )
        except Exception as ex:
            messagebox.showerror("Preview Error", f"Failed to generate preview:\n{ex}", parent=self)

    def _export_pdf(self):
        if not self.current_report_data:
            messagebox.showwarning("No Report", "Please generate a report first.", parent=self)
            return

        bill_to_safe = "".join(c for c in self.current_report_data.get("bill_to", "Report") if c.isalnum() or c in (" ", "_", "-")).strip()
        default_name = f"Consolidated_Bills_{bill_to_safe}_{self.from_date_var.get()}_to_{self.to_date_var.get()}.pdf"

        out_dir = str(paths.output_dir())
        os.makedirs(out_dir, exist_ok=True)
        default_path = os.path.join(out_dir, default_name)

        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Consolidated Report PDF",
            initialdir=out_dir,
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf"), ("All Files", "*.*")]
        )

        if not save_path:
            return

        try:
            comp = self.db.collection("companies").find_one()
            generate_consolidated_report_pdf(
                self.current_report_data,
                save_path,
                company=comp,
                customer=self.current_report_data.get("customer")
            )

            # Prompt to open
            ans = messagebox.askyesno(
                "PDF Exported",
                f"Consolidated Report PDF generated successfully:\n{save_path}\n\nDo you want to open it now?",
                parent=self
            )
            if ans:
                if os.name == "nt":
                    os.startfile(save_path)
                else:
                    subprocess.run(["xdg-open", save_path])
        except Exception as ex:
            messagebox.showerror("Export Failed", f"Failed to export PDF:\n{ex}", parent=self)
