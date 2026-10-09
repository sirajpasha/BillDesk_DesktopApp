"""Settings > Company Settings: manage the business entities that appear on invoices and delivery challans.

Layout follows the reference design: header + "Add Company", KPI cards (registered companies, default company),
search, and a paged table with logo, contact details, GSTIN badge, address and edit / delete actions.
"""
from __future__ import annotations

import base64
import io
import logging
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from app.printing.invoice import _resolve_company_logo
from app.services.master_service import MasterService

log = logging.getLogger(__name__)

BG, CARD, INK, MUTED, LINE = "#f3f4f6", "#ffffff", "#0f172a", "#64748b", "#e5e7eb"
PURPLE, GREEN, RED = "#5b54d6", "#059669", "#ef4444"
FONT = "Segoe UI"


def _logo_png_bytes(company: Dict[str, Any], size: int) -> Optional[bytes]:
    """The company's logo (data URI, or an /images/x.png reference resolved from app/assets) as a size x size PNG."""
    try:
        from PIL import Image
        uri = _resolve_company_logo(company)
        if not uri.startswith("data:image"):
            return None
        raw = base64.b64decode(uri.split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGBA")
            im.thumbnail((size, size))
            canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
            canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
            out = io.BytesIO()
            canvas.save(out, format="PNG")
            return out.getvalue()
    except Exception:
        log.warning("Could not render the logo of %s", company.get("company_id"), exc_info=True)
        return None


class CompanyDialog(tk.Toplevel):
    """Add / edit one company."""

    def __init__(self, parent, svc: MasterService, company: Optional[Dict[str, Any]] = None, on_saved=None, created_by: str = "system"):
        super().__init__(parent)
        self.svc, self.company, self.on_saved, self.created_by = svc, company, on_saved, created_by
        self.logo_uri: str = (company or {}).get("logo_url", "") or ""
        self._photo: Optional[tk.PhotoImage] = None
        self.title("Edit Company" if company else "Add Company")
        self.configure(bg=CARD)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)

        head = tk.Frame(self, bg=PURPLE, padx=18, pady=12)
        head.pack(fill="x")
        tk.Label(head, text=("Edit Company" if company else "Add Company"), font=(FONT, 12, "bold"), fg="#fff", bg=PURPLE).pack(anchor="w")

        body = tk.Frame(self, bg=CARD, padx=20, pady=14)
        body.pack(fill="both", expand=True)
        self.vars: Dict[str, tk.StringVar] = {}
        row = 0

        def label(text, r, required=False):
            tk.Label(body, text=text + (" *" if required else ""), font=(FONT, 9, "bold"), fg=MUTED, bg=CARD).grid(row=r, column=0, sticky="nw", pady=6, padx=(0, 14))

        def entry(key, r, required=False, text=None):
            label(text or key, r, required)
            v = tk.StringVar(value=str((company or {}).get(key, "") or ""))
            e = tk.Entry(body, textvariable=v, width=46, font=(FONT, 10), relief="solid", bd=1)
            e.grid(row=r, column=1, sticky="we", pady=6)
            self.vars[key] = v
            return e

        self.name_entry = entry("name", row, True, "Company name"); row += 1
        label("Address", row)
        self.address_txt = tk.Text(body, width=46, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word")
        self.address_txt.insert("1.0", str((company or {}).get("address", "") or ""))
        self.address_txt.grid(row=row, column=1, sticky="we", pady=6); row += 1
        entry("phone", row, text="Phone number(s)"); row += 1
        entry("email", row, text="Email"); row += 1
        entry("gst_number", row, text="GSTIN (optional)"); row += 1
        label("Terms & conditions (on invoice)", row)
        self.terms_txt = tk.Text(body, width=46, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word")
        self.terms_txt.insert("1.0", str((company or {}).get("terms_and_conditions", "") or ""))
        self.terms_txt.grid(row=row, column=1, sticky="we", pady=6); row += 1
        entry("signatory_label", row, text="Signatory title"); row += 1
        if not self.vars["signatory_label"].get():
            self.vars["signatory_label"].set("Authorized Signatory")

        label("Logo", row)
        logo_box = tk.Frame(body, bg=CARD)
        logo_box.grid(row=row, column=1, sticky="w", pady=6)
        self.logo_lbl = tk.Label(logo_box, bg=CARD, width=8, height=3, relief="solid", bd=1, text="no logo", fg=MUTED, font=(FONT, 8))
        self.logo_lbl.pack(side="left")
        tk.Button(logo_box, text="Choose...", command=self.choose_logo, relief="solid", bd=1, bg="#fff", font=(FONT, 9), padx=10).pack(side="left", padx=8)
        tk.Button(logo_box, text="Remove", command=self.remove_logo, relief="solid", bd=1, bg="#fff", font=(FONT, 9), padx=10).pack(side="left")
        row += 1
        self._show_logo()

        self.default_var = tk.BooleanVar(value=bool(company and company.get("company_id") == svc.default_company_id()))
        tk.Checkbutton(body, text="Use as the default company (used on bills that name no company)", variable=self.default_var,
                       bg=CARD, font=(FONT, 9), activebackground=CARD).grid(row=row, column=1, sticky="w", pady=(8, 0))

        foot = tk.Frame(self, bg=CARD, padx=20, pady=12)
        foot.pack(fill="x")
        tk.Button(foot, text="Save", command=self.save, bg=PURPLE, fg="#fff", relief="flat", font=(FONT, 10, "bold"), padx=22, pady=6).pack(side="right")
        tk.Button(foot, text="Cancel", command=self.destroy, relief="solid", bd=1, bg="#fff", font=(FONT, 10), padx=16, pady=5).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.name_entry.focus_set()

    # ------------------------------------------------------------------ logo
    def _show_logo(self):
        png = _logo_png_bytes({"logo_url": self.logo_uri}, 56) if self.logo_uri else None
        if png:
            self._photo = tk.PhotoImage(data=png)
            self.logo_lbl.config(image=self._photo, text="", width=60, height=60)
        else:
            self._photo = None
            self.logo_lbl.config(image="", text="no logo", width=8, height=3)

    def choose_logo(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a logo", filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.logo_uri = self.svc.logo_data_uri(path)
        except Exception as exc:
            messagebox.showerror("Logo", f"That file could not be read as an image:\n{exc}", parent=self)
            return
        self._show_logo()

    def remove_logo(self):
        self.logo_uri = ""
        self._show_logo()

    # ------------------------------------------------------------------ save
    def collect(self) -> Dict[str, Any]:
        data = {k: v.get().strip() for k, v in self.vars.items()}
        data["address"] = self.address_txt.get("1.0", "end").strip()
        data["terms_and_conditions"] = self.terms_txt.get("1.0", "end").strip()
        data["logo_url"] = self.logo_uri
        data["is_default"] = bool(self.default_var.get())
        if self.company:
            data["company_id"] = self.company["company_id"]
        else:
            data["created_by"] = self.created_by
        return data

    def save(self) -> bool:
        try:
            self.svc.save_company(self.collect())
        except ValueError as exc:
            messagebox.showwarning("Company", str(exc), parent=self)
            return False
        except Exception:
            log.exception("Saving the company failed")
            messagebox.showerror("Company", "The company could not be saved. See the log file for details.", parent=self)
            return False
        if self.on_saved:
            self.on_saved()
        self.destroy()
        return True


class CompanyConfigView(tk.Frame):
    def __init__(self, parent, db, current_user=None, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.db = db
        self.current_user = current_user
        self.svc = MasterService(db)
        self.page = 1
        self.per_page = 10
        self.search_var = tk.StringVar()
        self.per_page_var = tk.StringVar(value="10")
        self._photos: List[tk.PhotoImage] = []
        self._rows: List[Dict[str, Any]] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ layout
    def _build(self):
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.page_frame = tk.Frame(self.canvas, bg=BG)
        win = self.canvas.create_window((0, 0), window=self.page_frame, anchor="nw")
        self.page_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

        pf = tk.Frame(self.page_frame, bg=BG)
        pf.pack(fill="both", expand=True, padx=44, pady=(26, 30))

        tk.Label(pf, text="Company Configuration", font=(FONT, 20, "bold"), fg=INK, bg=BG).pack(anchor="w")
        tk.Label(pf, text="Configure company details, branding and the names that appear on invoices", font=(FONT, 10), fg=MUTED, bg=BG).pack(anchor="w", pady=(2, 18))

        head = tk.Frame(pf, bg=BG)
        head.pack(fill="x")
        title = tk.Frame(head, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="Company Configuration", font=(FONT, 14, "bold"), fg=INK, bg=BG).pack(anchor="w")
        tk.Label(title, text="Manage multiple business entities, branding, and legal information.", font=(FONT, 9), fg=MUTED, bg=BG).pack(anchor="w")
        self.add_btn = tk.Button(head, text="+  Add Company", command=self.add_company, bg=PURPLE, fg="#fff", activebackground="#4a43c2",
                                 activeforeground="#fff", relief="flat", font=(FONT, 10, "bold"), padx=20, pady=9, cursor="hand2")
        self.add_btn.pack(side="right")

        kpis = tk.Frame(pf, bg=BG)
        kpis.pack(fill="x", pady=18)
        self.kpi_count = self._kpi(kpis, "0", "Registered Companies", PURPLE, "left")
        self.kpi_default = self._kpi(kpis, "-", "Default Company", GREEN, "right")

        sbox = tk.Frame(pf, bg=CARD, highlightbackground="#d1d5db", highlightthickness=1, padx=10)
        sbox.pack(anchor="w", pady=(0, 14))
        tk.Label(sbox, text="\U0001F50D", bg=CARD, fg=MUTED, font=(FONT, 11)).pack(side="left")
        self.search_entry = tk.Entry(sbox, textvariable=self.search_var, width=42, relief="flat", font=(FONT, 10), bg=CARD, fg=INK, insertbackground=INK)
        self.search_entry.pack(side="left", ipady=8, padx=(6, 4))
        self.placeholder = tk.Label(sbox, text="Search company configuration...", bg=CARD, fg="#9ca3af", font=(FONT, 10))
        self.placeholder.place(x=38, rely=0.5, anchor="w")
        self.placeholder.bind("<Button-1>", lambda _e: self.search_entry.focus_set())
        self.search_var.trace_add("write", lambda *_: self._on_search())

        card = tk.Frame(pf, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x")
        bar = tk.Frame(card, bg=CARD, padx=22, pady=14)
        bar.pack(fill="x")
        self.total_lbl = tk.Label(bar, text="Total: 0 companies", font=(FONT, 10), fg=MUTED, bg=CARD)
        self.total_lbl.pack(side="left")
        tools = tk.Frame(bar, bg=CARD)
        tools.pack(side="right")
        for text, cmd in (("⬇  Export", self.export_csv), ("⬆  Import", self.import_csv)):
            tk.Button(tools, text=text, command=cmd, relief="solid", bd=1, bg=CARD, fg=INK, font=(FONT, 9), padx=14, pady=5, cursor="hand2").pack(side="left", padx=4)
        self.prev_btn = tk.Button(tools, text="<", command=lambda: self._go(-1), relief="solid", bd=1, bg=CARD, font=(FONT, 9), width=3)
        self.prev_btn.pack(side="left", padx=(12, 2))
        self.page_lbl = tk.Label(tools, text="Page 1 of 1", font=(FONT, 9), fg=MUTED, bg=CARD)
        self.page_lbl.pack(side="left", padx=6)
        self.next_btn = tk.Button(tools, text=">", command=lambda: self._go(1), relief="solid", bd=1, bg=CARD, font=(FONT, 9), width=3)
        self.next_btn.pack(side="left", padx=(2, 12))
        self.per_page_cbo = ttk.Combobox(tools, textvariable=self.per_page_var, values=("10", "25", "50"), state="readonly", width=4)
        self.per_page_cbo.pack(side="left")
        tk.Label(tools, text=" per page", font=(FONT, 9), fg=MUTED, bg=CARD).pack(side="left")
        self.per_page_cbo.bind("<<ComboboxSelected>>", lambda _e: self._on_per_page())

        self.table = tk.Frame(card, bg=CARD)
        self.table.pack(fill="x")
        for c, w in enumerate((3, 3, 2, 3, 2)):
            self.table.columnconfigure(c, weight=w, uniform="col")

    def _kpi(self, parent, value: str, caption: str, color: str, side: str) -> tk.Label:
        box = tk.Frame(parent, bg=color, padx=26, pady=20)
        box.pack(side=side, fill="x", expand=True, padx=(0, 10) if side == "left" else (10, 0))
        val = tk.Label(box, text=value, font=(FONT, 22, "bold"), fg="#fff", bg=color, anchor="w")
        val.pack(fill="x")
        tk.Label(box, text=caption, font=(FONT, 10), fg="#e0e7ff" if color == PURPLE else "#d1fae5", bg=color, anchor="w").pack(fill="x")
        return val

    def _wheel(self, event):
        try:
            if self.winfo_ismapped():
                self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ data & rendering
    def refresh(self):
        self.all_companies = self.svc.list_companies()
        default_id = self.svc.default_company_id()
        self.default_id = default_id
        default = next((c for c in self.all_companies if c.get("company_id") == default_id), None)
        self.kpi_count.config(text=str(len(self.all_companies)))
        self.kpi_default.config(text=(default or {}).get("name", "-"))
        self._render()

    def _filtered(self) -> List[Dict[str, Any]]:
        return self.svc.list_companies(self.search_var.get())

    def _render(self):
        self.placeholder.place_forget() if self.search_var.get() else self.placeholder.place(x=38, rely=0.5, anchor="w")
        self._rows = self._filtered()
        total = len(self._rows)
        pages = max(1, math.ceil(total / self.per_page))
        self.page = min(max(1, self.page), pages)
        start = (self.page - 1) * self.per_page
        shown = self._rows[start:start + self.per_page]

        self.total_lbl.config(text=f"Total: {total} compan{'y' if total == 1 else 'ies'}")
        self.page_lbl.config(text=f"Page {self.page} of {pages}")
        self.prev_btn.config(state="normal" if self.page > 1 else "disabled")
        self.next_btn.config(state="normal" if self.page < pages else "disabled")

        for w in self.table.winfo_children():
            w.destroy()
        self._photos.clear()
        headers = ("Company Info", "Contact Details", "Legal (GSTIN)", "Address", "Actions")
        for c, h in enumerate(headers):
            tk.Label(self.table, text=h, font=(FONT, 9, "bold"), fg="#374151", bg="#f9fafb", anchor="e" if h == "Actions" else "w",
                     padx=22, pady=11).grid(row=0, column=c, sticky="we")
        if not shown:
            tk.Label(self.table, text="No companies match your search." if self.search_var.get() else "No companies yet - click Add Company.",
                     font=(FONT, 10), fg=MUTED, bg=CARD, pady=30).grid(row=1, column=0, columnspan=5)
            return
        for r, comp in enumerate(shown, start=1):
            self._row(r, comp)

    def _row(self, r: int, comp: Dict[str, Any]):
        pad = {"padx": 22, "pady": 12}
        sep = tk.Frame(self.table, bg=LINE, height=1)
        sep.grid(row=r * 2 - 1, column=0, columnspan=5, sticky="we")
        row = r * 2

        info = tk.Frame(self.table, bg=CARD)
        info.grid(row=row, column=0, sticky="w", **pad)
        png = _logo_png_bytes(comp, 40)
        if png:
            photo = tk.PhotoImage(data=png)
            self._photos.append(photo)
            tk.Label(info, image=photo, bg=CARD).pack(side="left", padx=(0, 10))
        else:
            tk.Label(info, text=(comp.get("name") or "?")[:1].upper(), width=3, height=1, bg="#e0e7ff", fg="#4338ca", font=(FONT, 12, "bold")).pack(side="left", padx=(0, 10))
        names = tk.Frame(info, bg=CARD)
        names.pack(side="left")
        tk.Label(names, text=comp.get("name", ""), font=(FONT, 10, "bold"), fg=INK, bg=CARD, wraplength=190, justify="left").pack(anchor="w")
        sub = tk.Frame(names, bg=CARD)
        sub.pack(anchor="w")
        tk.Label(sub, text=comp.get("company_id", ""), font=(FONT, 8), fg=MUTED, bg=CARD).pack(side="left")
        if comp.get("company_id") == self.default_id:
            tk.Label(sub, text=" DEFAULT ", font=(FONT, 7, "bold"), fg="#047857", bg="#d1fae5").pack(side="left", padx=(8, 0))

        contact = tk.Frame(self.table, bg=CARD)
        contact.grid(row=row, column=1, sticky="w", **pad)
        if comp.get("phone"):
            tk.Label(contact, text="☎  " + comp["phone"], font=(FONT, 9), fg="#374151", bg=CARD, wraplength=210, justify="left", anchor="w").pack(anchor="w")
        if comp.get("email"):
            tk.Label(contact, text="✉  " + comp["email"], font=(FONT, 9), fg="#374151", bg=CARD, anchor="w").pack(anchor="w")

        gst = (comp.get("gst_number") or "").strip()
        badge = tk.Label(self.table, text=gst or "N/A", font=(FONT, 8, "bold"), fg="#4338ca" if gst else "#475569",
                         bg="#e0e7ff" if gst else "#f1f5f9", padx=10, pady=3)
        badge.grid(row=row, column=2, sticky="w", **pad)

        addr = " ".join(str(comp.get("address", "")).split())
        tk.Label(self.table, text="• " + (addr if len(addr) <= 46 else addr[:45] + "…") if addr else "", font=(FONT, 9), fg="#4b5563", bg=CARD,
                 wraplength=220, justify="left", anchor="w").grid(row=row, column=3, sticky="w", **pad)

        acts = tk.Frame(self.table, bg=CARD)
        acts.grid(row=row, column=4, sticky="e", **pad)
        cid = comp["company_id"]
        edit = tk.Button(acts, text="✏", command=lambda c=cid: self.edit_company(c), relief="solid", bd=1, bg=CARD, fg="#374151", width=3, cursor="hand2", font=("Segoe UI Emoji", 10))
        edit.pack(side="left", padx=3)
        dele = tk.Button(acts, text="\U0001F5D1", command=lambda c=cid: self.delete_company(c), relief="solid", bd=1, bg="#fef2f2", fg=RED, width=3, cursor="hand2", font=("Segoe UI Emoji", 10))
        dele.pack(side="left", padx=3)
        edit.company_id = dele.company_id = cid               # handy for tests / accessibility tooling

    # ------------------------------------------------------------------ interactions
    def _on_search(self):
        self.page = 1
        self._render()

    def _on_per_page(self):
        self.per_page = int(self.per_page_var.get())
        self.page = 1
        self._render()

    def _go(self, delta: int):
        self.page += delta
        self._render()

    def add_company(self):
        user = getattr(self.current_user, "username", "system")
        self.dialog = CompanyDialog(self, self.svc, None, on_saved=self.refresh, created_by=user)
        return self.dialog

    def edit_company(self, company_id: str):
        comp = self.svc.company_repo.find_one({"company_id": company_id})
        if comp:
            self.dialog = CompanyDialog(self, self.svc, comp, on_saved=self.refresh)
            return self.dialog

    def delete_company(self, company_id: str):
        comp = next((c for c in self.all_companies if c.get("company_id") == company_id), None)
        if not comp:
            return
        used = self.svc.company_usage(company_id)
        extra = f"\n\n{used} existing bill(s) use this company. They are not changed and still print correctly." if used else ""
        if not messagebox.askyesno("Delete Company", f"Delete '{comp.get('name')}' ({company_id})?{extra}", parent=self):
            return
        try:
            self.svc.delete_company(company_id)
        except ValueError as exc:
            messagebox.showwarning("Delete Company", str(exc), parent=self)
            return
        self.refresh()

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, title="Export companies", defaultextension=".csv", initialfile="companies.csv",
                                            filetypes=[("CSV", "*.csv")])
        if path:
            n = self.svc.export_companies_csv(path)
            messagebox.showinfo("Export", f"{n} compan{'y' if n == 1 else 'ies'} exported to\n{path}", parent=self)

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import companies (CSV with a 'name' column)", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            res = self.svc.import_companies_csv(path, created_by=getattr(self.current_user, "username", "import"))
        except Exception as exc:
            log.exception("Company import failed")
            messagebox.showerror("Import", f"The file could not be imported:\n{exc}", parent=self)
            return
        msg = f"{res['added']} added, {res['skipped']} skipped (already exist)."
        if res["errors"]:
            msg += f"\n\n{len(res['errors'])} row(s) not imported:\n" + "\n".join(res["errors"][:8])
        messagebox.showinfo("Import", msg, parent=self)
        self.refresh()
