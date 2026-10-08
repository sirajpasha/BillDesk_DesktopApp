from qa_gui_common import *
from datetime import datetime, timezone, timedelta
import tkinter as tk

root, db, auth, billing, user, win = boot()
raw = db.db
win.show_page("New Bill"); pump(root, 5)
bf = win.frames["New Bill"]
def row(i): return bf.row_widgets[i]
def setv(w, v):
    w.delete(0, tk.END); w.insert(0, v)
def reset_form(): bf._reset_bill(); pump(root, 2)
def item(i): return raw.items.find_one({"item_id": i})
def cust(c): return raw.customers.find_one({"cust_id": c})

# ---------------------------------------------------------- grid basics
check("GUI-BILL-01", "default grid has settings.default_num_rows rows", len(bf.row_widgets) == settings.default_num_rows, len(bf.row_widgets))
shot(root, "billing_empty")

# real <Return> key events
setv(row(0)["code"], "101"); key(root, row(0)["code"], "<Return>")
check("GUI-BILL-02", "code 101 + Enter fetches Apple, unit kg, rate 20.00, qty 1", (row(0)["name"].get(), row(0)["unit"].get(), row(0)["rate"].get(), row(0)["qty"].get()) == ("Apple","kg","20.00","1"),
      (row(0)["name"].get(), row(0)["unit"].get(), row(0)["rate"].get(), row(0)["qty"].get()))
check("GUI-BILL-03", "after code Enter, focus moves to Qty", root.focus_get() is row(0)["qty"], root.focus_get())
setv(row(0)["qty"], "2.5"); key(root, row(0)["qty"], "<Return>")
check("GUI-BILL-04", "Qty Enter moves focus to Unit", root.focus_get() is row(0)["unit"], root.focus_get())
check("GUI-BILL-05", "line amount = 2.5 x 20 = 50.00", row(0)["amount"].cget("text") == "₹50.00", row(0)["amount"].cget("text"))
check("GUI-BILL-06", "grand total label updates", "50.00" in bf.total_lbl.cget("text"), bf.total_lbl.cget("text"))

# unknown code
clear_dialogs()
setv(row(1)["code"], "ZZZ999"); key(root, row(1)["code"], "<Return>")
nm = row(1)["name"].get()
bf._clear_row(1)
bf._clear_row(0); setv(row(5)["code"], "ZZZ999"); bf._on_code_entered(5); pump(root, 2)
check("GUI-BILL-07", "unknown item code 'ZZZ999' must NOT silently fill a random item (Apple)", row(5)["name"].get() == "", f"typed ZZZ999 -> row filled with {row(5)['name'].get()!r} code={row(5)['code'].get()!r} rate={row(5)['rate'].get()!r}")
bf._clear_row(5)
setv(row(0)["code"], "101"); bf._on_code_entered(0); setv(row(0)["qty"], "2.5"); bf._recalculate_row(0)
# name-prefix lookup
setv(row(1)["code"], "banana"); key(root, row(1)["code"], "<Return>")
check("GUI-BILL-08", "typing name prefix 'banana' resolves a Banana item", "banana" in row(1)["name"].get().lower(), row(1)["name"].get())
bf._clear_row(1)
# regex metacharacters in code box
for bad in ["(", "[a-", ".*", "\\"]:
    try:
        setv(row(2)["code"], bad); bf._on_code_entered(2); ok = True; ev = row(2)["name"].get()
    except Exception as e:
        ok = False; ev = repr(e)
    check(f"GUI-BILL-09-{bad!r}", f"regex metachar {bad!r} in code box does not raise", ok, f"name={ev!r}")
    bf._clear_row(2)

# rate keystroke recalc
setv(row(3)["code"], "102"); bf._on_code_entered(3); setv(row(3)["qty"], "4"); row(3)["rate"].delete(0, tk.END)
vals = []
for ch in "123":
    row(3)["rate"].insert(tk.END, ch); key(root, row(3)["rate"], "<KeyRelease>"); vals.append(row(3)["amount"].cget("text"))
check("GUI-BILL-10", "keystroke rate 1,12,123 x qty 4 -> 4.00 / 48.00 / 492.00", vals == ["₹4.00","₹48.00","₹492.00"], vals)
# non-numeric / negative
setv(row(3)["qty"], "abc"); bf._recalculate_row(3)
check("GUI-BILL-11", "non-numeric qty treated as 0 (amount 0.00)", row(3)["amount"].cget("text") == "₹0.00", row(3)["amount"].cget("text"))
setv(row(3)["qty"], "-5"); setv(row(3)["rate"], "20"); bf._recalculate_row(3)
tot = bf._update_grand_total()
check("GUI-BILL-12", "negative qty must not reduce the grand total", row(3)["amount"].cget("text") != "₹-100.00" and tot >= 50.0, f"row amount={row(3)['amount'].cget('text')} grand_total={tot}")
reset_form()

# ---------------------------------------------------------- customer selection & fixed price
now = datetime.now(timezone.utc)
raw.fixed_prices.delete_many({})
raw.fixed_prices.insert_one({"customer_id":"Cust0001","item_id":"FRU0001","rate":12.0,"is_active":True,"start_date":now-timedelta(days=2),"end_date":now+timedelta(days=2)})
setv(row(0)["code"], "101"); bf._on_code_entered(0)
before = row(0)["rate"].get()
bf._open_customer_search(); pump(root, 4)
tl = toplevels(bf)[0]
shot(root, "billing_customer_search")
cards = [w for w in walk(tl) if isinstance(w, tk.Label) and w.cget("text") == "Anna Adarsh Hostel"]
check("GUI-BILL-14", "customer search lists seeded customer 'Anna Adarsh Hostel'", bool(cards), [w.cget("text") for w in walk(tl) if isinstance(w, tk.Label)][:6])
# search filter
ent = [w for w in walk(tl) if isinstance(w, tk.Entry)][0]
ent.insert(0, "9444434066"); ent.event_generate("<KeyRelease>"); pump(root, 3)
names = [w.cget("text") for w in walk(tl) if isinstance(w, tk.Label)]
check("GUI-BILL-15", "search by bill_to_phone finds Anna Adarsh Hostel", "Anna Adarsh Hostel" in names, names[:6])
cards = [w for w in walk(tl) if isinstance(w, tk.Label) and w.cget("text") == "Anna Adarsh Hostel"]
cards[0].master.event_generate("<Button-1>"); pump(root, 3)
check("GUI-BILL-16", "picking customer applies contract rate 12.00 to existing row (was %s)" % before, row(0)["rate"].get() == "12.00", row(0)["rate"].get())
check("GUI-BILL-17", "delivery/bill-to labels filled", bf.customer_var.get() == "Anna Adarsh Hostel", bf.customer_var.get())

# ---------------------------------------------------------- SAVE: customer pays everything in cash at counter
setv(row(0)["qty"], "10"); bf._recalculate_row(0)         # 10 x 12 = 120
clear_dialogs()
bf._open_payment_modal(); pump(root, 4)
tl = toplevels(bf)[0]
post = find_button(tl, "Post Payment"); post.invoke(); pump(root, 6)
d = last_dialog()
check("GUI-BILL-18", "save shows 'Bill Saved' with invoice number", d and d[0]=="showinfo" and "Invoice #" in d[2], d)
bill = raw.bills.find_one(sort=[("created_at", -1)])
check("GUI-BILL-19", "bill persisted with total 120", bill and bill["total_amount"] == 120.0, bill and bill["total_amount"])
check("GUI-BILL-20", "fully-paid-at-counter bill is stored as status=paid, balance_due=0", bill["status"] == "paid" and bill["balance_due"] == 0, f"status={bill['status']} balance_due={bill['balance_due']}")
check("GUI-BILL-21", "payment receipt (Cash 120) recorded in payments collection", raw.payments.count_documents({}) == 1, f"payments={raw.payments.count_documents({})}")
check("GUI-BILL-22", "customer outstanding balance NOT increased when paid in full (expected 0)", cust("Cust0001")["current_balance"] == 0.0, f"current_balance={cust('Cust0001')['current_balance']}")
check("GUI-BILL-23", "company chosen in the form is stored on the bill", bill.get("company_id") not in (None, ""), f"company_id={bill.get('company_id')!r}")
check("GUI-BILL-24", "stock decremented by 10", item("FRU0001")["stock"] == 90.0, item("FRU0001")["stock"])
check("GUI-BILL-25", "form reset after save", bf.row_widgets[0]["code"].get() == "" and bf.customer_var.get() == "Cash")

# ---------------------------------------------------------- SAVE: partial payment (credit sale)
bf._open_customer_search(); pump(root, 3); tl = toplevels(bf)[0]
[w for w in walk(tl) if isinstance(w, tk.Label) and w.cget("text") == "Anna Adarsh Hostel"][0].master.event_generate("<Button-1>"); pump(root, 3)
setv(row(0)["code"], "102"); bf._on_code_entered(0); setv(row(0)["qty"], "10"); setv(row(0)["rate"], "50"); bf._recalculate_row(0)   # 500
bf._open_payment_modal(); pump(root, 4); tl = toplevels(bf)[0]
amt = [w for w in walk(tl) if isinstance(w, tk.Entry)][0]; setv(amt, "200")
find_button(tl, "Post Payment").invoke(); pump(root, 6)
bill2 = raw.bills.find_one(sort=[("created_at", -1)])
check("GUI-BILL-26", "part-paid (200 of 500): status=partial, balance_due=300", bill2["status"] == "partial" and bill2["balance_due"] == 300, f"status={bill2['status']} balance_due={bill2['balance_due']}")
check("GUI-BILL-27", "customer outstanding = 300 after part-payment", cust("Cust0001")["current_balance"] == 300.0, cust("Cust0001")["current_balance"])

# ---------------------------------------------------------- credit limit via UI
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":400.0}})
bf._open_customer_search(); pump(root, 3); tl = toplevels(bf)[0]
[w for w in walk(tl) if isinstance(w, tk.Label) and w.cget("text") == "Anna Adarsh Hostel"][0].master.event_generate("<Button-1>"); pump(root, 3)
setv(row(0)["code"], "101"); bf._on_code_entered(0); setv(row(0)["qty"], "100"); setv(row(0)["rate"], "20"); bf._recalculate_row(0)
bf._open_payment_modal(); pump(root, 4); tl = toplevels(bf)[0]
amt = [w for w in walk(tl) if isinstance(w, tk.Entry)][0]; setv(amt, "0"); clear_dialogs()
find_button(tl, "Post Payment").invoke(); pump(root, 4)
d = last_dialog()
check("GUI-BILL-28", "credit-limit breach shows 'Failed to Save Bill' error", d and d[0]=="showerror" and "credit limit" in d[2].lower(), d)
check("GUI-BILL-29", "form data retained after failed save (cashier can fix)", row(0)["code"].get() != "", row(0)["code"].get())
try: toplevels(bf)[0].destroy()
except Exception: pass
reset_form()

# ---------------------------------------------------------- over-payment & junk amount
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":0.0}})
setv(row(0)["code"], "105"); bf._on_code_entered(0); setv(row(0)["qty"], "1"); setv(row(0)["rate"], "100"); bf._recalculate_row(0)
bf._open_payment_modal(); pump(root, 4); tl = toplevels(bf)[0]
amt = [w for w in walk(tl) if isinstance(w, tk.Entry)][0]; setv(amt, "abc")
find_button(tl, "Post Payment").invoke(); pump(root, 4)
b3 = raw.bills.find_one(sort=[("created_at", -1)])
check("GUI-BILL-30", "non-numeric 'Amount Received' is rejected (not silently treated as full payment)", b3["invoice_no"] == bill2["invoice_no"], f"new bill saved: status={b3['status']} balance_due={b3['balance_due']}")
for _t in toplevels(bf): _t.destroy()
reset_form()
setv(row(0)["code"], "105"); bf._on_code_entered(0); setv(row(0)["qty"], "1"); setv(row(0)["rate"], "100"); bf._recalculate_row(0)
bf._open_payment_modal(); pump(root, 4); tl = toplevels(bf)[0]
amt = [w for w in walk(tl) if isinstance(w, tk.Entry)][0]; setv(amt, "5000"); n0 = raw.bills.count_documents({})
find_button(tl, "Post Payment").invoke(); pump(root, 4)
b4 = raw.bills.find_one(sort=[("created_at", -1)])
check("GUI-BILL-31", "receiving 5000 against a 100 bill is rejected/flagged as over-payment (or booked as advance)", raw.bills.count_documents({}) == n0 or raw.payments.count_documents({"is_advance": True}) > 0, f"bills {n0}->{raw.bills.count_documents({})}; status={b4['status']} balance_due={b4['balance_due']}")
for _t in toplevels(bf): _t.destroy()
reset_form()

# ---------------------------------------------------------- empty bill & park / recall
clear_dialogs(); bf._open_payment_modal(); pump(root, 2)
check("GUI-BILL-32", "saving an empty bill warns 'Empty Bill'", last_dialog() and last_dialog()[1] == "Empty Bill", last_dialog())
setv(row(0)["code"], "104"); bf._on_code_entered(0); setv(row(0)["qty"], "3"); bf._recalculate_row(0)
bf.park_bill(); pump(root, 3)
check("GUI-BILL-33", "park clears form and counts 1 parked bill", bf.parked_bills_count == 1 and row(0)["code"].get() == "", bf.parked_bills_count)
bf._open_parked_modal(); pump(root, 3); tl = toplevels(bf)[0]
card = [w for w in walk(tl) if isinstance(w, tk.Label) and "Total:" in w.cget("text")][0]
card.master.event_generate("<Button-1>"); pump(root, 3)
check("GUI-BILL-34", "recall restores line (Bajji Chilli, qty 3)", row(0)["name"].get() == "Bajji Chilli" and row(0)["qty"].get() == "3", (row(0)["name"].get(), row(0)["qty"].get()))
check("GUI-BILL-35", "parked count drops to 0 after recall", bf.parked_bills_count == 0, bf.parked_bills_count)
reset_form()
setv(row(0)["code"], "104"); bf._on_code_entered(0); bf.park_bill()
finish(root)
