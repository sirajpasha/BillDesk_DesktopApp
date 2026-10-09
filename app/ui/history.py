import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from app import paths
import subprocess
import platform
import math
from datetime import datetime
from typing import Any, Dict, List, Optional
from app.printing.invoice import generate_invoice_pdf, generate_dc_pdf
from app.ui.print_preview import show_print_preview
from app.services.master_service import MasterService
from app.utils.currency import format_inr
from app.utils.formatters import format_date
from app.ui.components.calendar_popup import attach_date_picker
from app.ui import theme

class BillHistoryFrame(tk.Frame):
    """
    Bill History View matching 08-bills-history.png exactly.
    Features:
    - 3 Color-Coded KPI cards: Total Bills (Purple), Total Revenue (Green), Today's Bills (Orange).
    - Top Action Buttons: Consolidated Bills, + New Bill.
    - Search & Filter bar: Calendar icon with Invoice Date + Reset Date, Real-time Live Search.
    - Interactive Table:
        * Columns: Invoice #, Date, Company, Customer, Items, Amount, Status, Actions.
        * Pill-styled status tags (paid, unpaid, partial, void).
        * Per-page pagination (25, 50, 75, 100) with Previous / Next navigation.
    - Export & Print operations:
        * Download / Print Tax Invoice (PDF) matching 48-invoice-print.png & Inv- 20260911-0006.pdf.
        * Download / Print Delivery Challan (DC PDF) matching DC- 20260911-0006.pdf.
        * Full details modal with itemized breakdown.
        * Void bill with double-entry and inventory rollback.
    """
    MAX_BILLS = 5000   # newest bills loaded; a notice is shown when the history is longer

    def __init__(self, parent, db, billing, current_user=None, on_navigate=None, **kwargs):
        super().__init__(parent, bg=theme.BG, **kwargs)
        self.db = db
        self.billing = billing
        self.current_user = current_user
        self.on_navigate = on_navigate
        self.master_svc = MasterService(db)

        self._all_bills: List[Dict[str, Any]] = []
        self._filtered_bills: List[Dict[str, Any]] = []

        # Pagination State
        self.current_page = 1
        self.per_page = 25

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Top Header Strip
        top_bar = tk.Frame(self, bg=theme.BG)
        top_bar.pack(fill="x", padx=28, pady=(20, 14))

        tk.Label(
            top_bar,
            text="Bill History",
            font=("Segoe UI", 22, "bold"),
            fg=theme.TEXT,
            bg=theme.BG
        ).pack(side="left")

        actions_box = tk.Frame(top_bar, bg=theme.BG)
        actions_box.pack(side="right")

        self.consolidated_btn = tk.Button(
            actions_box,
            text="📄 Consolidated Bills",
            font=theme.F_BOLD,
            bg=theme.SURFACE,
            fg=theme.SLATE_700,
            activebackground=theme.HEADING_BG,
            relief="solid",
            bd=1,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._consolidated_bills
        )
        self.consolidated_btn.pack(side="left", padx=(0, 10))

        self.new_bill_btn = tk.Button(
            actions_box,
            text="+ New Bill",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            activeforeground=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._on_new_bill
        )
        self.new_bill_btn.pack(side="left")

        # 2. KPI Cards Row (Purple, Green, Orange matching 08-bills-history.png)
        kpi_row = tk.Frame(self, bg=theme.BG)
        kpi_row.pack(fill="x", padx=28, pady=(0, 16))

        # Total Bills (Purple)
        self.card_total_bills_val, _ = self._create_kpi_card(
            kpi_row, "0", "Total Bills", bg_color="#5046e5"
        )
        # Total Revenue (Green)
        self.card_total_rev_val, _ = self._create_kpi_card(
            kpi_row, "₹0.00", "Total Revenue", bg_color=theme.SUCCESS
        )
        # Today's Bills (Orange)
        self.card_today_bills_val, _ = self._create_kpi_card(
            kpi_row, "0", "Today's Bills", bg_color=theme.WARNING
        )

        # 3. Filter Card Container (White card with subtle border)
        filter_card = tk.Frame(self, bg=theme.SURFACE, bd=1, relief="solid", highlightthickness=0)
        filter_card.pack(fill="x", padx=28, pady=(0, 14))

        filter_inner = tk.Frame(filter_card, bg=theme.SURFACE, padx=16, pady=12)
        filter_inner.pack(fill="x")

        # Left section: Calendar Badge + Invoice Date + Reset
        date_box = tk.Frame(filter_inner, bg=theme.SURFACE)
        date_box.pack(side="left")

        cal_badge = tk.Label(
            date_box,
            text="📅",
            font=theme.F_TEXT12,
            bg="#f0f9ff",
            fg="#0284c7",
            padx=8,
            pady=4,
            relief="solid",
            bd=1
        )
        cal_badge.pack(side="left", padx=(0, 8))

        date_lbl_box = tk.Frame(date_box, bg=theme.SURFACE)
        date_lbl_box.pack(side="left")

        tk.Label(
            date_lbl_box,
            text="INVOICE DATE:",
            font=theme.F_LABEL,
            fg=theme.TEXT_MUTED,
            bg=theme.SURFACE
        ).pack(anchor="w")

        date_input_row = tk.Frame(date_lbl_box, bg=theme.SURFACE)
        date_input_row.pack(anchor="w", pady=(2, 0))

        self.date_var = tk.StringVar(value="")
        self.date_ent = tk.Entry(
            date_input_row,
            textvariable=self.date_var,
            font=theme.F_BODY,
            width=13,
            relief="solid",
            bd=1
        )
        self.date_ent.pack(side="left", padx=(0, 6), ipady=4)
        attach_date_picker(self.date_ent, "%d/%m/%Y", label="The invoice date filter", partial_ok=True)
        self.date_var.trace_add("write", lambda *_: self._on_date_changed())

        self.reset_date_btn = tk.Button(
            date_input_row,
            text="Reset Date",
            font=theme.F_LABEL,
            bg="#fee2e2",
            fg="#ef4444",
            activebackground="#fecaca",
            relief="flat",
            bd=0,
            padx=6,
            pady=2,
            cursor="hand2",
            command=self._reset_date
        )

        # Vertical Divider
        divider = tk.Frame(filter_inner, bg=theme.BORDER, width=1, height=36)
        divider.pack(side="left", padx=16)

        # Right section: Search
        search_box = tk.Frame(filter_inner, bg=theme.SURFACE)
        search_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            search_box,
            text="SEARCH (OPTIONAL):",
            font=theme.F_LABEL,
            fg=theme.TEXT_MUTED,
            bg=theme.SURFACE
        ).pack(anchor="w")

        search_input_f = tk.Frame(search_box, bg=theme.SURFACE)
        search_input_f.pack(fill="x", pady=(2, 0))

        search_icon = tk.Label(
            search_input_f,
            text="📄",
            font=theme.F_TEXT10,
            fg=theme.TEXT_FAINT,
            bg=theme.BG,
            relief="solid",
            bd=1,
            padx=6
        )
        search_icon.pack(side="left")

        self.search_var = tk.StringVar(value="")
        self.search_ent = tk.Entry(
            search_input_f,
            textvariable=self.search_var,
            font=theme.F_BODY,
            bg=theme.BG,
            relief="solid",
            bd=1
        )
        self.search_ent.pack(side="left", fill="x", expand=True, ipady=3)
        self.search_var.trace_add("write", lambda *_: self._apply_filter(reset_page=True))

        self.status_filter_var = tk.StringVar(value="All")
        self.status_filter_cb = ttk.Combobox(
            search_input_f, textvariable=self.status_filter_var, width=10, state="readonly",
            values=["All", "Unpaid", "Partial", "Paid", "Void", "Legacy"],
        )
        self.status_filter_cb.pack(side="left", padx=(8, 0))
        self.status_filter_cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter(reset_page=True))

        # 4. Main Table Card Container
        main_card = tk.Frame(self, bg=theme.SURFACE, bd=1, relief="solid", highlightthickness=0)
        main_card.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # Sub-header strip: Showing count + pagination
        sub_strip = tk.Frame(main_card, bg=theme.BG, padx=16, pady=8, bd=1, relief="solid")
        sub_strip.pack(fill="x")

        self.showing_label = tk.Label(
            sub_strip,
            text="Showing 0 to 0 of 0 bills",
            font=theme.F_BODY,
            fg=theme.TEXT_MUTED,
            bg=theme.BG
        )
        self.showing_label.pack(side="left")

        # Pagination controls
        page_box = tk.Frame(sub_strip, bg=theme.BG)
        page_box.pack(side="right")

        tk.Label(page_box, text="PER PAGE:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).pack(side="left", padx=(0, 4))
        self.per_page_var = tk.StringVar(value="25")
        per_page_cb = ttk.Combobox(page_box, textvariable=self.per_page_var, values=["25", "50", "75", "100"], width=4, state="readonly")
        per_page_cb.pack(side="left", padx=(0, 12))
        per_page_cb.bind("<<ComboboxSelected>>", self._on_per_page_changed)

        self.prev_btn = tk.Button(
            page_box,
            text="< Previous",
            font=theme.F_SMALL,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            relief="solid",
            bd=1,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._prev_page
        )
        self.prev_btn.pack(side="left", padx=(0, 6))

        self.page_label = tk.Label(
            page_box,
            text="Page 1 of 1",
            font=theme.F_BOLD,
            fg=theme.TEXT_STRONG,
            bg=theme.BG
        )
        self.page_label.pack(side="left", padx=(0, 6))

        self.next_btn = tk.Button(
            page_box,
            text="Next >",
            font=theme.F_SMALL,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            relief="solid",
            bd=1,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._next_page
        )
        self.next_btn.pack(side="left")

        # Table Container
        table_container = tk.Frame(main_card, bg=theme.SURFACE, padx=4, pady=4)
        table_container.pack(fill="both", expand=True)

        cols = ("invoice_no", "invoice_date", "company", "customer_name", "items_count", "total_amount", "status", "actions")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("invoice_no", text="Invoice #", anchor="w")
        self.tree.heading("invoice_date", text="Date", anchor="center")
        self.tree.heading("company", text="Company", anchor="w")
        self.tree.heading("customer_name", text="Customer", anchor="w")
        self.tree.heading("items_count", text="Items", anchor="center")
        self.tree.heading("total_amount", text="Amount", anchor="e")
        self.tree.heading("status", text="Status", anchor="center")
        self.tree.heading("actions", text="Right-click for actions", anchor="center")

        self.tree.column("invoice_no", width=140, anchor="w")
        self.tree.column("invoice_date", width=110, anchor="center")
        self.tree.column("company", width=130, anchor="w")
        self.tree.column("customer_name", width=220, anchor="w")
        self.tree.column("items_count", width=90, anchor="center")
        self.tree.column("total_amount", width=120, anchor="e")
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("actions", width=135, anchor="center")

        # Status Tag Color Styling
        self.tree.tag_configure("paid", foreground="#10b981", background="#f0fdf4")
        self.tree.tag_configure("unpaid", foreground=theme.DANGER, background="#fef2f2")
        self.tree.tag_configure("partial", foreground=theme.WARNING, background="#fffbeb")
        self.tree.tag_configure("void", foreground="#9ca3af", background="#f9fafb")
        self.tree.tag_configure("legacy", foreground=theme.TEXT_MUTED)

        # Scrollbar
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>", lambda _e: self._view_details())
        self.tree.bind("<Button-3>", self._show_context_menu)

        # Action Toolbar at the bottom of the card
        action_strip = tk.Frame(main_card, bg=theme.BG, padx=16, pady=8, bd=1, relief="solid")
        action_strip.pack(fill="x", side="bottom")
        # Re-pack the table after the strip: pack gives space in order, so on a short window the buttons were clipped
        table_container.pack_forget()
        table_container.pack(fill="both", expand=True)

        # 1. Preview Invoice Button (Primary Indigo)
        self.btn_prev_inv = tk.Button(
            action_strip,
            text="👁️ Preview Invoice",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            activeforeground=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._preview_invoice_selected
        )
        self.btn_prev_inv.pack(side="left", padx=(0, 6))

        # 2. Preview DC Button (Amber)
        self.btn_prev_dc = tk.Button(
            action_strip,
            text="🚚 Preview DC",
            font=theme.F_BOLD,
            bg=theme.WARNING,
            fg=theme.SURFACE,
            activebackground="#b45309",
            activeforeground=theme.SURFACE,
            relief="flat",
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._preview_dc_selected
        )
        self.btn_prev_dc.pack(side="left", padx=(0, 6))

        # 3. Download Invoice Button (Emerald green outline/solid)
        self.btn_dl_inv = tk.Button(
            action_strip,
            text="📥 Save Invoice",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SUCCESS,
            activebackground="#f0fdf4",
            activeforeground="#047857",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._download_invoice_selected
        )
        self.btn_dl_inv.pack(side="left", padx=(0, 6))

        # 4. Download DC Button (Slate outline)
        self.btn_dl_dc = tk.Button(
            action_strip,
            text="🚚 Save DC",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            activebackground=theme.BG,
            activeforeground=theme.TEXT_STRONG,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._download_dc_selected
        )
        self.btn_dl_dc.pack(side="left", padx=(0, 8))

        # 5. View Details Button
        self.btn_view = tk.Button(
            action_strip,
            text="📝 View / Edit Bill",
            font=theme.F_BODY,
            bg=theme.HEADING_BG,
            fg=theme.SLATE_700,
            activebackground=theme.BORDER,
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._view_details
        )
        self.btn_view.pack(side="left", padx=(0, 8))

        # 4. Void Button (Red outline)
        self.btn_void = tk.Button(
            action_strip,
            text="🚫 Void Bill",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg="#ef4444",
            activebackground="#fee2e2",
            relief="solid",
            bd=1,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._void_selected
        )
        self.btn_void.pack(side="left", padx=(0, 8))

        self.btn_return = tk.Button(
            action_strip, text="↩ Return Goods", font=theme.F_BODY, bg=theme.SURFACE, fg="#b45309",
            activebackground="#fef3c7", relief="solid", bd=1, padx=12, pady=4, cursor="hand2",
            command=self._return_selected
        )
        self.btn_return.pack(side="left", padx=(0, 8))
        tk.Button(
            action_strip, text="🖨 Credit Notes", font=theme.F_BODY, bg=theme.SURFACE, fg=theme.SLATE_600,
            activebackground=theme.HEADING_BG, relief="solid", bd=1, padx=12, pady=4, cursor="hand2",
            command=self._credit_notes_selected
        ).pack(side="left", padx=(0, 8))

        # 5. Refresh Button (Right aligned)
        tk.Button(
            action_strip,
            text="🔄 Refresh",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            activebackground=theme.HEADING_BG,
            relief="solid",
            bd=1,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self.refresh
        ).pack(side="right")

        # F1 (search) and F5 (refresh) are routed to this screen by the main window while it is showing

    def focus_search(self) -> None:
        self.search_ent.focus_set()

    def _create_kpi_card(self, parent, initial_val: str, label_text: str, bg_color: str):
        card = tk.Frame(parent, bg=bg_color, padx=22, pady=18, bd=0)
        card.pack(side="left", fill="both", expand=True, padx=6)

        val_label = tk.Label(
            card,
            text=initial_val,
            font=("Segoe UI", 26, "bold"),
            fg=theme.SURFACE,
            bg=bg_color,
            anchor="w"
        )
        val_label.pack(fill="x")

        sub_label = tk.Label(
            card,
            text=label_text,
            font=theme.F_TEXT10,
            fg="#e0e7ff" if bg_color == "#5046e5" else "#dcfce7" if bg_color == theme.SUCCESS else "#fef3c7",
            bg=bg_color,
            anchor="w"
        )
        sub_label.pack(fill="x", pady=(2, 0))

        return val_label, card

    def _on_new_bill(self):
        if self.on_navigate:
            self.on_navigate("New Bill")
        else:
            messagebox.showinfo("New Bill", "Please switch to the New Bill tab from the top menu.", parent=self)

    def _consolidated_bills(self):
        if self.on_navigate:
            self.on_navigate("Consolidated Billing")
        else:
            messagebox.showinfo(
                "Consolidated Bills",
                "Consolidated Billing Report:\nAggregate statement of multi-order deliveries grouped by customer.",
                parent=self
            )

    def _on_date_changed(self):
        val = self.date_var.get().strip()
        if val:
            self.reset_date_btn.pack(side="left")
        else:
            self.reset_date_btn.pack_forget()
        self._apply_filter(reset_page=True)

    def _reset_date(self):
        self.date_var.set("")

    def _on_per_page_changed(self, _event=None):
        try:
            self.per_page = int(self.per_page_var.get())
        except ValueError:
            self.per_page = 25
        self._apply_filter(reset_page=True)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_current_page()

    def _next_page(self):
        total_p = math.ceil(len(self._filtered_bills) / self.per_page) or 1
        if self.current_page < total_p:
            self.current_page += 1
            self._render_current_page()

    @staticmethod
    def display_status(raw: Any) -> str:
        """paid / unpaid / partial / void as recorded; anything else (older bills carry the word "active" and no
        payment tracking, their money sits in the customer balance) is shown as "legacy"."""
        st = str(raw or "unpaid").lower()
        return st if st in ("paid", "unpaid", "partial", "void") else "legacy"

    def refresh(self):
        bills = self.billing.search_bills(limit=self.MAX_BILLS)
        self._all_bills = []
        try:
            company_names = {c.get("company_id"): c.get("name") for c in self.db.collection("companies").find({})}
        except Exception:
            company_names = {}

        total_rev = 0.0
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_count = 0

        for b in bills:
            d = dict(b)
            date_obj = d.get("invoice_date")
            d["date_display"] = format_date(date_obj)
            d["items_count_display"] = f"{len(d.get('items', []))} items"
            amt = float(d.get("total_amount", 0.0))
            d["amount_display"] = format_inr(amt)
            d["company_display"] = d.get("company_name") or company_names.get(d.get("company_id")) or "-"
            d["status_display"] = self.display_status(d.get("status"))

            if d["status_display"] != "void":
                total_rev += amt

            inv_dt_str = ""
            if isinstance(date_obj, datetime):
                inv_dt_str = date_obj.strftime("%Y-%m-%d")
            elif isinstance(date_obj, str):
                inv_dt_str = date_obj[:10]

            if inv_dt_str == today_str and d["status_display"] != "void":
                today_count += 1

            self._all_bills.append(d)

        self._history_truncated = len(bills) >= self.MAX_BILLS
        # Sort latest bills first
        self._all_bills.sort(key=lambda x: str(x.get("invoice_no", "")), reverse=True)

        # Update KPI Cards
        self.card_total_bills_val.config(text=str(len([b for b in self._all_bills if b.get("status_display") != "void"])))
        self.card_total_rev_val.config(text=format_inr(total_rev))
        self.card_today_bills_val.config(text=str(today_count))

        self._apply_filter(reset_page=False)

    def _apply_filter(self, reset_page: bool = True):
        if reset_page:
            self.current_page = 1

        q = self.search_var.get().strip().lower()
        d_filter = self.date_var.get().strip().lower()
        status_filter = self.status_filter_var.get().strip().lower()

        self._filtered_bills = []
        for b in self._all_bills:
            inv = str(b.get("invoice_no", "")).lower()
            cust = str(b.get("customer_name", "")).lower()
            date_str = str(b.get("date_display", "")).lower()

            if q and (q not in inv and q not in cust):
                continue
            if status_filter != "all" and b.get("status_display") != status_filter:
                continue
            if d_filter and (d_filter not in date_str and d_filter not in str(b.get("invoice_date", "")).lower()):
                continue

            self._filtered_bills.append(b)

        self._render_current_page()

    def _render_current_page(self):
        total_items = len(self._filtered_bills)
        total_pages = math.ceil(total_items / self.per_page) or 1
        if self.current_page > total_pages:
            self.current_page = total_pages

        start_idx = (self.current_page - 1) * self.per_page
        end_idx = min(start_idx + self.per_page, total_items)
        page_items = self._filtered_bills[start_idx:end_idx]

        # Clear existing rows
        for item in self.tree.get_children():
            self.tree.delete(item)

        for b in page_items:
            status_txt = b.get("status_display", "unpaid")
            self.tree.insert(
                "",
                "end",
                iid=b.get("invoice_no"),
                values=(
                    b.get("invoice_no", ""),
                    b.get("date_display", ""),
                    b.get("company_display", "-"),
                    b.get("customer_name", ""),
                    b.get("items_count_display", ""),
                    b.get("amount_display", ""),
                    status_txt.lower(),
                    "Invoice · DC · Edit"
                ),
                tags=(status_txt.lower(),)
            )

        # Update showing count and pagination state
        if total_items == 0:
            self.showing_label.config(text="Showing 0 of 0 bills")
        else:
            self.showing_label.config(text=f"Showing {start_idx + 1} to {end_idx} of {total_items} bills")

        if getattr(self, "_history_truncated", False):
            self.showing_label.config(text=self.showing_label.cget("text") + f"  (latest {self.MAX_BILLS} bills loaded - narrow with search/date for older ones)")
        self.page_label.config(text=f"Page {self.current_page} of {total_pages}")
        self.prev_btn.config(state="normal" if self.current_page > 1 else "disabled")
        self.next_btn.config(state="normal" if self.current_page < total_pages else "disabled")

    def _get_selected_bill(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if not sel:
            return None
        inv_no = sel[0]
        for b in self._all_bills:
            if b.get("invoice_no") == inv_no:
                return b
        return None

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="👁️ Preview Invoice (PDF)", command=self._preview_invoice_selected)
            menu.add_command(label="🚚 Preview Delivery Challan (DC PDF)", command=self._preview_dc_selected)
            menu.add_separator()
            menu.add_command(label="📥 Download Invoice (PDF)", command=self._download_invoice_selected)
            menu.add_command(label="🚚 Download Delivery Challan (DC PDF)", command=self._download_dc_selected)
            menu.add_separator()
            menu.add_command(label="📝 View Bill Details", command=self._view_details)
            menu.add_command(label="🚫 Void Bill", command=self._void_selected)
            menu.post(event.x_root, event.y_root)

    def _preview_invoice_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice from the table first.", parent=self)
            return

        inv_no = bill["invoice_no"]
        db_bill = self.db.collection("bills").find_one({"invoice_no": inv_no})
        if not db_bill:
            messagebox.showerror("Error", f"Invoice {inv_no} not found in database.", parent=self)
            return

        try:
            out_dir = str(paths.output_dir())
            os.makedirs(out_dir, exist_ok=True)
            file_path = os.path.join(out_dir, f"Inv- {inv_no}.pdf")

            comp_id = db_bill.get("company_id")
            comp = self.master_svc.get_company(comp_id) or {}
            cust = None
            if db_bill.get("customer_id"):
                cust = self.db.collection("customers").find_one({"cust_id": db_bill["customer_id"]})

            generate_invoice_pdf(file_path, db_bill, company=comp, customer=cust)
            show_print_preview(
                self,
                file_path,
                title=f"Invoice — {inv_no}",
                default_filename=f"Inv- {inv_no}.pdf"
            )
        except Exception as ex:
            messagebox.showerror("Preview Error", f"Failed to generate invoice preview:\n{ex}", parent=self)

    def _preview_dc_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice from the table first.", parent=self)
            return

        inv_no = bill["invoice_no"]
        db_bill = self.db.collection("bills").find_one({"invoice_no": inv_no})
        if not db_bill:
            messagebox.showerror("Error", f"Invoice {inv_no} not found in database.", parent=self)
            return

        try:
            out_dir = str(paths.output_dir())
            os.makedirs(out_dir, exist_ok=True)
            file_path = os.path.join(out_dir, f"DC- {inv_no}.pdf")

            cust = None
            if db_bill.get("customer_id"):
                cust = self.db.collection("customers").find_one({"cust_id": db_bill["customer_id"]})

            dc_comp_id = (cust.get("dc_company_id") if cust else None) or db_bill.get("company_id")
            comp = self.master_svc.get_company(dc_comp_id) or {}

            generate_dc_pdf(file_path, db_bill, company=comp, customer=cust)
            show_print_preview(
                self,
                file_path,
                title=f"Delivery Challan — {inv_no}",
                default_filename=f"DC- {inv_no}.pdf"
            )
        except Exception as ex:
            messagebox.showerror("Preview Error", f"Failed to generate DC preview:\n{ex}", parent=self)

    def _download_invoice_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice from the table first.", parent=self)
            return

        inv_no = bill["invoice_no"]
        db_bill = self.db.collection("bills").find_one({"invoice_no": inv_no})
        if not db_bill:
            messagebox.showerror("Error", f"Invoice {inv_no} not found in database.", parent=self)
            return

        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")],
            initialfile=f"Inv- {inv_no}.pdf",
            title="Save Invoice PDF"
        )
        if file_path:
            try:
                comp_id = db_bill.get("company_id")
                comp = self.master_svc.get_company(comp_id) or {}
                cust = None
                if db_bill.get("customer_id"):
                    cust = self.db.collection("customers").find_one({"cust_id": db_bill["customer_id"]})

                generate_invoice_pdf(file_path, db_bill, company=comp, customer=cust)
                messagebox.showinfo("Success", f"Invoice PDF saved successfully:\n{file_path}", parent=self)
                self._open_file(file_path)
            except Exception as ex:
                messagebox.showerror("Print Error", f"Failed to generate invoice PDF:\n{ex}", parent=self)

    def _download_dc_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice from the table first.", parent=self)
            return

        inv_no = bill["invoice_no"]
        db_bill = self.db.collection("bills").find_one({"invoice_no": inv_no})
        if not db_bill:
            messagebox.showerror("Error", f"Invoice {inv_no} not found in database.", parent=self)
            return

        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")],
            initialfile=f"DC- {inv_no}.pdf",
            title="Save Delivery Challan PDF"
        )
        if file_path:
            try:
                cust = None
                if db_bill.get("customer_id"):
                    cust = self.db.collection("customers").find_one({"cust_id": db_bill["customer_id"]})

                dc_comp_id = (cust.get("dc_company_id") if cust else None) or db_bill.get("company_id")
                comp = self.master_svc.get_company(dc_comp_id) or {}

                generate_dc_pdf(file_path, db_bill, company=comp, customer=cust)
                messagebox.showinfo("Success", f"Delivery Challan PDF saved successfully:\n{file_path}", parent=self)
                self._open_file(file_path)
            except Exception as ex:
                messagebox.showerror("Print Error", f"Failed to generate DC PDF:\n{ex}", parent=self)

    def _open_file(self, file_path: str):
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

    def _return_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select the invoice the goods were bought on.", parent=self)
            return
        if bill.get("status_display") == "void":
            messagebox.showwarning("Void invoice", "A void invoice cannot have goods returned against it.", parent=self)
            return
        from app.ui.return_dialog import ReturnDialog
        dlg = ReturnDialog(self, self.db, bill["invoice_no"], bill.get("customer_name", ""),
                           walk_in=bill.get("customer_id") in (None, "CASH"),
                           user=self.current_user.username if self.current_user else "system")
        self.wait_window(dlg)
        if dlg.result:
            self.refresh()

    def _credit_notes_selected(self):
        """List the returns made against the selected invoice and print one."""
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice.", parent=self)
            return
        from app.services.returns_service import ReturnsService
        rets = ReturnsService(self.db).returns_for_invoice(bill["invoice_no"])
        if not rets:
            messagebox.showinfo("Credit notes", f"No goods have been returned against {bill['invoice_no']}.", parent=self)
            return
        from app.ui.return_dialog import open_note_pdf
        from app.utils.currency import format_inr
        dlg = tk.Toplevel(self)
        dlg.title(f"Credit notes - {bill['invoice_no']}")
        dlg.transient(self.winfo_toplevel())
        lb = tk.Listbox(dlg, width=64, height=min(10, len(rets)), font=theme.F_TEXT10)
        for r in rets:
            lb.insert(tk.END, f"{r['return_id']}   {format_date(r.get('return_date'))}   {format_inr(r.get('total_refund_amount', 0.0))}")
        lb.pack(padx=14, pady=(14, 6))
        lb.selection_set(0)

        def _print():
            sel = lb.curselection()
            if sel:
                open_note_pdf(dlg, self.db, "sales", rets[sel[0]])
        lb.bind("<Double-1>", lambda _e: _print())
        def _cancel():
            sel = lb.curselection()
            if not sel:
                return
            ret = rets[sel[0]]
            if not messagebox.askyesno("Cancel return", f"Cancel {ret['return_id']} ({format_inr(ret.get('total_refund_amount', 0.0))})?\n\n"
                                       "The credit given to the customer is taken back, the stock returns to where it was and the "
                                       "ledger is reversed. The credit note stays on file, marked cancelled.", parent=dlg):
                return
            try:
                ReturnsService(self.db).cancel_return(ret["return_id"], user_id=self.current_user.username if self.current_user else "system",
                                                      reason="cancelled from Bill History")
            except Exception as exc:
                messagebox.showerror("Cancel return", str(exc), parent=dlg)
                return
            messagebox.showinfo("Cancel return", f"{ret['return_id']} cancelled.", parent=dlg)
            dlg.destroy()
            self.refresh()

        row = tk.Frame(dlg)
        row.pack(pady=(0, 12))
        tk.Button(row, text="Print / Save PDF", command=_print, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", padx=14, pady=5).pack(side="left", padx=6)
        tk.Button(row, text="Cancel this return", command=_cancel, fg="#b91c1c", relief="solid", bd=1, padx=12, pady=4).pack(side="left", padx=6)
        self.credit_notes_dialog = dlg
        tk.Button(row, text="Close", command=dlg.destroy, relief="solid", bd=1, padx=14, pady=4).pack(side="left")

    def _void_selected(self):
        bill = self._get_selected_bill()
        if not bill:
            messagebox.showinfo("Select Bill", "Please select an invoice to void.", parent=self)
            return
        inv_no = bill["invoice_no"]
        if bill.get("status_display") == "void":
            messagebox.showwarning("Already Voided", f"Invoice {inv_no} is already voided.", parent=self)
            return

        msg = (
            f"Are you sure you want to VOID invoice {inv_no}?\n\n"
            f"This will:\n"
            f"• Reverse {bill['amount_display']} from customer's balance\n"
            f"• Return billed produce back into warehouse stock\n"
            f"• Revert returnable crate counts\n"
            f"• Mark invoice as 'void' with an audit entry"
        )
        if messagebox.askyesno("Confirm Void & Reversal", msg, parent=self):
            try:
                u_name = self.current_user.username if self.current_user else "system"
                self.billing.void_bill(inv_no, user_id=u_name)
                messagebox.showinfo("Success", f"Invoice {inv_no} voided and all financial/stock impacts reversed.", parent=self)
                self.refresh()
            except Exception as ex:
                messagebox.showerror("Void Error", str(ex), parent=self)

    def _view_details(self):
        bill = self._get_selected_bill()
        if not bill:
            return
        inv_no = bill["invoice_no"]
        db_bill = self.db.collection("bills").find_one({"invoice_no": inv_no})
        if not db_bill:
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Invoice Details — {inv_no}")
        dlg.geometry("700x520")
        dlg.transient(self)
        dlg.configure(bg=theme.SURFACE)

        # Header Strip
        top_header = tk.Frame(dlg, bg=theme.PRIMARY, padx=16, pady=12)
        top_header.pack(fill="x")
        tk.Label(
            top_header,
            text=f"Invoice: {inv_no}",
            font=theme.F_H12B,
            fg=theme.SURFACE,
            bg=theme.PRIMARY
        ).pack(side="left")

        status_str = self.display_status(db_bill.get("status")).upper()
        tk.Label(
            top_header,
            text=f"Status: {status_str}",
            font=theme.F_TEXT10B,
            fg="#dcfce7" if status_str == "PAID" else "#fee2e2" if status_str == "UNPAID" else "#fef08a",
            bg=theme.PRIMARY
        ).pack(side="right")

        # Customer & Meta Info
        info_box = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        info_box.pack(fill="x")

        c_name = db_bill.get("customer_name") or "Cash"
        inv_dt = format_date(db_bill.get("invoice_date"))
        tot_amt = format_inr(db_bill.get("total_amount", 0.0))

        tk.Label(info_box, text=f"Customer: {c_name}", font=theme.F_H11B, fg=theme.TEXT, bg=theme.SURFACE).pack(anchor="w")
        tk.Label(info_box, text=f"Date: {inv_dt}   |   Grand Total: {tot_amt}", font=theme.F_BODY, fg=theme.TEXT_MUTED, bg=theme.SURFACE).pack(anchor="w", pady=(2, 0))

        # Items Table
        items_tree = ttk.Treeview(dlg, columns=("item", "qty", "rate", "amount"), show="headings", height=9)
        items_tree.heading("item", text="Item Description")
        items_tree.heading("qty", text="Quantity")
        items_tree.heading("rate", text="Rate")
        items_tree.heading("amount", text="Amount")

        items_tree.column("item", width=300)
        items_tree.column("qty", width=100, anchor="e")
        items_tree.column("rate", width=110, anchor="e")
        items_tree.column("amount", width=120, anchor="e")

        for line in db_bill.get("items", []):
            items_tree.insert("", "end", values=(
                line.get("name", ""),
                f"{float(line.get('qty', 0)):g} {line.get('unit', 'kg')}",
                format_inr(line.get("rate", 0)),
                format_inr(line.get("amount", 0))
            ))

        items_tree.pack(fill="both", expand=True, padx=16, pady=8)

        # Dialog Footer with Print Actions
        btn_box = tk.Frame(dlg, bg=theme.SURFACE, padx=16, pady=12)
        btn_box.pack(fill="x")

        tk.Button(
            btn_box,
            text="👁️ Preview Invoice",
            font=theme.F_BOLD,
            bg=theme.PRIMARY,
            fg=theme.SURFACE,
            activebackground=theme.PRIMARY_DARK,
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._preview_invoice_selected
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_box,
            text="🚚 Preview DC",
            font=theme.F_BOLD,
            bg=theme.WARNING,
            fg=theme.SURFACE,
            activebackground="#b45309",
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._preview_dc_selected
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_box,
            text="📥 Save Invoice",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SUCCESS,
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._download_invoice_selected
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            btn_box,
            text="🚚 Save DC",
            font=theme.F_BODY,
            bg=theme.SURFACE,
            fg=theme.SLATE_600,
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._download_dc_selected
        ).pack(side="left")

        tk.Button(
            btn_box,
            text="Close",
            font=theme.F_BODY,
            bg=theme.HEADING_BG,
            fg=theme.SLATE_700,
            relief="solid",
            bd=1,
            padx=16,
            pady=4,
            cursor="hand2",
            command=dlg.destroy
        ).pack(side="right")
