"""Atomic multi-step writes, proven on a REAL single-node replica set (and contrasted with a standalone server).

Starts its own throw-away replica-set mongod (port QA_RS_PORT, default 27098, temp data dir) through the same helper the
packaged application uses. The standalone comparison uses MONGODB_URL (the usual QA server).
"""
import os, sys, json, shutil, tempfile
sys.path.insert(0, os.getcwd())
os.environ.setdefault("PARKED_BILLS_FILE", os.path.join(os.environ.get("QA_SCRATCH", "."), "parked_bills_qa.json"))
from datetime import datetime
from pathlib import Path

from app.config.settings import Settings
from app.database import connection as conn
from app.database.connection import MongoDatabase
from app.database.local_mongod import ensure_local_mongod, stop_local_mongod
from app.models.billing import BillCreate, BillItem
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.models.order import OrderCreate, OrderItem
from app.services.payment_service import PaymentService
from app.services.procurement_service import ProcurementService

RS_PORT = int(os.environ.get("QA_RS_PORT", "27098"))
RS_URL = f"mongodb://127.0.0.1:{RS_PORT}"
STANDALONE_URL = os.environ["MONGODB_URL"]
RESULTS = []


def check(tc, desc, cond, evidence=""):
    RESULTS.append((tc, desc, bool(cond), str(evidence)))
    print(("PASS" if cond else "FAIL"), tc, "-", desc, "|", str(evidence)[:240])


class Boom(RuntimeError):
    pass


def boom(*a, **k):
    raise Boom("simulated failure")


def open_db(url, name):
    db = MongoDatabase(Settings(mongodb_url=url, db_name=name)); db.connect()
    return db


def reset_world(db):
    raw = db.db
    for c in raw.list_collection_names():
        raw[c].drop()
    for c in ("bills", "stock_transactions", "bill_audits", "journal_entries", "payments", "ledger_transactions", "purchase_bills", "orders", "crate_transactions", "grns", "purchase_orders"):
        raw.create_collection(c)                       # collections must exist before a multi-document transaction touches them on older servers
    raw.customers.insert_one({"cust_id": "C1", "name": "Cust", "status": "active", "is_deleted": 0, "current_balance": 100.0, "credit_limit": 0.0, "payment_terms_days": 30})
    raw.items.insert_one({"item_id": "I1", "item_alias": "101", "name": "Apple", "unit": "kg", "status": "active", "is_deleted": 0, "stock": 100.0})
    raw.items.insert_one({"item_id": "I2", "item_alias": "102", "name": "Pear", "unit": "kg", "status": "active", "is_deleted": 0, "stock": 100.0})
    raw.suppliers.insert_one({"supplier_id": "S1", "name": "Sup", "status": "active", "is_deleted": 0, "current_balance": 0.0, "tds_applicable": True, "tds_rate": 2.0})


def snap(db):
    raw = db.db
    return {
        "bills": raw.bills.count_documents({}), "stock_txns": raw.stock_transactions.count_documents({}), "audits": raw.bill_audits.count_documents({}),
        "journals": raw.journal_entries.count_documents({}), "payments": raw.payments.count_documents({}), "purchase_bills": raw.purchase_bills.count_documents({}),
        "grns": raw.grns.count_documents({}),
        "stock_I1": raw.items.find_one({"item_id": "I1"})["stock"], "stock_I2": raw.items.find_one({"item_id": "I2"})["stock"],
        "cust_balance": raw.customers.find_one({"cust_id": "C1"})["current_balance"],
        "supp_balance": raw.suppliers.find_one({"supplier_id": "S1"})["current_balance"],
        "orders": [(o["order_id"], o["status"]) for o in raw.orders.find({})],
        "bill_status": sorted((b["invoice_no"], b["status"]) for b in raw.bills.find({})),
    }


def bill(qty=5, received=None):
    it = BillItem(item_id="I1", name="Apple", qty=qty, unit="kg", rate=20.0, amount=qty * 20.0)
    return BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="Cust", items=[it],
                      total_amount=qty * 20.0, balance_due=qty * 20.0, created_by="qa", amount_received=received)


# --------------------------------------------------------------------------------------------- server
stop_local_mongod(RS_URL)
tmp = Path(tempfile.mkdtemp(prefix="billdesk_rs_"))
state = ensure_local_mongod(RS_URL, db_dir=tmp / "db", log_file=tmp / "mongod.log", replica_set="rs0")
check("TX-00", "the helper starts a mongod as a single-node replica set and elects a primary", state == "started", state)
rs = open_db(RS_URL, "sv_billing_qa_tx")
sa = open_db(STANDALONE_URL, "sv_billing_qa_tx")
check("TX-01", "replica-set connection reports transaction support; standalone does not", rs.supports_transactions and not sa.supports_transactions, (rs.supports_transactions, sa.supports_transactions))
check("TX-02", "starting again is a no-op ('running')", ensure_local_mongod(RS_URL, db_dir=tmp / "db", log_file=tmp / "mongod.log", replica_set="rs0") == "running")


# --------------------------------------------------------------------------------------------- scenarios
def scenario(name, desc, setup, act, patch_target):
    """Run the same failing operation on both servers. Replica set: nothing changes. Standalone: record what leaked."""
    out = {}
    for label, db in (("rs", rs), ("standalone", sa)):
        reset_world(db)
        ctx = setup(db)
        before = snap(db)
        restore = patch_target(db, ctx)
        try:
            act(db, ctx)
            raised = False
        except Boom:
            raised = True
        finally:
            restore()
        out[label] = (raised, before, snap(db))
    r_raised, r_before, r_after = out["rs"]
    s_raised, s_before, s_after = out["standalone"]
    check(f"TX-{name}-a", f"{desc}: on a replica set the failure leaves NO trace (all-or-nothing)", r_raised and r_before == r_after,
          {k: (r_before[k], r_after[k]) for k in r_before if r_before[k] != r_after[k]} or "unchanged")
    leaked = {k: (s_before[k], s_after[k]) for k in s_before if s_before[k] != s_after[k]}
    check(f"TX-{name}-b", f"{desc}: (contrast) a standalone server keeps the half-finished work", s_raised and bool(leaked), leaked or "nothing leaked")


def patcher(obj_getter, attr, repl=boom):
    def apply(db, ctx):
        obj = obj_getter(ctx)
        old = getattr(obj, attr)
        setattr(obj, attr, repl)
        return lambda: setattr(obj, attr, old)
    return apply


svc = {}
def billing(db): return svc.setdefault(("b", id(db)), BillingService(db))


scenario("S1", "create_bill failing while posting to the ledger",
         lambda db: billing(db), lambda db, b: b.create_bill(bill()), patcher(lambda b: b.ledger, "post_sale"))
scenario("S2", "create_bill failing while recording the counter payment",
         lambda db: billing(db), lambda db, b: b.create_bill(bill(received=50.0)), patcher(lambda b: b.payment_svc, "record_customer_payment"))


def setup_void(db):
    b = billing(db); b.create_bill(bill(received=20.0)); return b
scenario("S3", "void_bill failing while reversing the ledger entries",
         setup_void, lambda db, b: b.void_bill(db.db.bills.find_one({})["invoice_no"], "qa"), patcher(lambda b: b.ledger, "reverse_entries"))


def setup_pay(db):
    b = billing(db); b.create_bill(bill()); return PaymentService(db)
scenario("S4", "record_customer_payment failing while posting the receipt",
         setup_pay, lambda db, p: p.record_customer_payment("C1", 30.0, invoice_no=db.db.bills.find_one({})["invoice_no"]), patcher(lambda p: p.ledger, "post_receipt"))
scenario("S5", "create_purchase_bill failing while posting to the ledger",
         lambda db: ProcurementService(db),
         lambda db, p: p.create_purchase_bill("S1", "B1", [{"item_id": "I1", "name": "Apple", "qty": 10.0, "rate": 10.0}]),
         patcher(lambda p: p.ledger, "post_purchase_bill"))


def setup_grn(db):
    p = ProcurementService(db)
    po = p.create_purchase_order("S1", [{"item_id": "I1", "name": "Apple", "qty": 10.0, "rate": 10.0}, {"item_id": "I2", "name": "Pear", "qty": 10.0, "rate": 10.0}])
    return p, po
calls = {"n": 0}
def flaky_txn(*a, **k):
    calls["n"] += 1
    if calls["n"] % 2 == 0:
        raise Boom("second item fails")
    return orig_txn(*a, **k)
orig_txn = None
def grn_patch(db, ctx):
    global orig_txn
    p, _ = ctx
    orig_txn = p.inv_repo.record_stock_txn; calls["n"] = 0
    p.inv_repo.record_stock_txn = flaky_txn
    return lambda: setattr(p.inv_repo, "record_stock_txn", orig_txn)
scenario("S6", "a goods receipt failing on its second line",
         setup_grn, lambda db, ctx: ctx[0].record_grn(ctx[1]["po_id"], [{"item_id": "I1", "name": "Apple", "qty": 5.0}, {"item_id": "I2", "name": "Pear", "qty": 5.0}]), grn_patch)


def setup_order(db):
    o = OrderService(db)
    created = o.create_order(OrderCreate(customer_id="C1", customer_name="Cust", created_by="qa", items=[OrderItem(item_id="I1", name="Apple", qty=4.0, unit="kg", rate=20.0, amount=80.0)]))
    return o, created
scenario("S7", "order -> bill conversion failing after the invoice was created",
         setup_order, lambda db, ctx: ctx[0].convert_to_bill(ctx[1]["order_id"], "qa"), patcher(lambda c: c[0].bill_repo, "update_one"))

# --------------------------------------------------------------------------------------------- success path & hygiene
reset_world(rs)
b = BillingService(rs)
saved = b.create_bill(bill(qty=10, received=60.0))
s = snap(rs)
check("TX-10", "a successful bill commits everything together (bill, stock, balance, ledger, payment)",
      s["bills"] == 1 and s["stock_I1"] == 90.0 and s["cust_balance"] == 100.0 + 200.0 - 60.0 and s["journals"] >= 2 and s["payments"] == 1, s)
other = open_db(RS_URL, "sv_billing_qa_tx")                    # a different connection sees the committed data
check("TX-11", "committed data is visible to another connection", other.db.bills.count_documents({}) == 1)
check("TX-12", "no transaction is left open after success or failure", conn._active_session.get() is None)
o = OrderService(rs)
od = o.create_order(OrderCreate(customer_id="C1", customer_name="Cust", created_by="qa", items=[OrderItem(item_id="I1", name="Apple", qty=2.0, unit="kg", rate=20.0, amount=40.0)]))
res = o.convert_to_bill(od["order_id"], "qa")
check("TX-13", "nested transactions join the outer one (order conversion = create_bill inside convert_to_bill)",
      rs.db.orders.find_one({"order_id": od["order_id"]})["status"] == "billed" and rs.db.bills.count_documents({"invoice_no": res["invoice_no"]}) == 1)
try:
    with rs.transaction():
        rs.collection("bills").insert_one({"invoice_no": "X-ROLLBACK", "status": "unpaid", "is_deleted": 0})
        raise Boom("rollback me")
except Boom:
    pass
check("TX-14", "a bare `with db.transaction()` block rolls back on any exception", rs.db.bills.count_documents({"invoice_no": "X-ROLLBACK"}) == 0)
with sa.transaction() as sess:
    check("TX-15", "on a standalone server transaction() is a harmless no-op", sess is None)

stop_local_mongod(RS_URL)
shutil.rmtree(tmp, ignore_errors=True)
fails = [r for r in RESULTS if not r[2]]
print(f"\nTOTAL {len(RESULTS)} PASS {len(RESULTS) - len(fails)} FAIL {len(fails)}")
if os.environ.get("QA_OUT"):
    json.dump(RESULTS, open(os.environ["QA_OUT"], "w"), indent=1)
