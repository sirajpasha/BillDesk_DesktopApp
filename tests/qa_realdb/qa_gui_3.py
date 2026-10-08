from qa_gui_common import *
from datetime import datetime, timedelta
import tkinter as tk

root, db, auth, billing, user, win = boot()
raw = db.db
def setv(w, v): w.delete(0, tk.END); w.insert(0, v)
def item(i): return raw.items.find_one({"item_id": i})
def cust(c): return raw.customers.find_one({"cust_id": c})

# ================================================================= BILLING: negative qty vs saved lines
win.show_page("New Bill"); pump(root, 4); bf = win.frames["New Bill"]
setv(bf.row_widgets[0]["code"], "101"); bf._on_code_entered(0); setv(bf.row_widgets[0]["qty"], "10"); bf._recalculate_row(0)       # 200
setv(bf.row_widgets[1]["code"], "102"); bf._on_code_entered(1); setv(bf.row_widgets[1]["qty"], "-5"); bf._recalculate_row(1)       # -100
grand = bf._update_grand_total()
bf._open_payment_modal(); pump(root, 4); tl = toplevels(bf)[0]
find_button(tl, "Post Payment").invoke(); pump(root, 5)
saved_n = raw.bills.count_documents({})
check("GUI-BILL-13", "a bill containing an invalid line (qty -5) is NOT saved; the cashier is told which row to fix (no silent total/lines mismatch)",
      saved_n == 0 and last_dialog() and last_dialog()[1] == "Fix These Lines" and "Row 2" in last_dialog()[2], f"bills saved={saved_n}; grid total={grand}; dialog={last_dialog()}")
for _t in toplevels(bf): _t.destroy()
bf._reset_bill()

# ================================================================= ORDER FORM + SMART IMPORTER
win.show_page("New Order"); pump(root, 4); of = win.frames["New Order"]
def of_row(i): return of.row_widgets[i]
shot(root, "order_form_empty")
cases = [
    ("101 5kg",        ("Apple", 5.0, "kg")),
    ("Apple 25kg",     ("Apple", 25.0, "kg")),
    ("102 50kg",       ("Avarai", 50.0, "kg")),
    ("Banana Green 3 kg", ("Banana Green", 3.0, "kg")),
    ("Tomato 2 boxes", None),                       # unknown item -> should be flagged, not invented
    ("5 kg",           None),                       # no item name -> must not guess
    ("avarai 4",       ("Avarai", 4.0, "kg")),
    ("Apple x",        ("Apple", 1.0, "kg")),
]
for i, (line, exp) in enumerate(cases):
    of.reset_form(); pump(root, 1)
    n = of._parse_and_populate_lines(line); pump(root, 1)
    r = of_row(0); got = (r["item_var"].get(), float(r["qty_var"].get() or 0), r["unit"].get().lower()) if n else None
    if exp is None:
        check(f"GUI-IMP-{i+1:02d}", f"importer line {line!r}: unknown/ambiguous text is skipped, never guessed", n == 0 and line in of.import_skipped, f"imported={n} skipped={of.import_skipped}")
    else:
        check(f"GUI-IMP-{i+1:02d}", f"importer line {line!r} -> {exp}", got == exp, f"got {got}")
of.reset_form(); of._parse_and_populate_lines("101 5kg\n102 50kg\n5 kg\nMango 2 boxes\napple 3"); pump(root, 2)
shot(root, "order_form_after_import")

# ---- create an order through the form
of.reset_form(); pump(root, 2)
of.selected_customer = cust("Cust0001"); of.customer_var.set("Anna Adarsh Hostel")
of._parse_and_populate_lines("101 10kg\n102 20kg")           # 10*20 + 20*20 = 600
today = datetime.now()
of.date_var.set(today.strftime("%d - %m - %Y")); of.delivery_var.set((today + timedelta(days=1)).strftime("%d - %m - %Y"))
clear_dialogs(); of._save_order(); pump(root, 3)
o = raw.orders.find_one(sort=[("created_at", -1)])
check("GUI-ORD-01", "order saved via form (status pending, total 600)", o and o["status"] == "pending" and o["total_amount"] == 600.0, o and (o["order_id"], o["status"], o["total_amount"]))
check("GUI-ORD-02", "order stores hidden commission=5% and mandi fee=1% of total (30 / 6)", o and (o["commission_amt"], o["mandi_fee_amt"]) == (30.0, 6.0), o and (o["commission_amt"], o["mandi_fee_amt"]))
check("GUI-ORD-03", "commission/mandi fee shown on the order form are included in the order total (and carried to the bill)", o and o["total_amount"] == 636.0, f"form displays Comm/Mandi Fee but stored total_amount={o and o['total_amount']} excludes them (expected 636.0); converted bill also ignores them")
# validation
of.reset_form(); of.selected_customer = cust("Cust0001"); of.customer_var.set("Anna Adarsh Hostel"); of._parse_and_populate_lines("101 3kg")
of.date_var.set(today.strftime("%d - %m - %Y")); of.delivery_var.set((today - timedelta(days=3)).strftime("%d - %m - %Y")); clear_dialogs(); of._save_order()
check("GUI-ORD-04", "delivery date before order date rejected", last_dialog() and last_dialog()[1] == "Invalid Date Range", last_dialog())
of.delivery_var.set("31 - 02 - 2026"); clear_dialogs(); of._save_order()
check("GUI-ORD-05", "impossible date 31-02-2026 rejected", last_dialog() and last_dialog()[1] == "Invalid Delivery Date", last_dialog())
of.delivery_var.set("tomorrow"); clear_dialogs(); of._save_order()
check("GUI-ORD-06", "non-date text rejected", last_dialog() and last_dialog()[1] == "Invalid Delivery Date", last_dialog())
of.delivery_var.set((today + timedelta(days=1)).strftime("%d - %m - %Y")); of.row_widgets[0]["qty_var"].set("0"); clear_dialogs(); of._save_order()
check("GUI-ORD-07", "qty 0 rejected", last_dialog() and last_dialog()[1] == "Invalid Quantity", last_dialog())
of.row_widgets[0]["qty_var"].set("-3"); clear_dialogs(); of._save_order()
check("GUI-ORD-08", "negative qty rejected", last_dialog() and last_dialog()[1] == "Invalid Quantity", last_dialog())
of.row_widgets[0]["qty_var"].set("abc"); clear_dialogs(); of._save_order()
check("GUI-ORD-09", "non-numeric qty rejected", last_dialog() and last_dialog()[1] == "Invalid Quantity", last_dialog())
of.row_widgets[0]["qty_var"].set("3"); of.customer_var.set("Select Customer (F5)"); clear_dialogs(); of._save_order()
check("GUI-ORD-10", "no customer -> 'Customer Required'", last_dialog() and last_dialog()[1] == "Customer Required", last_dialog())
of.reset_form(); pump(root, 2)
of.customer_var.set("Some Typed Walk-in"); of._parse_and_populate_lines("101 1kg"); of.date_var.set(today.strftime("%d - %m - %Y")); of.delivery_var.set(today.strftime("%d - %m - %Y")); n0 = raw.orders.count_documents({})
clear_dialogs(); of._save_order()
oo = raw.orders.find_one(sort=[("created_at", -1)])
check("GUI-ORD-11", "free-typed customer name that is not in the master cannot create an order", raw.orders.count_documents({}) == n0, f"orders {n0}->{raw.orders.count_documents({})}, customer_id stored={oo and oo['customer_id']!r}")

# ---- orders list / convert / cancel
win.show_page("Orders"); pump(root, 4); ov = win.frames["Orders"]; ov.load_orders(); pump(root, 3)
shot(root, "orders_list")
check("GUI-ORD-12", "orders list shows saved orders", len(ov.orders_tree.get_children()) >= 1, len(ov.orders_tree.get_children()))
oid = o["order_id"]
ov.orders_tree.selection_set(oid); clear_dialogs()
raw.customers.update_one({"cust_id": "Cust0001"}, {"$set": {"credit_limit": 100.0}})
ov._convert_to_bill(); pump(root, 3)
bl = raw.bills.find_one({"linked_source_id": oid})
check("GUI-ORD-13", "convert-to-bill (UI) honours customer credit limit (limit 100, order 600)", bl is None, f"bill created={bool(bl)}; customer balance={cust('Cust0001')['current_balance']}; dialog={last_dialog()}")
raw.customers.update_one({"cust_id": "Cust0001"}, {"$set": {"credit_limit": 0.0}})
if bl is None:
    clear_dialogs(); ov._convert_to_bill(); pump(root, 3); bl = raw.bills.find_one({"linked_source_id": oid})
check("GUI-ORD-14", "convert-to-bill creates invoice and marks order billed", bl and raw.orders.find_one({"order_id": oid})["status"] == "billed", bl and bl["invoice_no"])
ov.load_orders(); ov.orders_tree.selection_set(oid); clear_dialogs(); ov._cancel_order(); pump(root, 3)
st = raw.orders.find_one({"order_id": oid})["status"]
check("GUI-ORD-15", "an already-BILLED order cannot be cancelled (would orphan the invoice)", st == "billed", f"order status now {st!r}; invoice {bl and bl['invoice_no']} status={raw.bills.find_one({'invoice_no': bl['invoice_no']})['status'] if bl else None}")

# ================================================================= HISTORY
win.show_page("Bill History"); pump(root, 4); hv = win.frames["Bill History"]; hv.refresh(); pump(root, 3)
shot(root, "bill_history")
n_bills = raw.bills.count_documents({"is_deleted": 0})
check("GUI-HIST-01", "history lists every bill in DB", len(hv._all_bills) == n_bills, f"ui={len(hv._all_bills)} db={n_bills}")
hv.search_var.set("zzz-no-such"); hv._apply_filter(); check("GUI-HIST-02", "search with no match shows 'Showing 0 of 0'", "0 of 0" in hv.showing_label.cget("text"), hv.showing_label.cget("text"))
hv.search_var.set("anna"); hv._apply_filter(); check("GUI-HIST-03", "search by customer name (case-insensitive)", len(hv._filtered_bills) >= 1, len(hv._filtered_bills))
hv.search_var.set("([");
try: hv._apply_filter(); ok = True
except Exception as e: ok = False
check("GUI-HIST-04", "regex-special text in search box does not crash", ok)
hv.search_var.set(""); hv._apply_filter()
target = [b for b in hv._all_bills if b.get("status_display") != "void" and b.get("customer_id") == "Cust0001"][0]
bal_before = cust("Cust0001")["current_balance"]; stock_before = item(target["items"][0]["item_id"])["stock"]
hv.tree.selection_set(target["invoice_no"]); clear_dialogs(); hv._void_selected(); pump(root, 3)
nb = raw.bills.find_one({"invoice_no": target["invoice_no"]})
check("GUI-HIST-05", "void via UI marks bill void and shows success", nb["status"] == "void" and last_dialog()[0] == "showinfo", last_dialog())
restored_qty = sum(l["qty"] for l in target["items"] if l["item_id"] == target["items"][0]["item_id"])
check("GUI-HIST-06", "void restores stock of every line of that item", item(target["items"][0]["item_id"])["stock"] == stock_before + restored_qty, (stock_before, item(target["items"][0]["item_id"])["stock"], restored_qty))
check("GUI-HIST-07", "void reduces customer balance by the bill total (balance never < 0 for an unpaid bill)", cust("Cust0001")["current_balance"] == bal_before - target["total_amount"], (bal_before, cust("Cust0001")["current_balance"]))
hv.tree.selection_set(target["invoice_no"]); clear_dialogs(); hv._void_selected()
check("GUI-HIST-08", "voiding an already void bill warns", last_dialog() and last_dialog()[0] == "showwarning", last_dialog())
check("GUI-HIST-09", "KPI 'total bills' excludes void", hv.card_total_bills_val.cget("text") == str(len([b for b in hv._all_bills if b.get('status_display') != 'void']) ), hv.card_total_bills_val.cget("text"))
hv.refresh(); bills_rev = sum(b["total_amount"] for b in raw.bills.find({"status": {"$ne": "void"}, "is_deleted": 0}))
check("GUI-HIST-10", "KPI revenue = sum of non-void bills", abs(float(hv.card_total_rev_val.cget("text").replace("₹","").replace(",","").strip() or 0) - bills_rev) < 0.01, f"ui={hv.card_total_rev_val.cget('text')} db={bills_rev}")
hv.tree.selection_remove(hv.tree.selection()); clear_dialogs(); hv._void_selected()
check("GUI-HIST-11", "void with nothing selected asks to select a bill", last_dialog() and last_dialog()[0] == "showinfo", last_dialog())

# history capped at 500 rows?
import uuid
raw.bills.insert_many([{"invoice_no": f"19990101-{i:04d}", "invoice_date": "1999-01-01", "customer_id": "CASH", "customer_name": "bulk", "items": [], "total_amount": 1.0, "balance_due": 1.0, "status": "unpaid", "is_deleted": 0, "created_at": datetime(1999, 1, 1)} for i in range(520)])
hv.refresh(); pump(root, 3)
check("GUI-HIST-12", "history shows ALL bills (>500) and KPI counts are correct", len(hv._all_bills) == raw.bills.count_documents({"is_deleted": 0}), f"ui={len(hv._all_bills)} db={raw.bills.count_documents({'is_deleted': 0})}")
raw.bills.delete_many({"customer_name": "bulk"})

# ================================================================= CONSOLIDATED REPORT
win.show_page("Consolidated Billing"); pump(root, 4); cv = win.frames["Consolidated Billing"]; shot(root, "consolidated_report")
check("GUI-CONS-01", "consolidated report view opens", cv is not None)
rep = billing.get_consolidated_report("Anna Adarsh Hostel", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"), (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
nonvoid = [b for b in raw.bills.find({"customer_id": "Cust0001", "status": {"$nin": ["void", "cancelled"]}})]
check("GUI-CONS-02", "consolidated total equals sum of non-void bills for the customer", abs(rep["total_bill_amount"] - sum(b["total_amount"] for b in nonvoid)) < 0.01, (rep["total_bill_amount"], sum(b["total_amount"] for b in nonvoid)))
try: billing.get_consolidated_report("", "2026-01-01", "2026-12-31"); ok = False
except ValueError: ok = True
check("GUI-CONS-03", "blank customer rejected", ok)
try: r = billing.get_consolidated_report("Anna Adarsh Hostel", "2026-12-31", "2026-01-01"); ok = (r["total_bill_amount"] == 0)
except Exception: ok = True
check("GUI-CONS-04", "reversed date range (from > to) yields empty / is rejected", ok)
finish(root)
