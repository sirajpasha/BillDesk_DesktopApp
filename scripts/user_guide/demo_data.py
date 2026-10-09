"""Fictional demo data for the user-guide screenshots (never production data)."""
import os, sys, random
sys.path.insert(0, os.getcwd())
from datetime import datetime, timedelta, timezone
from app.config.settings import settings
assert "demo" in settings.db_name
from app.database.connection import MongoDatabase
from app.models.billing import BillCreate, BillItem
from app.models.order import OrderCreate, OrderItem
from app.services.billing_service import BillingService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.procurement_service import ProcurementService
from app.services.inventory_service import InventoryService
from app.services.ledger_service import LedgerService
from app.services.session_service import SessionService
from app.services.master_service import MasterService

random.seed(7)
db = MongoDatabase(settings); db.connect(); db.ensure_indexes(); raw = db.db
now = datetime.now()

# customers (fictional)
for cid, name, phone, addr, limit in [
    ("CUST101", "Green Leaf Restaurant", "9840011122", "12, Anna Salai, Chennai - 600002", 50000.0),
    ("CUST102", "Sri Lakshmi Caterers", "9840033344", "45, Mount Road, Chennai - 600006", 80000.0),
    ("CUST103", "Hotel Annapoorna", "9841155566", "7, Gandhi Street, T. Nagar, Chennai - 600017", 100000.0),
    ("CUST104", "Sunrise Hostel Mess", "9444466677", "88, OMR, Sholinganallur, Chennai - 600119", 40000.0),
]:
    raw.customers.update_one({"cust_id": cid}, {"$set": {"cust_id": cid, "name": name, "bill_to_name": name, "address": addr, "contact_person_phone": phone,
        "bill_to_phone": phone, "company_id": "Company0001", "credit_limit": limit, "payment_terms_days": 15, "status": "active", "is_deleted": 0,
        "current_balance": 0.0, "crate_balances": []}}, upsert=True)
raw.customers.update_many({"cust_id": {"$in": ["Cust0001", "COUNTER"]}}, {"$set": {"current_balance": 0.0, "credit_limit": 0.0}})

for alias, iid, name, cat in (("106", "VEG0101", "Beans", "Vegetables"), ("107", "VEG0102", "Beetroot", "Vegetables"), ("111", "VEG0103", "Tomato", "Vegetables"),
                              ("112", "VEG0104", "Onion", "Vegetables"), ("113", "VEG0105", "Potato", "Vegetables")):
    raw.items.update_one({"item_id": iid}, {"$set": {"item_id": iid, "item_alias": alias, "name": name, "unit": "Kg", "category": cat, "status": "active", "is_deleted": 0, "stock": 0.0}}, upsert=True)
raw.items.update_many({"item_alias": {"$in": ["101", "102", "104", "105"]}}, {"$set": {"unit": "Kg"}})
aliases = {"101": 160.0, "102": 45.0, "104": 55.0, "105": 40.0, "106": 60.0, "107": 35.0, "111": 30.0, "112": 28.0}
items = {a: raw.items.find_one({"item_alias": a}) for a in aliases}

# opening balances: capital in cash
LedgerService(db).post_journal_entry("OPENING-1", "manual", [{"account_id": "1000", "debit": 50000.0, "credit": 0.0}, {"account_id": "3000", "debit": 0.0, "credit": 50000.0}], "admin")

# purchases first so there is stock and a cost basis
proc = ProcurementService(db); ms = MasterService(db)
raw.suppliers.update_one({"supplier_id": "SUP001"}, {"$set": {"name": "Fresh Farm Suppliers", "tds_applicable": True, "tds_rate": 1.0, "tds_section": "194C", "current_balance": 0.0, "status": "active", "is_deleted": 0}})
lines = [{"item_id": items[a]["item_id"], "name": items[a]["name"], "qty": q, "unit": "kg", "rate": r}
         for a, q, r in (("101", 300.0, 130.0), ("102", 300.0, 36.0), ("104", 250.0, 44.0), ("105", 300.0, 32.0), ("106", 250.0, 48.0), ("107", 300.0, 26.0), ("111", 400.0, 22.0), ("112", 500.0, 21.0))]
po = proc.create_purchase_order("SUP001", lines, user_id="admin")
grn = proc.record_grn(po["po_id"], [{"item_id": l["item_id"], "name": l["name"], "qty": l["qty"]} for l in lines], "admin")
pb = proc.create_purchase_bill("SUP001", "FF-2291", lines, po["po_id"], grn["grn_id"], user_id="admin")
PaymentService(db).record_supplier_payment(pb["purchase_id"], "SUP001", 40000.0, payment_method="NEFT", reference_no="UTR8841", user_id="admin")

# a fixed contract price
ms.save_fixed_price("CUST103", items["101"]["item_id"], 150.0, datetime.now(timezone.utc) - timedelta(days=30), datetime.now(timezone.utc) + timedelta(days=60), "admin")

# sales over the last 10 days
bs = BillingService(db); pay = PaymentService(db)
custs = [("CUST101", "Green Leaf Restaurant"), ("CUST102", "Sri Lakshmi Caterers"), ("CUST103", "Hotel Annapoorna"), ("CUST104", "Sunrise Hostel Mess")]
made = []
for day in range(9, -1, -1):
    d = now - timedelta(days=day)
    for k in range(3 if day < 3 else 2):
        cid, cname = custs[(day + k) % 4]
        picks = random.sample(list(aliases), random.randint(4, 8))
        bl = []
        for a in picks:
            q = float(random.choice([2, 3, 5, 8, 10, 12, 15, 20, 25]))
            bl.append(BillItem(item_id=items[a]["item_id"], item_alias=a, name=items[a]["name"], qty=q, unit="kg", rate=aliases[a], amount=round(q * aliases[a], 2)))
        total = round(sum(x.amount for x in bl), 2)
        recv = None
        r = random.random()
        if r < 0.45: recv = total
        elif r < 0.6: recv = round(total / 2, 2)
        b = bs.create_bill(BillCreate(invoice_date=d.strftime("%Y-%m-%d"), customer_id=cid, customer_name=cname, company_id="Company0001", items=bl,
                                      total_amount=total, balance_due=total, created_by="admin", amount_received=recv, payment_method=random.choice(["Cash", "UPI"]) if recv else "Cash"))
        made.append(b)
for day in (2, 0):                                   # walk-in cash sales
    d = now - timedelta(days=day)
    bl = [BillItem(item_id=items["105"]["item_id"], item_alias="105", name="Banana Green", qty=6.0, unit="kg", rate=40.0, amount=240.0),
          BillItem(item_id=items["101"]["item_id"], item_alias="101", name="Apple", qty=2.0, unit="kg", rate=160.0, amount=320.0)]
    bs.create_bill(BillCreate(invoice_date=d.strftime("%Y-%m-%d"), customer_id="CASH", customer_name="Cash Customer", company_id="Company0001", items=bl,
                              total_amount=560.0, balance_due=560.0, created_by="admin", amount_received=560.0, payment_method="Cash"))
bs.void_bill(made[3]["invoice_no"], "admin")          # one voided bill so History shows it
pay.record_customer_payment("CUST103", 5000.0, payment_method="UPI", reference_no="UPI-5521", user_id="admin")   # a receipt on account

# orders
osvc = OrderService(db)
for i, (cid, cname, st) in enumerate([("CUST101", "Green Leaf Restaurant", "pending"), ("CUST102", "Sri Lakshmi Caterers", "pending"), ("CUST104", "Sunrise Hostel Mess", "confirmed"), ("CUST103", "Hotel Annapoorna", "pending")]):
    its = [OrderItem(item_id=items[a]["item_id"], name=items[a]["name"], qty=float(q), unit="kg", rate=aliases[a], amount=q * aliases[a]) for a, q in (("111", 20 + i), ("106", 10), ("105", 15))]
    osvc.create_order(OrderCreate(customer_id=cid, customer_name=cname, company_id="Company0001", items=its, status=st, created_by="admin",
                                  order_date=now, delivery_date=now + timedelta(days=1 + i % 2), notes="Deliver before 7 AM"))

# waste + adjustment + drawer
inv = InventoryService(db)
inv.record_waste(items["105"]["item_id"], 6.0, 32.0, "Over-ripe", "admin")
inv.record_waste(items["106"]["item_id"], 4.0, 48.0, "Damaged in transit", "admin")
inv.adjust_stock(items["107"]["item_id"], -3.0, "Dried out overnight", "admin")
SessionService(db).open_session("USER0001", "admin", 2000.0)
print("demo data ready:", {c: raw[c].estimated_document_count() for c in ("bills", "orders", "payments", "customers", "journal_entries")})
