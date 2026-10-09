"""Capture the user-guide screenshots from the real application running on the FICTIONAL demo database.

    MONGODB_URL=mongodb://127.0.0.1:27099 DB_NAME=sv_billing_qa_demo QA_SCRATCH=<dir> PYTHONPATH=tests/qa_realdb python scripts/user_guide/capture_screenshots.py
Writes PNGs to $QA_SCRATCH/guide_img and a text dump of every button / box seen to $QA_SCRATCH/ui_dump.txt (what the guide must describe)."""
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

from qa_gui_common import *            # noqa: F401,F403  (the harness: boot, pump, shot, walk, find_button, DIALOGS ...)
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageFont, ImageGrab

OUT = os.path.join(SCRATCH, "guide_img")
os.makedirs(OUT, exist_ok=True)
FAILED = []
DUMP = open(os.path.join(SCRATCH, "ui_dump.txt"), "w", encoding="utf-8")


def step(name, fn):
    try:
        fn()
        print("ok  ", name)
    except Exception:
        FAILED.append(name)
        print("FAIL", name)
        traceback.print_exc()


def dump(label, container):
    items = []
    for w in walk(container):
        try:
            if isinstance(w, (tk.Button, ttk.Button)):
                items.append("[button] " + str(w.cget("text")))
            elif isinstance(w, (tk.Label,)) and str(w.cget("text")).strip() and len(str(w.cget("text"))) < 70:
                items.append("[label] " + str(w.cget("text")).replace("\n", " / "))
            elif isinstance(w, ttk.Combobox):
                items.append("[list] " + ", ".join(map(str, w.cget("values"))))
            elif isinstance(w, ttk.Treeview):
                items.append("[columns] " + ", ".join(str(w.heading(c)["text"]) for c in w["columns"]))
        except tk.TclError:
            pass
    DUMP.write(f"\n=== {label}\n" + "\n".join(dict.fromkeys(items)) + "\n")


def save_widget(widget, name, pad=0):
    widget.update_idletasks()
    try:
        widget.lift()
        widget.attributes("-topmost", True)
    except Exception:
        pass
    pump(widget, 8)
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    ImageGrab.grab(bbox=(x - pad, y - pad, x + w + pad, y + h + pad)).save(os.path.join(OUT, name + ".png"))


def save_app(name):
    shot(root, name)
    os.replace(os.path.join(SCRATCH, "shots", name + ".png"), os.path.join(OUT, name + ".png"))


def setv(w, v):
    w.delete(0, tk.END)
    w.insert(0, v)


def new_toplevels(owner):
    return [w for w in walk(owner) if isinstance(w, tk.Toplevel)]


def last_modal(owner):
    tls = new_toplevels(owner)
    return tls[-1] if tls else None


def close_all(owner):
    for t in new_toplevels(owner):
        try:
            t.destroy()
        except tk.TclError:
            pass
    pump(root, 3)


def dialog(owner, open_fn, name, fill=None, size=None):
    """Open a dialog, optionally fill it, photograph it, close it."""
    close_all(owner)
    open_fn()
    pump(root, 10)
    d = last_modal(owner)
    assert d is not None, f"{name}: no dialog opened"
    if size:
        d.geometry(size)
        pump(root, 4)
    if fill:
        fill(d)
        pump(root, 6)
    dump(name, d)
    save_widget(d, name)
    d.destroy()
    pump(root, 3)


def blocking_dialog(owner, open_fn, name, fill=None, size=None):
    """For dialogs whose opener waits until they are closed (Return Goods): photograph from a timer, then close."""
    close_all(owner)

    def snap():
        d = last_modal(owner)
        if d is None:
            return
        if size:
            d.geometry(size)
            pump(root, 4)
        if fill:
            fill(d)
            pump(root, 6)
        dump(name, d)
        save_widget(d, name)
        d.destroy()
    root.after(1200, snap)
    open_fn()
    pump(root, 3)


# ------------------------------------------------------------------ the login screen (its own window, before the main one)
def login_shot():
    from app.ui.login_window import LoginWindow
    db0 = MongoDatabase(settings)       # noqa: F405
    db0.connect()
    r0 = tk.Tk()
    r0.withdraw()
    lw = LoginWindow(r0, AuthService(db0))     # noqa: F405
    pump(r0, 10)
    lw.username_entry.insert(0, "admin")
    pump(r0, 4)
    save_widget(lw, "01-login")
    lw.destroy()
    r0.destroy()
    db0.close()


step("login", login_shot)

root, db, auth, billing, user, win = boot("admin", "admin123")
root.geometry("1380x880+10+10")
root.update()
raw = db.db
CUST = lambda cid: raw.customers.find_one({"cust_id": cid})      # noqa: E731


def page(name, img, w=1380, h=880, extra=None, label=None):
    def run():
        close_all(root)
        root.geometry(f"{w}x{h}+10+10")
        root.update()
        win.show_page(name)
        pump(root, 12)
        if extra:
            extra()
            pump(root, 8)
        dump(label or name, root)
        save_app(img)
    step(img, run)


# ------------------------------------------------------------------ 1. overview
page("Dashboard", "03-dashboard", h=760)


def glance():
    cv = [w for w in walk(win.frames["Dashboard"]) if isinstance(w, tk.Canvas)][0]
    cv.yview_moveto(1.0)
page("Dashboard", "04-dashboard-at-a-glance", extra=glance)
page("Dashboard", "05-menu-bar", 1380, 200)

# ------------------------------------------------------------------ 2. New Bill
bf = win.frames["New Bill"]
page("New Bill", "10-new-bill-empty")


def customer_picker():
    bf._reset_bill()
    d_open = lambda: bf._open_customer_search()          # noqa: E731

    def fill(d):
        e = d.search_entry
        e.insert(0, "Green")
        d.refresh_list()
    dialog(bf, d_open, "11-customer-picker", fill)
step("customer picker", customer_picker)


def calendar_under_date():
    bf._apply_customer(CUST("CUST101"))
    pump(root, 14)
    bf.date_ent._date_picker.open()
    pump(root, 10)
    save_app("12-bill-calendar")
    bf.date_ent._date_picker.popup.close()
step("calendar", calendar_under_date)


def lines():
    bf._reset_bill()
    bf._apply_customer(CUST("CUST101"))
    pump(root, 12)
    if bf.date_ent._date_picker.popup:
        bf.date_ent._date_picker.popup.close()
    for i, (code, qty) in enumerate([("111", "25"), ("112", "40"), ("102", "12")]):
        r = bf.row_widgets[i]
        setv(r["code"], code)
        key(root, r["code"], "<Return>")           # noqa: F405
        setv(r["qty"], qty)
        key(root, r["qty"], "<Return>")            # noqa: F405
        bf._recalculate_row(i)
    r = bf.row_widgets[3]
    setv(r["code"], "101")
    bf._on_code_entered(3)
    setv(r["qty"], "6")
    bf._recalculate_row(3)
    pump(root, 8)
    save_app("13-bill-item-hint")
    for i, (code, qty) in enumerate([("106", "8"), ("107", "5")], start=4):
        r = bf.row_widgets[i]
        setv(r["code"], code)
        bf._on_code_entered(i, focus_next=False)
        setv(r["qty"], qty)
        bf._recalculate_row(i)
    pump(root, 8)
    save_app("15-new-bill-filled")
step("bill lines", lines)


def chooser():
    r = bf.row_widgets[6]
    setv(r["code"], "be")
    d = {}

    def snap():
        t = last_modal(bf)
        if t is not None:
            dump("14-item-chooser", t)
            save_widget(t, "14-item-chooser")
            t.destroy()
    root.after(900, snap)
    bf._on_code_entered(6, focus_next=False)
    r = bf.row_widgets[6]
    bf._clear_row(6)
step("item chooser", chooser)


def duplicate():
    r = bf.row_widgets[6]
    setv(r["code"], "111")

    def snap():
        t = last_modal(bf)
        if t is not None:
            dump("16-duplicate-item", t)
            save_widget(t, "16-duplicate-item")
            btn = find_button(t, "Ignore")
            if btn:
                btn.invoke()
    root.after(900, snap)
    bf._on_code_entered(6)
    bf._clear_row(6)
step("duplicate dialog", duplicate)


def payment():
    close_all(bf)
    bf._open_payment_modal()
    pump(root, 10)
    d = last_modal(bf)
    amt = [w for w in walk(d) if isinstance(w, tk.Entry)][0]
    setv(amt, "2000")
    dump("17-payment-dialog", d)
    save_widget(d, "17-payment-dialog")
    d.destroy()
step("payment dialog", payment)


def parked():
    bf.park_bill()
    pump(root, 6)
    bf._open_parked_modal()
    pump(root, 10)
    d = last_modal(bf)
    dump("18-parked-bills", d)
    save_widget(d, "18-parked-bills")
    card = [w for w in walk(d) if isinstance(w, tk.Label) and "Total:" in str(w.cget("text"))][0]
    d.update()
    card.master.event_generate("<Button-1>")
    pump(root, 10)
step("park and recall", parked)


def save_bill():
    bf._open_payment_modal()
    pump(root, 8)
    d = last_modal(bf)
    amt = [w for w in walk(d) if isinstance(w, tk.Entry)][0]
    setv(amt, "2000")
    find_button(d, "Post Payment").invoke()
    pump(root, 12)
step("save bill", save_bill)


def pdfs():
    import pymupdf as fitz
    from app.printing.invoice import generate_invoice_pdf, generate_dc_pdf
    from app.ui.print_preview import show_print_preview
    from app.services.master_service import MasterService
    b = raw.bills.find_one({"customer_id": "CUST101"}, sort=[("created_at", -1)])
    comp = MasterService(db).get_company(b.get("company_id"))
    cust = raw.customers.find_one({"cust_id": b["customer_id"]})
    out = os.path.join(SCRATCH, "guide_pdf")
    os.makedirs(out, exist_ok=True)
    inv = generate_invoice_pdf(os.path.join(out, "inv.pdf"), b, company=comp, customer=cust)
    dc = generate_dc_pdf(os.path.join(out, "dc.pdf"), b, company=comp, customer=cust)
    for src, name in ((inv, "20-invoice-pdf"), (dc, "21-delivery-challan-pdf")):
        fitz.open(src)[0].get_pixmap(dpi=85).save(os.path.join(OUT, name + ".png"))
    dlg = show_print_preview(bf, inv, title=f"Invoice — {b['invoice_no']}", default_filename="inv.pdf")
    pump(root, 16)
    dump("19-print-preview", dlg)
    save_widget(dlg, "19-print-preview")
    dlg.destroy()
step("PDFs + print preview", pdfs)

# ------------------------------------------------------------------ 3. Bill History and returns
hv = win.frames["Bill History"]
page("Bill History", "30-bill-history")


def history_filter():
    hv.status_filter_var.set("Unpaid")
    hv._apply_filter()
page("Bill History", "31-bill-history-status-filter", extra=history_filter)


def history_calendar():
    hv.status_filter_var.set("All")
    hv.date_ent.focus_set()
    hv.date_ent._date_picker.open()
    pump(root, 8)
page("Bill History", "32-bill-history-date-filter", extra=history_calendar)
if hv.date_ent._date_picker.popup:
    hv.date_ent._date_picker.popup.close()
hv.date_var.set("")


def view_bill():
    win.show_page("Bill History")
    pump(root, 8)
    hv.tree.selection_set(hv.tree.get_children()[0])
    dialog(hv, hv._view_details, "33-view-bill")
step("view bill", view_bill)


def returns():
    from app.services.returns_service import ReturnsService
    bills = [b for b in raw.bills.find({"customer_id": "CUST104", "status": {"$in": ["unpaid", "partial"]}}).sort("invoice_no", -1)]
    inv = bills[0]["invoice_no"]
    win.show_page("Bill History")
    pump(root, 8)
    hv.tree.selection_set(inv)

    def fill(d):
        d.rows[0]["qty"].set("3")
        d.rows[1]["qty"].set("1")
        d.rows[1]["waste"].set(True)
        d.reason.insert(0, "Quality not as ordered")
    blocking_dialog(hv, hv._return_selected, "34-return-goods", fill, size="760x440")
    bill_with_note = raw.sales_returns.find_one({"status": "completed", "applied_to_bill": {"$exists": True}})["original_invoice_no"]
    hv.tree.selection_set(bill_with_note)
    dialog(hv, hv._credit_notes_selected, "35-credit-notes")
    from app.printing.notes import generate_credit_note_pdf, generate_debit_note_pdf
    import pymupdf as fitz
    ret = raw.sales_returns.find_one({"status": "completed", "applied_to_bill": {"$exists": True}})
    bill = raw.bills.find_one({"invoice_no": ret["original_invoice_no"]})
    from app.services.master_service import MasterService
    p = generate_credit_note_pdf(os.path.join(SCRATCH, "guide_pdf", "cn.pdf"), ret, MasterService(db).get_company(bill.get("company_id")), raw.customers.find_one({"cust_id": ret["customer_id"]}))
    fitz.open(p)[0].get_pixmap(dpi=85).save(os.path.join(OUT, "36-credit-note-pdf.png"))
    pr = raw.purchase_returns.find_one({})
    pb = raw.purchase_bills.find_one({"purchase_id": pr["purchase_id"]})
    p2 = generate_debit_note_pdf(os.path.join(SCRATCH, "guide_pdf", "dn.pdf"), pr, MasterService(db).get_company(pb.get("company_id")), raw.suppliers.find_one({"supplier_id": pr["supplier_id"]}))
    fitz.open(p2)[0].get_pixmap(dpi=85).save(os.path.join(OUT, "74-debit-note-pdf.png"))
step("returns", returns)

# ------------------------------------------------------------------ 4. Orders
ov = win.orders_view
page("Orders", "40-orders")


def orders_calendar():
    ov.notebook.select(0)
    ent = [w for w in walk(ov) if isinstance(w, tk.Entry) and getattr(w, "_date_picker", None)][0]
    ent.focus_set()
    ent._date_picker.open()
    pump(root, 8)
page("Orders", "41-orders-date-filter", extra=orders_calendar)
for w in walk(ov):
    if isinstance(w, tk.Entry) and getattr(w, "_date_picker", None) and w._date_picker.popup:
        w._date_picker.popup.close()

of = win.order_form_view


def order_form():
    of.reset_form()
    of._apply_customer(CUST("CUST102"))
    pump(root, 12)
    of.date_picker.popup.close() if of.date_picker.popup else None
    of.import_matches([(raw.items.find_one({"item_alias": a}), q, "Kg") for a, q in (("111", 30), ("112", 50), ("106", 12), ("107", 8))])
    pump(root, 6)
page("New Order", "42-new-order", extra=order_form)


def order_calendar():
    order_form()
    of.delivery_ent.event_generate("<Button-1>", x=5, y=5)
    pump(root, 10)
page("New Order", "43-order-delivery-calendar", extra=order_calendar)
if of.delivery_picker.popup:
    of.delivery_picker.popup.close()


def smart_image():
    from PIL import Image as PILImage
    font = ImageFont.truetype(r"C:\Windows\Fonts\Nirmala.ttc", 40)
    im = PILImage.new("RGB", (800, 470), "white")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(["09.10.26", "Green Leaf", "வெங்காயம் - 20", "உருளைக்கிழங்கு - 15", "பீன்ஸ் - 10", "பீட்ரூட் - 5", "Apple - 8"]):
        d.text((40, 15 + i * 62), line, font=font, fill="black")
    path = os.path.join(SCRATCH, "guide_pdf", "order_note.png")
    im.save(path)
    win.show_page("New Order")
    pump(root, 8)
    of.reset_form()
    dlg = of._open_smart_importer()
    pump(root, 8)
    dlg.geometry("1040x640+60+30")
    dlg.load_image(path, wait=True)
    pump(root, 10)
    dump("44-smart-importer", dlg)
    save_widget(dlg, "44-smart-importer")
    dlg.destroy()
step("smart importer", smart_image)


def text_importer():
    win.show_page("New Order")
    pump(root, 8)
    of._open_text_importer()
    pump(root, 8)
    d = last_modal(of)
    t = [w for w in walk(d) if isinstance(w, tk.Text)][0]
    t.insert("1.0", "111 30kg\n112 50kg\nbeans 12 kg\nbeetroot 8\n105 20kg")
    dump("45-text-importer", d)
    save_widget(d, "45-text-importer")
    d.destroy()
step("text importer", text_importer)


def matrix():
    ov.notebook.select(ov.matrix_tab)
    ov.load_matrix()
page("Order Matrix", "46-order-matrix", extra=matrix)


def matrix_date():
    ov.notebook.select(ov.matrix_tab)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    ov.matrix_date_var.set(tomorrow)
    ov.load_matrix()
    pump(root, 6)
page("Order Matrix", "47-order-matrix-by-date", extra=matrix_date)
ov.matrix_date_var.set("")

# ------------------------------------------------------------------ 5. Masters
mv = win.masters_view
page("Item Master", "50-items")


def add_item(d):
    ents = [w for w in walk(d) if isinstance(w, tk.Entry)]
    setv(ents[0], "120")
    setv(ents[1], "Cauliflower")
    setv(ents[2], "35")
page("Item Master", "50b-items-dummy") if False else None
step("add item", lambda: (win.show_page("Item Master"), pump(root, 8), dialog(mv, mv._add_item_dialog, "51-add-item", add_item)))
page("Customer Master", "52-customers")
step("add customer", lambda: (win.show_page("Customer Master"), pump(root, 8), dialog(mv, mv._add_customer_dialog, "53-add-customer", size="900x640")))
page("Supplier Master", "54-suppliers")
step("add supplier", lambda: (win.show_page("Supplier Master"), pump(root, 8), dialog(mv, mv._add_supplier_dialog, "55-add-supplier")))
page("Fixed Rates", "56-fixed-rates")
step("add fixed rate", lambda: (win.show_page("Fixed Rates"), pump(root, 8), dialog(mv, mv._add_fixed_price_dialog, "57-add-fixed-rate", lambda d: [w for w in walk(d) if isinstance(w, tk.Entry) and getattr(w, "_date_picker", None)][0]._date_picker.open())))

# ------------------------------------------------------------------ 6. Stock and purchases
iv = win.inventory_view
page("Inventory", "60-inventory")
step("stock adjustment", lambda: (win.show_page("Inventory"), pump(root, 8), iv.stock_table.tree.selection_set(iv.stock_table.tree.get_children()[0]), dialog(iv, iv._adjustment_dialog, "61-stock-adjustment")))
page("Inventory", "62-stock-movements", extra=lambda: iv.notebook.select(1))
step("waste dialog", lambda: (win.show_page("Inventory"), pump(root, 8), iv.stock_table.tree.selection_set(iv.stock_table.tree.get_children()[0]), dialog(iv, iv._waste_dialog, "63-waste-dialog")))
page("Inventory", "64-waste-logs", extra=lambda: iv.notebook.select(2))
page("Inventory", "65-crates", extra=lambda: iv.notebook.select(3))
pv = win.procurement_view
page("Procurement", "66-vendor-bills")
step("vendor bill dialog", lambda: (win.show_page("Procurement"), pump(root, 8), dialog(pv, pv._add_vendor_bill_dialog, "67-add-vendor-bill")))
page("Procurement", "68-purchase-orders", extra=lambda: pv.notebook.select(1))
page("Procurement", "69-goods-receipts", extra=lambda: pv.notebook.select(2))
page("Procurement", "70-returns-to-suppliers", extra=lambda: pv.notebook.select(3))


def purchase_return():
    win.show_page("Procurement")
    pump(root, 8)
    pv.notebook.select(0)
    pv.bills_table.tree.selection_set(pv.bills_table.tree.get_children()[0])

    def fill(d):
        d.rows[0]["qty"].set("10")
    blocking_dialog(pv, pv._return_selected_bill, "71-return-to-supplier", fill, size="740x380")
step("purchase return", purchase_return)

# ------------------------------------------------------------------ 7. Accounts
fv = win.finance_view
page("Finance", "80-accounting-home")
page("Accounts Receivables", "81-receivables")
step("receipt dialog", lambda: (win.show_page("Accounts Receivables"), pump(root, 8), dialog(fv, fv._record_payment_dialog, "82-receipt-dialog")))


def statement():
    from app.ui.statement_view import StatementWindow
    win.show_page("Accounts Receivables")
    pump(root, 8)
    w = StatementWindow(fv, db, "CUST103", "Hotel Annapoorna")
    pump(root, 12)
    dump("83-customer-statement", w)
    save_widget(w, "83-customer-statement")
    w.destroy()
step("statement", statement)
page("Accounts Payables", "84-payables")
step("supplier payment", lambda: (win.show_page("Accounts Payables"), pump(root, 8), dialog(fv, fv._supplier_payment_dialog, "85-supplier-payment")))
page("BRS", "86-banking")
step("bank dialog", lambda: (win.show_page("BRS"), pump(root, 8), dialog(fv, fv._add_bank_dialog, "87-add-bank")))
page("Finance", "88-general-ledger", extra=lambda: fv.notebook.select(fv.gl_tab))
step("journal dialog", lambda: (win.show_page("Finance"), fv.notebook.select(fv.gl_tab), pump(root, 8), dialog(fv, fv._post_journal_dialog, "89-journal-dialog")))


def statements():
    for fn, name in ((fv._view_trial_balance, "90-trial-balance"), (fv._view_pl, "91-profit-and-loss"), (fv._view_balance_sheet, "92-balance-sheet")):
        dialog(fv, fn, name)
win.show_page("Finance")
pump(root, 8)
step("financial statements", statements)
page("Integrity Check", "93-integrity-check")

# ------------------------------------------------------------------ 8. Reports
rv = win.reports_view
for n, img in (("Daybook", "100-daybook"), ("Item-wise Sales", "101-item-wise-sales"), ("Customer-wise Sales", "102-customer-wise-sales")):
    def go(n=n):
        rv.from_var.set((datetime.now() - timedelta(days=30)).strftime("%d/%m/%Y"))
        rv.show_report(n)
    page(n, img, extra=go)


def report_calendar():
    rv.show_report("Daybook")
    rv.to_ent.event_generate("<Button-1>", x=5, y=5)
    pump(root, 8)
page("Daybook", "103-report-calendar", extra=report_calendar)
if rv.to_picker.popup:
    rv.to_picker.popup.close()


def consolidated():
    cv = win.consolidated_view
    win.show_page("Consolidated Billing")
    pump(root, 8)
    ents = billing.get_unique_bill_to_entities()
    cv.selected_entity = next(e for e in ents if e["name"] == "Green Leaf Restaurant")
    cv.bill_to_lbl.config(text="Green Leaf Restaurant")
    cv.from_date_var.set((datetime.now() - timedelta(days=12)).strftime("%d-%m-%Y"))
    cv.to_date_var.set(datetime.now().strftime("%d-%m-%Y"))
    cv._generate_report()
    pump(root, 10)
page("Consolidated Billing", "104-consolidated-bills", extra=consolidated)

# ------------------------------------------------------------------ 9. Administration
page("Handover & Settlement", "110-cash-drawer")


def open_drawer():
    av = win.admin_view
    win.show_page("Handover & Settlement")
    pump(root, 8)
    close_all(av)
    av.session_svc.admin_repo.sessions.col.update_many({"status": "open"}, {"$set": {"status": "closed"}})
    av.load_session()
    dialog(av, av._open_session_dialog, "111-open-drawer")
step("open drawer dialog", open_drawer)
page("User Management", "112-users", extra=lambda: [w for w in win.admin_view.winfo_children() if isinstance(w, ttk.Notebook)][0].select(1))
step("add user", lambda: (win.show_page("User Management"), pump(root, 8), dialog(win.admin_view, win.admin_view._add_user_dialog, "113-add-user")))
page("Company Settings", "114-company-configuration")


def company_dialog():
    cv = win.frames["Company Settings"]
    win.show_page("Company Settings")
    pump(root, 8)
    d = cv.edit_company("Company0001")
    pump(root, 10)
    dump("115-company-dialog", d)
    save_widget(d, "115-company-dialog")
    d.destroy()
step("company dialog", company_dialog)
page("DB Connection", "116-backup-and-database")
page("System Audit Logs", "117-audit-logs")

root.destroy()
DUMP.close()
print("FAILED:", FAILED, "| images:", len(os.listdir(OUT)))
