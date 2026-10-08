"""Service-layer QA against a REAL MongoDB (not the in-memory mock).
Run with MONGODB_URL / DB_NAME pointing at a disposable DB.
"""
import sys, os, traceback
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.getcwd())
from app.config.settings import settings
from app.database.connection import MongoDatabase
from app.models.billing import BillCreate, BillItem
from app.models.order import OrderCreate, OrderItem
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.inventory_service import InventoryService
from app.services.procurement_service import ProcurementService
from app.services.session_service import SessionService
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService

assert "qa" in settings.db_name, "refusing to run against a non-QA database"
db = MongoDatabase(settings); db.connect()
raw = db.db
RESULTS = []

def check(tc, desc, cond, evidence=""):
    RESULTS.append((tc, desc, bool(cond), str(evidence)))
    print(("PASS" if cond else "FAIL"), tc, "-", desc, "|", evidence)

def expect_err(tc, desc, fn, contains=""):
    try:
        fn()
        check(tc, desc, False, "no exception raised")
    except Exception as e:
        check(tc, desc, contains.lower() in str(e).lower(), f"{type(e).__name__}: {e}")

def reset():
    for c in ["bills","orders","payments","ledger_transactions","journal_entries","stock_transactions","bill_audits",
              "crate_transactions","waste_logs","purchase_orders","grns","purchase_bills","ap_payments","cashier_sessions","sessions","fixed_prices"]:
        raw[c].delete_many({})
    raw.items.update_many({}, {"$set": {"stock": 100.0}})
    raw.customers.update_many({}, {"$set": {"current_balance": 0.0, "crate_balances": []}})
    raw.suppliers.update_many({}, {"$set": {"current_balance": 0.0}})

def item(i): return raw.items.find_one({"item_id": i})
def cust(c): return raw.customers.find_one({"cust_id": c})

def mk_bill(cust_id="Cust0001", name="Anna Adarsh Hostel", lines=None, extra=None, user="admin"):
    lines = lines or [("FRU0001", "101", "Apple", 10, 20.0)]
    items = [BillItem(item_id=i, item_alias=a, name=n, qty=q, unit="kg", rate=r, amount=q*r) for i,a,n,q,r in lines]
    total = sum(x.amount for x in items)
    kw = dict(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id=cust_id, customer_name=name,
              items=items, total_amount=total, balance_due=total, created_by=user)
    kw.update(extra or {})
    return BillCreate(**kw)

bs, os_, ps, inv, pr, ss, ls = (BillingService(db), OrderService(db), PaymentService(db), InventoryService(db),
                               ProcurementService(db), SessionService(db), LedgerService(db))

# ---------------------------------------------------------------- BILLING
reset()
b = bs.create_bill(mk_bill())
check("SVC-BILL-01", "create bill stores doc with invoice YYYYMMDD-0001", b["invoice_no"].endswith("-0001") and len(b["invoice_no"]) == 13, b["invoice_no"])
check("SVC-BILL-02", "stock decremented 100 -> 90", item("FRU0001")["stock"] == 90.0, item("FRU0001")["stock"])
check("SVC-BILL-03", "customer balance +200", cust("Cust0001")["current_balance"] == 200.0, cust("Cust0001")["current_balance"])
check("SVC-BILL-04", "stock_transactions row type=sale qty=-10", raw.stock_transactions.count_documents({"type":"sale","qty":-10.0,"reference_id":b["invoice_no"]}) == 1)
check("SVC-BILL-05", "bill_audits CREATE row written", raw.bill_audits.count_documents({"invoice_no":b["invoice_no"],"action":"CREATE"}) == 1)
check("SVC-BILL-06", "due_date = invoice_date + 30d", b["due_date"] is not None and (b["due_date"].date() - datetime.now().date()).days in (29,30,31), b["due_date"])
b2 = bs.create_bill(mk_bill())
check("SVC-BILL-07", "second invoice increments sequence -0002", b2["invoice_no"].endswith("-0002"), b2["invoice_no"])
expect_err("SVC-BILL-08", "duplicate invoice_no rejected", lambda: bs.create_bill(mk_bill(extra={"invoice_no": b["invoice_no"]})), "already exists")
expect_err("SVC-BILL-09", "qty=0 rejected", lambda: bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",0,20.0)])), "greater than zero")
expect_err("SVC-BILL-10", "negative qty rejected", lambda: bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",-5,20.0)])), "greater than zero")
expect_err("SVC-BILL-11", "negative rate rejected", lambda: bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",1,-2.0)])), "negative")
expect_err("SVC-BILL-12", "empty item list rejected", lambda: bs.create_bill(mk_bill().model_copy(update={"items": []})), "at least one")
expect_err("SVC-BILL-13", "unknown customer rejected", lambda: bs.create_bill(mk_bill(cust_id="NOPE")), "not found")
# credit limit: Cust0001 limit 5000, balance now 400
expect_err("SVC-BILL-14", "credit limit exceeded blocked (400+5000>5000)", lambda: bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",250,20.0)])), "credit limit")
before = (item("FRU0001")["stock"], cust("Cust0001")["current_balance"])
try: bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",250,20.0)]))
except Exception: pass
check("SVC-BILL-15", "failed credit check leaves stock/balance untouched", before == (item("FRU0001")["stock"], cust("Cust0001")["current_balance"]), before)
exact = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",230,20.0)]))  # 400+4600 = 5000 exactly
check("SVC-BILL-16", "bill exactly AT credit limit is allowed (boundary)", exact is not None, exact["total_amount"])
# walk-in cash customer
raw.customers.update_one({"cust_id":"COUNTER"},{"$set":{"credit_limit":0.0}})
c1 = bs.create_bill(mk_bill(cust_id="CASH", name="Cash", lines=[("VEG0001","102","Avarai",5,20.0)]))
check("SVC-BILL-17", "CASH customer: no customer balance change, due_date None", c1["due_date"] is None, c1["due_date"])
# stock oversell
raw.items.update_one({"item_id":"VEG0002"},{"$set":{"stock":3.0}})
try:
    ov = bs.create_bill(mk_bill(cust_id="CASH", name="Cash", lines=[("VEG0002","104","Bajji Chilli",50,20.0)]))
    check("SVC-BILL-18", "selling 50 when only 3 in stock is blocked or flagged on the bill", bool(ov.get("stock_warnings")), f"stock_warnings={ov.get('stock_warnings')}")
except Exception as e:
    check("SVC-BILL-18", "selling 50 when only 3 in stock is blocked or flagged on the bill", True, e)

expect_err("SVC-BILL-19", "caller-supplied total that disagrees with the lines is rejected (total_amount=1 for a Rs10 line)",
           lambda: bs.create_bill(mk_bill(cust_id="CASH", name="Cash", lines=[("FRU0002","105","Banana Green",1,10.0)]).model_copy(update={"total_amount": 1.0, "balance_due": 1.0})), "does not match")
mism = mk_bill(cust_id="CASH", name="Cash", lines=[("FRU0002","105","Banana Green",2,10.0)]).model_copy(update={"items":[BillItem(item_id="FRU0002",name="Banana Green",qty=2,unit="kg",rate=10.0,amount=999.0)]})
m = bs.create_bill(mism)
check("SVC-BILL-20", "line amount is recomputed as qty*rate (amount=999 passed for 2x10 -> 20.00)", m["items"][0]["amount"] == 20.0, f"stored line amount={m['items'][0]['amount']}")

# ---------------------------------------------------------------- VOID
reset()
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":0.0}})
vb = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",10,20.0)], extra={"crates_issued":5,"crates_returned":2,"crate_item_id":"CRATE-PLASTIC"}))
check("SVC-VOID-00", "crate txn recorded on bill", raw.crate_transactions.count_documents({"reference_id":vb["invoice_no"]}) == 1)
check("SVC-VOID-00b", "customer.crate_balances updated (+3 outstanding)", any(abs(float(x.get('balance', x.get('qty', 0)))) == 3 for x in (cust("Cust0001").get("crate_balances") or [])), cust("Cust0001").get("crate_balances"))
r = bs.void_bill(vb["invoice_no"], "admin")
check("SVC-VOID-01", "void sets status=void, balance_due=0", raw.bills.find_one({"invoice_no":vb["invoice_no"]})["status"]=="void")
check("SVC-VOID-02", "void restores stock 100", item("FRU0001")["stock"] == 100.0, item("FRU0001")["stock"])
check("SVC-VOID-03", "void restores customer balance to 0", cust("Cust0001")["current_balance"] == 0.0, cust("Cust0001")["current_balance"])
check("SVC-VOID-04", "VOID audit row written", raw.bill_audits.count_documents({"invoice_no":vb["invoice_no"],"action":"VOID"}) == 1)
check("SVC-VOID-05", "void reverses crate balance (TC-BILL-06)", not any(float(x.get('balance', x.get('qty',0))) for x in (cust("Cust0001").get("crate_balances") or [])) , cust("Cust0001").get("crate_balances"))
check("SVC-VOID-06", "void posts contra journal entry (EPIC-03 Task 3.2.3)", raw.journal_entries.count_documents({}) > 0, f"journal_entries={raw.journal_entries.count_documents({})}")
expect_err("SVC-VOID-07", "double void rejected", lambda: bs.void_bill(vb["invoice_no"]), "already voided")
expect_err("SVC-VOID-08", "void unknown invoice rejected", lambda: bs.void_bill("19990101-0001"), "not found")
# void AFTER partial payment
reset()
pb = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",10,20.0)]))   # 200
ps.record_customer_payment("Cust0001", 120.0, invoice_no=pb["invoice_no"])
check("SVC-VOID-09a", "pre-void: balance=80 after paying 120", cust("Cust0001")["current_balance"] == 80.0, cust("Cust0001")["current_balance"])
bs.void_bill(pb["invoice_no"])
pay9 = raw.payments.find_one({"party_id": "Cust0001"})
check("SVC-VOID-09", "void of part-paid bill: customer ends with 120 credit (balance -120) and the payment is released as unallocated credit", cust("Cust0001")["current_balance"] == -120.0 and pay9["allocation_status"] == "unallocated" and pay9["is_advance"] and pay9["allocations"] == [], f"balance={cust('Cust0001')['current_balance']} payment={pay9['allocation_status']} alloc={pay9['allocations']}")

# ---------------------------------------------------------------- PAYMENTS
reset()
b1 = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",10,20.0)]))      # 200
b2 = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",5,20.0)]))       # 100
p = ps.record_customer_payment("Cust0001", 50.0, invoice_no=b1["invoice_no"])
bb = raw.bills.find_one({"invoice_no":b1["invoice_no"]})
check("SVC-PAY-01", "partial pay: balance_due 150, status partial", bb["balance_due"]==150.0 and bb["status"]=="partial", (bb["balance_due"], bb["status"]))
check("SVC-PAY-02", "customer balance 300 -> 250", cust("Cust0001")["current_balance"] == 250.0, cust("Cust0001")["current_balance"])
check("SVC-PAY-03", "ledger_transactions credit row written", raw.ledger_transactions.count_documents({"type":"credit","amount":50.0}) == 1)
expect_err("SVC-PAY-04", "over-allocation rejected", lambda: ps.record_customer_payment("Cust0001", 999.0, invoice_no=b1["invoice_no"]), "exceeds")
expect_err("SVC-PAY-05", "zero payment rejected", lambda: ps.record_customer_payment("Cust0001", 0), "greater than zero")
expect_err("SVC-PAY-06", "negative payment rejected", lambda: ps.record_customer_payment("Cust0001", -5), "greater than zero")
expect_err("SVC-PAY-07", "unknown customer rejected", lambda: ps.record_customer_payment("NOPE", 5), "not found")
p = ps.record_customer_payment("Cust0001", 150.0, invoice_no=b1["invoice_no"])
check("SVC-PAY-08", "paying exact remainder -> status paid, due 0", raw.bills.find_one({"invoice_no":b1["invoice_no"]})["status"]=="paid")
# FIFO: no invoice -> goes to b2 (100). pay 130 => 100 alloc + 30 advance
p = ps.record_customer_payment("Cust0001", 130.0)
check("SVC-PAY-09", "FIFO alloc pays b2 fully, remainder is advance", p["is_advance"] and p["allocation_status"]=="partial" and p["allocations"][0]["amount"]==100.0, (p["allocation_status"], p["allocations"], p["is_advance"]))
check("SVC-PAY-10", "customer balance goes negative (-30) = advance credit", cust("Cust0001")["current_balance"] == -30.0, cust("Cust0001")["current_balance"])
# pay-all float rounding
reset()
fb = bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",3,33.33)]))        # 99.99
ps.record_customer_payment("Cust0001", 33.33, invoice_no=fb["invoice_no"])
ps.record_customer_payment("Cust0001", 33.33, invoice_no=fb["invoice_no"])
ps.record_customer_payment("Cust0001", 33.33, invoice_no=fb["invoice_no"])
bb = raw.bills.find_one({"invoice_no":fb["invoice_no"]})
check("SVC-PAY-11", "3 x 33.33 against 99.99 settles to paid (float rounding)", bb["status"]=="paid", (bb["status"], repr(bb["balance_due"])))
# payment on void bill
vb = bs.create_bill(mk_bill()); bs.void_bill(vb["invoice_no"])
expect_err("SVC-PAY-12", "payment against a VOID invoice rejected", lambda: ps.record_customer_payment("Cust0001", 10.0, invoice_no=vb["invoice_no"]), "")
expect_err("SVC-PAY-13", "payment against another customer's invoice rejected", lambda: ps.record_customer_payment("COUNTER", 10.0, invoice_no=fb["invoice_no"]), "")
check("SVC-PAY-14", "payment posts journal entry (EPIC-07 Task 7.1)", raw.journal_entries.count_documents({}) > 0, f"journal_entries={raw.journal_entries.count_documents({})}")

# ---------------------------------------------------------------- ORDERS
reset()
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":300.0}})
o = os_.create_order(OrderCreate(customer_id="Cust0001", customer_name="Anna Adarsh Hostel", created_by="admin",
        items=[OrderItem(item_id="FRU0001", name="Apple", qty=50, unit="kg", rate=20.0, amount=1000.0)]))
check("SVC-ORD-01", "order created pending with total 1000", o["status"]=="pending" and o["total_amount"]==1000.0 and o["order_id"], (o["order_id"], o["status"]))
expect_err("SVC-ORD-02", "empty order rejected", lambda: os_.create_order(OrderCreate(customer_id="Cust0001", customer_name="x", created_by="a", items=[])), "at least one")
expect_err("SVC-ORD-03", "order qty<=0 rejected", lambda: os_.create_order(OrderCreate(customer_id="Cust0001", customer_name="x", created_by="a", items=[OrderItem(item_id="FRU0001",name="A",qty=0,unit="kg",rate=1,amount=0)])), "greater than zero")
try:
    cv = os_.convert_to_bill(o["order_id"], "admin")
    check("SVC-ORD-04", "convert respects customer credit limit (limit 300, order 1000)", False, f"converted anyway -> balance {cust('Cust0001')['current_balance']}")
except Exception as e:
    check("SVC-ORD-04", "convert respects customer credit limit (limit 300, order 1000)", True, e)
bl = raw.bills.find_one({"linked_source_id": o["order_id"]})
if bl is None:                       # limit blocked it (correct) -> lift the limit and convert to exercise the rest
    raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":0.0}}); os_.convert_to_bill(o["order_id"], "admin")
    bl = raw.bills.find_one({"linked_source_id": o["order_id"]})
if bl:
    check("SVC-ORD-05", "converted bill gets CREATE audit row", raw.bill_audits.count_documents({"invoice_no": bl["invoice_no"]}) > 0, "audit rows=%d" % raw.bill_audits.count_documents({"invoice_no": bl["invoice_no"]}))
    check("SVC-ORD-06", "converted bill has invoice_date/due_date consistent with direct bills", bl.get("due_date") is not None, f"due_date={bl.get('due_date')}")
    check("SVC-ORD-07", "order -> billed, linked_bill_ids set", raw.orders.find_one({"order_id":o["order_id"]})["status"]=="billed" and raw.orders.find_one({"order_id":o["order_id"]})["linked_bill_ids"]==[bl["invoice_no"]])
    expect_err("SVC-ORD-08", "re-convert billed order rejected", lambda: os_.convert_to_bill(o["order_id"]), "already billed")
    ob = raw.orders.find_one({"order_id":o["order_id"]})
    os_.update_order(o["order_id"], {"status":"cancelled"})
    expect_err("SVC-ORD-09", "cancelled order cannot be converted", lambda: os_.convert_to_bill(o["order_id"]), "")
o2 = os_.create_order(OrderCreate(customer_id="Cust0001", customer_name="Anna", created_by="admin", status="cancelled",
        items=[OrderItem(item_id="FRU0001", name="Apple", qty=1, unit="kg", rate=1.0, amount=1.0)]))
expect_err("SVC-ORD-10", "cancelled order cannot be converted to bill", lambda: os_.convert_to_bill(o2["order_id"]), "")
o3 = os_.create_order(OrderCreate(customer_id="Cust0001", customer_name="Anna", created_by="admin",
        items=[OrderItem(item_id="VEG0001", name="Avarai", qty=4, unit="kg", rate=20.0, amount=80.0)]))
before = item("VEG0001")["stock"]
pu = os_.convert_to_purchase(o3["order_id"], "SUP001", "Fresh Farm Suppliers", "admin")
check("SVC-ORD-11", "convert_to_purchase: stock +4, supplier balance +78.40 (80 less 2% TDS)", item("VEG0001")["stock"]==before+4 and raw.suppliers.find_one({"supplier_id":"SUP001"})["current_balance"]==78.4, (item("VEG0001")["stock"], raw.suppliers.find_one({"supplier_id":"SUP001"})["current_balance"]))
try:
    os_.convert_to_purchase(o3["order_id"], "SUP001", "Fresh Farm Suppliers", "admin"); check("SVC-ORD-12", "same order cannot be converted to purchase twice", False, "second purchase created -> stock inflated twice")
except ValueError as e:
    check("SVC-ORD-12", "same order cannot be converted to purchase twice", item("VEG0001")["stock"] == before + 4, e)
check("SVC-ORD-13", "supplier TDS applied on order->purchase (supplier tds_applicable)", raw.purchase_bills.find_one({"purchase_id":pu["purchase_id"]}).get("tds_amount",0)>0, "tds_amount=%s" % raw.purchase_bills.find_one({"purchase_id":pu["purchase_id"]}).get("tds_amount"))
m = os_.get_order_matrix()
check("SVC-ORD-14", "order matrix returns rows/customers", "rows" in m and "customers" in m, m)

# ---------------------------------------------------------------- PRICING
reset()
now = datetime.now(timezone.utc)
raw.fixed_prices.insert_one({"customer_id":"Cust0001","item_id":"FRU0001","rate":12.0,"is_active":True,"start_date":now-timedelta(days=5),"end_date":now+timedelta(days=5)})
raw.fixed_prices.insert_one({"customer_id":"Cust0001","item_id":"VEG0001","rate":9.0,"is_active":True,"start_date":now-timedelta(days=15),"end_date":now-timedelta(days=5)})
pr_s = PricingService(db)
check("SVC-PRICE-01", "active fixed price used", pr_s.resolve_rate("Cust0001","FRU0001") == (12.0, True), pr_s.resolve_rate("Cust0001","FRU0001"))
check("SVC-PRICE-02", "expired fixed price ignored -> item default (20.0)", pr_s.resolve_rate("Cust0001","VEG0001", default_rate=20.0)[1] is False, pr_s.resolve_rate("Cust0001","VEG0001", default_rate=20.0))
check("SVC-PRICE-03", "item with only 'default_rate' (seed schema) resolves to 20 w/o caller default", pr_s.resolve_rate("Cust0001","VEG0002")[0] == 20.0, pr_s.resolve_rate("Cust0001","VEG0002"))
check("SVC-PRICE-04", "other customer unaffected by Cust0001 fixed price", pr_s.resolve_rate("COUNTER","FRU0001")[1] is False)

# ---------------------------------------------------------------- INVENTORY
reset()
a = inv.adjust_stock("FRU0001", -12.5, "Drying loss", "admin")
check("SVC-INV-01", "adjust -12.5 -> stock 87.5 + txn logged", item("FRU0001")["stock"]==87.5 and raw.stock_transactions.count_documents({"type":"adjustment","qty":-12.5})==1, item("FRU0001")["stock"])
expect_err("SVC-INV-02", "zero adjustment rejected", lambda: inv.adjust_stock("FRU0001", 0, "x"), "zero")
expect_err("SVC-INV-03", "adjustment below zero rejected", lambda: inv.adjust_stock("FRU0001", -500, "x"), "negative")
expect_err("SVC-INV-04", "unknown item rejected", lambda: inv.adjust_stock("NOPE", 1, "x"), "not found")
try:
    inv.adjust_stock("FRU0001", 5, "")
    check("SVC-INV-05", "adjustment requires a non-empty reason (docstring: mandatory reason)", False, "accepted blank reason")
except Exception as e:
    check("SVC-INV-05", "adjustment requires a non-empty reason (docstring: mandatory reason)", True, e)
w = inv.record_waste("FRU0001", 10.0, 25.0, "Rotten", "admin")
check("SVC-INV-06", "waste: amount=250, stock 87.5->77.5, txn type=waste", w["amount"]==250.0 and raw.stock_transactions.count_documents({"type":"waste","qty":-10.0})==1 and item("FRU0001")["stock"]==77.5, (w["amount"], item("FRU0001")["stock"]))
s_before = item("FRU0001")["stock"]
try:
    inv.record_waste("FRU0001", 10000.0, 25.0, "Typo")
    check("SVC-INV-07", "waste larger than on-hand stock rejected", item("FRU0001")["stock"] >= 0, f"stock now {item('FRU0001')['stock']}")
except Exception as e:
    check("SVC-INV-07", "waste larger than on-hand stock rejected", True, e)
expect_err("SVC-INV-08", "waste qty<=0 rejected", lambda: inv.record_waste("FRU0001", 0, 1, "x"), "greater than zero")
try:
    inv.record_waste("FRU0001", 1, -25.0, "neg rate")
    check("SVC-INV-09", "negative waste rate rejected", False, "accepted -> negative loss")
except Exception as e:
    check("SVC-INV-09", "negative waste rate rejected", True, e)

# ---------------------------------------------------------------- PROCUREMENT
reset()
po = pr.create_purchase_order("SUP001", [{"item_id":"FRU0001","name":"Apple","qty":100,"rate":40.0}], user_id="admin")
check("SVC-PROC-01", "PO draft total 4000", po["status"]=="draft" and po["total_amount"]==4000.0, po["status"])
expect_err("SVC-PROC-02", "PO unknown supplier", lambda: pr.create_purchase_order("NOPE", [{"item_id":"x","qty":1,"rate":1}]), "not found")
expect_err("SVC-PROC-03", "PO empty items", lambda: pr.create_purchase_order("SUP001", []), "at least one")
g = pr.record_grn(po["po_id"], [{"item_id":"FRU0001","name":"Apple","qty":100}], "admin")
check("SVC-PROC-04", "GRN: stock +100, PO received", item("FRU0001")["stock"]==200.0 and raw.purchase_orders.find_one({"po_id":po["po_id"]})["status"]=="received", item("FRU0001")["stock"])
try:
    pr.record_grn(po["po_id"], [{"item_id":"FRU0001","name":"Apple","qty":100}], "admin")
    check("SVC-PROC-05", "second GRN against an already-received PO rejected", False, f"stock inflated to {item('FRU0001')['stock']}")
except Exception as e:
    check("SVC-PROC-05", "second GRN against an already-received PO rejected", True, e)
try:
    pr.record_grn(po["po_id"], [{"item_id":"FRU0001","name":"Apple","qty":7777}], "admin")
    check("SVC-PROC-06", "GRN qty greater than PO ordered qty (100) rejected/flagged", False, "accepted 7777 vs ordered 100")
except Exception as e:
    check("SVC-PROC-06", "GRN qty greater than PO ordered qty (100) rejected/flagged", True, e)
pb = pr.create_purchase_bill("SUP001", "SB-1", [{"item_id":"FRU0001","name":"Apple","qty":1000,"rate":50.0}], po["po_id"], g["grn_id"], user_id="admin")
check("SVC-PROC-07", "purchase bill TDS 2% on 50000 = 1000, payable 49000", pb["tds_amount"]==1000.0 and pb["payable_amount"]==49000.0, (pb["tds_amount"], pb["payable_amount"]))
check("SVC-PROC-08", "supplier balance += payable", raw.suppliers.find_one({"supplier_id":"SUP001"})["current_balance"]==49000.0)
check("SVC-PROC-09", "3-way match: purchase bill qty (1000) vs GRN qty (100) flagged", pb["match_status"]!="matched", f"match_status={pb['match_status']}")
ps.record_supplier_payment(pb["purchase_id"], "SUP001", 9000.0, user_id="admin")
check("SVC-PROC-10", "supplier part-pay: due 40000 status partial", raw.purchase_bills.find_one({"purchase_id":pb["purchase_id"]})["balance_due"]==40000.0)
expect_err("SVC-PROC-11", "supplier over-payment rejected", lambda: ps.record_supplier_payment(pb["purchase_id"], "SUP001", 99999.0), "exceeds")
expect_err("SVC-PROC-12", "supplier payment on unknown bill", lambda: ps.record_supplier_payment("NOPE","SUP001",1.0), "not found")
check("SVC-PROC-13", "AP payment posts journal entry", raw.journal_entries.count_documents({}) > 0, f"journal_entries={raw.journal_entries.count_documents({})}")

# ---------------------------------------------------------------- SESSIONS
reset()
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":0.0}})
s = ss.open_session("USER0001","admin",2000.0)
expect_err("SVC-SESS-01", "second open session for same user rejected", lambda: ss.open_session("USER0001","admin",1.0), "already")
bs.create_bill(mk_bill(cust_id="CASH", name="Cash", lines=[("FRU0001","101","Apple",100,35.0)], extra={"amount_received": 3500.0}))      # 3500 cash walk-in, paid in cash
bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",10,100.0)]))                                    # 1000 on CREDIT to Cust0001
ps.record_customer_payment("Cust0001", 500.0, payment_method="Cash", user_id="admin")
exp = ss.compute_expected_cash(s["session_id"])
check("SVC-SESS-02", "expected cash = 2000 + 3500 cash sale + 500 receipt = 6000 (credit bill excluded)", exp == 6000.0, f"expected_cash={exp} (credit bill of 1000 {'included' if exp==7000.0 else 'excluded'})")
c = ss.close_session(s["session_id"], 5950.0)
check("SVC-SESS-03", "close: difference = actual - expected", c["difference"] == 5950.0 - exp and c["status"]=="closed", c["difference"])
expect_err("SVC-SESS-04", "closing a closed session rejected", lambda: ss.close_session(s["session_id"], 1.0), "already closed")
expect_err("SVC-SESS-05", "close unknown session", lambda: ss.close_session("NOPE", 1.0), "not found")
try:
    ss.open_session("USER0002","manager",-100.0)
    check("SVC-SESS-06", "negative opening cash rejected", False, "accepted -100")
except Exception as e:
    check("SVC-SESS-06", "negative opening cash rejected", True, e)

# ---------------------------------------------------------------- LEDGER
reset()
j = ls.post_journal_entry("T1","manual",[{"account_id":"1200","debit":1500.0,"credit":0.0},{"account_id":"4000","debit":0.0,"credit":1500.0}],"admin")
check("SVC-GL-01", "balanced journal posts with state=posted", j["state"]=="posted")
expect_err("SVC-GL-02", "unbalanced journal rejected", lambda: ls.post_journal_entry("T2","manual",[{"account_id":"1200","debit":1500.0},{"account_id":"4000","credit":1200.0}]), "unbalanced")
check("SVC-GL-03", "rejected journal persisted nothing (count==1)", raw.journal_entries.count_documents({})==1)
tb = ls.get_trial_balance()
check("SVC-GL-04", "trial balance balanced", tb["is_balanced"] and tb["total_debit"]==1500.0, tb["total_debit"])
try:
    ls.post_journal_entry("T3","manual",[{"account_id":"1200","debit":-100.0,"credit":0.0},{"account_id":"4000","debit":0.0,"credit":-100.0}])
    check("SVC-GL-05", "negative debit/credit amounts rejected", False, "accepted")
except Exception as e:
    check("SVC-GL-05", "negative debit/credit amounts rejected", True, e)
try:
    ls.post_journal_entry("T4","manual",[])
    check("SVC-GL-06", "empty journal (no lines) rejected", False, "accepted empty journal")
except Exception as e:
    check("SVC-GL-06", "empty journal (no lines) rejected", True, e)
try:
    ls.post_journal_entry("T5","manual",[{"account_id":"1200","debit":10.0,"credit":10.0},{"account_id":"4000","debit":0.0,"credit":0.0}])
    check("SVC-GL-07", "a line with both debit and credit rejected", False, "accepted")
except Exception as e:
    check("SVC-GL-07", "a line with both debit and credit rejected", True, e)
reset()
raw.customers.update_one({"cust_id":"Cust0001"},{"$set":{"credit_limit":0.0}})
bs.create_bill(mk_bill(lines=[("FRU0001","101","Apple",10,20.0)], extra={"commission_amt":10.0,"mandi_fee_amt":5.0,"total_amount":215.0,"balance_due":215.0}))
pl = ls.get_profit_and_loss()
check("SVC-GL-08", "P&L sales includes sale (200)", pl["total_sales"]>=200.0, pl)
check("SVC-GL-09", "sale auto-posts balanced journal (AR Dr / Sales Cr)", raw.journal_entries.count_documents({"source_type":{"$in":["sale","bill","sales"]}})>0, f"journal_entries={raw.journal_entries.count_documents({})}")

# ---------------------------------------------------------------- AUTH
from app.services.auth_service import AuthService
au = AuthService(db)
for u,p,ok in [("admin","admin123",True),("manager","manager123",True),("user","user123",True),("admin","bad",False),("ghost","x",False),("admin-empty-pw","",False)]:
    try: au.login(u.replace("-empty-pw",""),p); good = True
    except ValueError: good = False
    check("SVC-AUTH-%s-%s" % (u, "ok" if ok else "bad"), f"login {u!r}/{p!r} -> {'success' if ok else 'rejected'}", good == ok)
check("SVC-AUTH-audit", "login writes user_activity_audits", raw.user_activity_audits.count_documents({"action":"login"})>=3)
raw.users.update_one({"username":"user"},{"$set":{"status":"inactive"}})
try: au.login("user","user123"); inactive_ok=False
except ValueError: inactive_ok=True
raw.users.update_one({"username":"user"},{"$set":{"status":"active"}})
check("SVC-AUTH-inactive", "inactive user cannot log in", inactive_ok)
check("SVC-AUTH-perm-manager", "manager role has non-empty menu permissions (role_permissions seeded)", len(au.permissions_for(au.login("manager","manager123")))>0, au.permissions_for(au.login("manager","manager123")))

print()
fails = [r for r in RESULTS if not r[2]]
print(f"TOTAL {len(RESULTS)}  PASS {len(RESULTS)-len(fails)}  FAIL {len(fails)}")
for r in fails: print("  FAIL", r[0], "-", r[1], "|", r[3])
import json
json.dump(RESULTS, open(os.environ.get("QA_OUT","qa_results.json"),"w"), indent=1)
