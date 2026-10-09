"""Real-MongoDB checks for the index set and the integrity service (the in-memory mock cannot prove either)."""
import os, sys, json
sys.path.insert(0, os.getcwd())
from datetime import datetime
from app.config.settings import settings
from app.database.connection import MongoDatabase
from app.models.billing import BillCreate, BillItem
from app.services.billing_service import BillingService
from app.services.integrity_service import IntegrityService
from app.services.payment_service import PaymentService
from app.services.ledger_service import LedgerService

assert "qa" in settings.db_name, "refusing to run against a non-QA database"
db = MongoDatabase(settings); db.connect()
raw = db.db
RESULTS = []


def check(tc, desc, cond, evidence=""):
    RESULTS.append((tc, desc, bool(cond), str(evidence)))
    print(("PASS" if cond else "FAIL"), tc, "-", desc, "|", str(evidence)[:260])


def plan(coll, q):
    w = raw[coll].find(q).explain()["queryPlanner"]["winningPlan"]
    while "inputStage" in w:
        w = w["inputStage"]
    return w.get("stage"), w.get("indexName")


# ---- start from an empty database: indexes must appear even where the collection does not exist yet
for c in raw.list_collection_names():
    raw[c].drop()
db.ensure_indexes()
names = lambda c: {i["name"] for i in raw[c].list_indexes()}
check("IDX-01", "journal_entries (created on demand) gets the (reference, source_type) index", "reference_1_source_type_1" in names("journal_entries"), names("journal_entries"))
db.ensure_indexes()                                                     # idempotent
check("IDX-02", "ensure_indexes is idempotent", "reference_1_source_type_1" in names("journal_entries"))

# ---- real activity so the planner has something to plan over
raw.customers.insert_one({"cust_id": "C1", "name": "Real Customer", "status": "active", "is_deleted": 0, "current_balance": 0.0, "credit_limit": 0.0, "payment_terms_days": 30})
raw.items.insert_one({"item_id": "I1", "item_alias": "101", "name": "Apple", "unit": "kg", "status": "active", "is_deleted": 0, "stock": 1000.0})
db.ensure_indexes()
bs, pay = BillingService(db), PaymentService(db)
for i in range(60):
    q = 1 + i % 5
    it = BillItem(item_id="I1", name="Apple", qty=q, unit="kg", rate=20.0, amount=q * 20.0)
    b = bs.create_bill(BillCreate(invoice_date=datetime.now().strftime("%Y-%m-%d"), customer_id="C1", customer_name="Real Customer", items=[it],
                                  total_amount=q * 20.0, balance_due=q * 20.0, created_by="qa"))
    if i % 3 == 0:
        pay.record_customer_payment("C1", 10.0, invoice_no=b["invoice_no"])
db.ensure_indexes()
check("IDX-03", "idempotency lookup uses the journal index", plan("journal_entries", {"reference": "X", "source_type": "sale"})[0] == "IXSCAN", plan("journal_entries", {"reference": "X", "source_type": "sale"}))
check("IDX-04", "open bills per customer use the bills index", plan("bills", {"customer_id": "C1", "status": {"$in": ["unpaid", "partial"]}})[0] == "IXSCAN", plan("bills", {"customer_id": "C1", "status": {"$in": ["unpaid", "partial"]}}))
check("IDX-05", "payments by party use an index", plan("payments", {"party_id": "C1"})[0] == "IXSCAN", plan("payments", {"party_id": "C1"}))

# ---- integrity on real Mongo
rep = IntegrityService(db).run_all()
bad = [(c["id"], c["status"], c["summary"]) for c in rep["checks"] if c["status"] in ("warn", "fail")]
check("INT-01", "freshly created, correctly posted data has no warnings or failures", not bad, bad)
check("INT-02", "all checks ran (none crashed)", len(rep["checks"]) == len(IntegrityService.CHECKS) and not any("the check itself failed" in c["summary"] for c in rep["checks"]))
before = {c: raw[c].estimated_document_count() for c in raw.list_collection_names()}
IntegrityService(db).run_all()
check("INT-03", "running the checks writes nothing", before == {c: raw[c].estimated_document_count() for c in raw.list_collection_names()})

# ---- corrupt the data on purpose; each corruption must be caught on a real database
b0 = raw.bills.find_one({})
raw.bills.update_one({"_id": b0["_id"]}, {"$set": {"total_amount": 1.0}})
raw.journal_entries.delete_one({"source_type": "receipt"})
raw.customers.update_one({"cust_id": "C1"}, {"$inc": {"current_balance": 777.0}})
st = {c["id"]: c["status"] for c in IntegrityService(db).run_all()["checks"]}
check("INT-04", "tampered bill total -> bill_arithmetic fails", st["bill_arithmetic"] == "fail", st["bill_arithmetic"])
check("INT-05", "a payment missing from the ledger -> ledger_coverage warns", st["ledger_coverage"] == "warn", st["ledger_coverage"])
check("INT-06", "a drifted customer balance -> customer_balances and ar_vs_customers warn", st["customer_balances"] == "warn" and st["ar_vs_customers"] == "warn", (st["customer_balances"], st["ar_vs_customers"]))

fails = [r for r in RESULTS if not r[2]]
print(f"\nTOTAL {len(RESULTS)} PASS {len(RESULTS) - len(fails)} FAIL {len(fails)}")
if os.environ.get("QA_OUT"):
    json.dump(RESULTS, open(os.environ["QA_OUT"], "w"), indent=1)
