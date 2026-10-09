"""Smart Importer (F8): read an order from a photo / scan with Tesseract OCR, translate it to English and review it.

Left: the picture. Right: what was read (customer, date, one row per item with the English name matched to the Item Master).
Rows that could not be matched are marked "?" and can be fixed (double-click) before they are imported into the order."""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, filedialog
from typing import Any, Callable, Dict, List, Optional

from PIL import Image, ImageTk, ImageOps

from app.services.ocr_service import SmartOcrService
from app.ui import theme

log = logging.getLogger(__name__)

UNITS = ["Kg", "Nos", "Bunch", "Pkt", "Box", "Bag", "Dz", "Gm", "Crate"]
IMAGE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"), ("All files", "*.*")]


class SmartImportDialog(tk.Toplevel):
    """`on_import(rows, customer, order_date)` is called with the reviewed rows when the user presses Import to Grid.
    Each row: {"item_id", "name", "qty", "unit"}."""

    def __init__(self, parent, items_cache: List[Dict[str, Any]], customers: List[Dict[str, Any]],
                 on_import: Callable[[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[date]], None],
                 on_text_mode: Optional[Callable[[], None]] = None, ocr: Optional[SmartOcrService] = None):
        super().__init__(parent)
        self.items_cache, self.customers, self.on_import, self.on_text_mode = items_cache, customers, on_import, on_text_mode
        self.ocr = ocr or SmartOcrService()
        self.rows: List[Dict[str, Any]] = []
        self.customer: Optional[Dict[str, Any]] = None
        self.order_date: Optional[date] = None
        self._photo = None
        self._results: "queue.Queue" = queue.Queue()
        self.title("Smart Importer (F8)")
        self.geometry("1040x620")
        self.configure(bg=theme.SURFACE)
        self.transient(parent.winfo_toplevel())

        head = tk.Frame(self, bg=theme.BG, padx=20, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="Smart Importer (F8)", font=("Segoe UI", 14, "bold"), fg="#1d4ed8", bg=theme.BG).pack(side="left")
        tk.Button(head, text="✕", font=theme.F_TEXT11, relief="solid", bd=1, bg=theme.SURFACE, width=3, command=self.destroy).pack(side="right")

        body = tk.Frame(self, bg=theme.SURFACE, padx=20, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="c")
        body.columnconfigure(1, weight=6, uniform="c")
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=theme.HEADING_BG, highlightbackground=theme.BORDER, highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.image_lbl = tk.Label(left, bg=theme.HEADING_BG, fg=theme.TEXT_MUTED, font=theme.F_TEXT10, justify="center",
                                  text="Upload a photo or scan of the order\n(English or Tamil, printed or written)")
        self.image_lbl.pack(fill="both", expand=True, padx=10, pady=10)

        right = tk.Frame(body, bg=theme.SURFACE)
        right.grid(row=0, column=1, sticky="nsew")
        self.banner_lbl = tk.Label(right, text="Waiting for an image", font=theme.F_H12B, fg=theme.TEXT, bg=theme.SURFACE, anchor="w")
        self.banner_lbl.pack(fill="x")
        self.msg_lbl = tk.Label(right, text="", font=theme.F_BODY, fg="#92400e", bg="#fef3c7", anchor="w", justify="left", wraplength=470, padx=10, pady=6)
        self.msg_lbl.pack(fill="x", pady=(8, 8))
        self.msg_lbl.pack_forget()

        meta = self._meta = tk.Frame(right, bg=theme.BG, highlightbackground=theme.BORDER, highlightthickness=1, padx=14, pady=10)
        meta.pack(fill="x", pady=(0, 10))
        tk.Label(meta, text="CUSTOMER:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).grid(row=0, column=0, sticky="w")
        tk.Label(meta, text="DATE:", font=theme.F_LABEL, fg=theme.TEXT_MUTED, bg=theme.BG).grid(row=0, column=1, sticky="w", padx=(30, 0))
        self.customer_lbl = tk.Label(meta, text="-", font=theme.F_H11B, bg=theme.BG, anchor="w")
        self.customer_lbl.grid(row=1, column=0, sticky="w")
        self.date_lbl = tk.Label(meta, text="-", font=theme.F_H11B, bg=theme.BG, anchor="w")
        self.date_lbl.grid(row=1, column=1, sticky="w", padx=(30, 0))

        cols = ("item", "qty", "unit", "read")
        frame = tk.Frame(right, bg=theme.SURFACE)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse", height=9)
        for key, text, width, anchor in (("item", "Item (English)", 190, "w"), ("qty", "Qty", 60, "e"), ("unit", "Unit", 70, "w"), ("read", "Read as", 150, "w")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("unmatched", foreground="#b91c1c", background="#fef2f2")
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        tk.Label(right, text="Double-click a row to correct the item, quantity or unit.", font=theme.F_SMALL, fg=theme.TEXT_FAINT, bg=theme.SURFACE).pack(anchor="w", pady=(4, 0))

        foot = tk.Frame(self, bg=theme.SURFACE, padx=20, pady=12)
        foot.pack(fill="x")
        if on_text_mode:
            tk.Button(foot, text="Paste text instead", relief="flat", bg=theme.SURFACE, fg="#1d4ed8", cursor="hand2", command=self._text_mode).pack(side="left")
        self.import_btn = tk.Button(foot, text="Import to Grid", font=theme.F_TEXT10B, bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", padx=20, pady=7,
                                    cursor="hand2", command=self.import_rows, state="disabled")
        self.import_btn.pack(side="right")
        self.upload_btn = tk.Button(foot, text="Upload Image…", font=theme.F_TEXT10, bg=theme.SURFACE, relief="solid", bd=1, padx=16, pady=6,
                                    cursor="hand2", command=self.choose_image)
        self.upload_btn.pack(side="right", padx=(0, 10))
        self.bind("<Escape>", lambda _e: self.destroy())

    # ------------------------------------------------------------------ image -> rows
    def choose_image(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Select the order image", filetypes=IMAGE_TYPES)
        if path:
            self.load_image(path)

    def load_image(self, path: str, wait: bool = False) -> None:
        """Show the picture and read it. The OCR runs in the background so the window stays alive; `wait=True` reads it now (tests)."""
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            img.load()
        except Exception as exc:
            messagebox.showerror("Image", f"This file could not be opened as a picture:\n{exc}", parent=self)
            return
        self._show_preview(img)
        self.banner_lbl.config(text="Reading the image…", fg=theme.TEXT)
        self._set_message("")
        self.import_btn.config(state="disabled")
        self.config(cursor="watch")
        if wait:
            self._finish(self._read(img))
            return
        threading.Thread(target=lambda: self._results.put(self._read(img)), daemon=True).start()
        self.after(200, self._poll)

    def _read(self, img: Image.Image) -> Dict[str, Any]:
        try:
            return self.ocr.read_order_image(img, self.items_cache, self.customers)
        except Exception as exc:
            log.exception("OCR failed")
            return {"rows": [], "customer": None, "customer_text": "", "date": None, "raw_text": "", "engine_ok": False,
                    "warnings": [f"Reading the image failed: {exc}"]}

    def _poll(self) -> None:
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(200, self._poll)
            return
        if self.winfo_exists():
            self._finish(result)

    def _show_preview(self, img: Image.Image) -> None:
        box_w, box_h = 430, 440
        thumb = img.copy()
        thumb.thumbnail((box_w, box_h))
        self._photo = ImageTk.PhotoImage(thumb)
        self.image_lbl.config(image=self._photo, text="")

    def _finish(self, result: Dict[str, Any]) -> None:
        self.config(cursor="")
        self.upload_btn.config(text="Upload Another")
        self.customer = result.get("customer")
        self.order_date = result.get("date")
        text = (self.customer or {}).get("name") or result.get("customer_text") or "-"
        self.customer_lbl.config(text=text if self.customer or text == "-" else f"{text}  (not in master)")
        self.date_lbl.config(text=self.order_date.strftime("%d/%m/%Y") if self.order_date else "-")
        self.rows = [{"item_id": r.get("item_id") if r.get("matched") else None, "name": r.get("name") if r.get("matched") else "",
                      "qty": float(r.get("qty") or 1), "unit": r.get("unit") or "Kg", "read": r.get("raw_query", ""), "matched": bool(r.get("matched"))}
                     for r in result.get("rows", [])]
        self.warnings = list(result.get("warnings", []))
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), tags=() if r["matched"] else ("unmatched",),
                             values=(r["name"] if r["matched"] else "?  (choose item)", f"{r['qty']:g}", r["unit"], r["read"]))
        bad = sum(1 for r in self.rows if not r["matched"])
        warnings = list(getattr(self, "warnings", []))
        if self.rows and not bad and not warnings:
            self.banner_lbl.config(text="Data extracted", fg="#15803d")
        elif self.rows or warnings:
            self.banner_lbl.config(text="Data extracted with warnings", fg="#b45309")
        self._set_message("\n".join(f"• {w}" for w in warnings))
        self.import_btn.config(state="normal" if any(r["matched"] for r in self.rows) else "disabled")

    def _set_message(self, text: str) -> None:
        if text:
            self.msg_lbl.config(text=text)
            self.msg_lbl.pack(fill="x", pady=(8, 8), before=self._meta)
        else:
            self.msg_lbl.pack_forget()

    # ------------------------------------------------------------------ correcting a row
    def edit_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        i = int(sel[0])
        row = self.rows[i]
        dlg = tk.Toplevel(self)
        dlg.title("Correct line")
        dlg.transient(self)
        dlg.configure(bg=theme.SURFACE, padx=18, pady=14)
        names = sorted({str(it.get("name", "")) for it in self.items_cache if it.get("name")}, key=str.lower)
        tk.Label(dlg, text=f"Read as: {row['read'] or '-'}", fg=theme.TEXT_MUTED, bg=theme.SURFACE).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(dlg, text="Item", bg=theme.SURFACE).grid(row=1, column=0, sticky="w")
        item_var = tk.StringVar(value=row["name"])
        item_cb = ttk.Combobox(dlg, textvariable=item_var, values=names, width=34)
        item_cb.grid(row=1, column=1, pady=3)
        tk.Label(dlg, text="Quantity", bg=theme.SURFACE).grid(row=2, column=0, sticky="w")
        qty_var = tk.StringVar(value=f"{row['qty']:g}")
        tk.Entry(dlg, textvariable=qty_var, width=12, relief="solid", bd=1).grid(row=2, column=1, sticky="w", pady=3)
        tk.Label(dlg, text="Unit", bg=theme.SURFACE).grid(row=3, column=0, sticky="w")
        unit_var = tk.StringVar(value=row["unit"])
        ttk.Combobox(dlg, textvariable=unit_var, values=UNITS, width=10).grid(row=3, column=1, sticky="w", pady=3)

        def _save():
            try:
                qty = float(qty_var.get().strip())
                if qty <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Quantity", "Enter a quantity greater than zero.", parent=dlg)
                return
            item = next((it for it in self.items_cache if str(it.get("name", "")).strip().lower() == item_var.get().strip().lower()), None)
            if not item:
                messagebox.showwarning("Item", "Choose an item from the list.", parent=dlg)
                return
            row.update({"item_id": item.get("item_id"), "name": item.get("name"), "qty": qty, "unit": unit_var.get() or "Kg", "matched": True})
            dlg.destroy()
            self._render()

        def _remove():
            self.rows.pop(i)
            dlg.destroy()
            self._render()

        bar = tk.Frame(dlg, bg=theme.SURFACE)
        bar.grid(row=4, column=0, columnspan=2, pady=(12, 0), sticky="e")
        tk.Button(bar, text="Remove line", fg="#b91c1c", relief="solid", bd=1, command=_remove).pack(side="left", padx=6)
        tk.Button(bar, text="Save", bg=theme.PRIMARY, fg=theme.SURFACE, relief="flat", padx=16, command=_save).pack(side="left")
        item_cb.focus_set()
        self.edit_dialog = dlg

    # ------------------------------------------------------------------ hand over
    def import_rows(self) -> None:
        good = [{"item_id": r["item_id"], "name": r["name"], "qty": r["qty"], "unit": r["unit"]} for r in self.rows if r["matched"]]
        if not good:
            return
        skipped = len(self.rows) - len(good)
        if skipped and not messagebox.askyesno("Import", f"{skipped} line(s) are not matched to an item and will be left out.\nImport the other {len(good)}?", parent=self):
            return
        self.on_import(good, self.customer, self.order_date)
        self.destroy()

    def _text_mode(self) -> None:
        self.destroy()
        if self.on_text_mode:
            self.on_text_mode()
