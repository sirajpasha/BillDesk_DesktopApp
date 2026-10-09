"""More fictional demo data for the user-guide screenshots: returns (credit and debit notes), a bank account, a second drawer user.
Run once, after demo_data.py, against the demo database only."""
import os
import sys

sys.path.insert(0, os.getcwd())
from app.config.settings import settings

assert "demo" in settings.db_name
from app.database.connection import MongoDatabase
from app.services.banking_service import BankingService
from app.services.purchase_returns_service import PurchaseReturnsService
from app.services.returns_service import ReturnsService

db = MongoDatabase(settings)
db.connect()
raw = db.db

# a credit note: part of a credit customer's invoice comes back, and one spoiled line on another
bills = list(raw.bills.find({"customer_id": {"$in": ["CUST101", "CUST102", "CUST103"]}, "status": {"$in": ["unpaid", "partial", "paid"]}}).sort("invoice_no", -1))
first = bills[0]
line = first["items"][0]
r1 = ReturnsService(db).create_return(first["invoice_no"], [{"item_id": line["item_id"], "qty": min(2.0, float(line["qty"]))}], reason="Quality not as ordered", user_id="admin")
second = bills[1]
line2 = second["items"][1]
ReturnsService(db).create_return(second["invoice_no"], [{"item_id": line2["item_id"], "qty": 1.0, "is_waste": True}], reason="Rotten on arrival", user_id="admin")
print("credit notes:", r1["return_id"], "on", first["invoice_no"])

# a debit note against the vendor bill
pb = raw.purchase_bills.find_one({})
pl = pb["items"][0]
PurchaseReturnsService(db).create_return(pb["purchase_id"], [{"item_id": pl["item_id"], "qty": 10.0}], reason="Short weight", user_id="admin")

# bank account
try:
    BankingService(db).save_bank_account({"bank_name": "State Bank of India", "account_number": "30012345678", "ifsc": "SBIN0001234",
                                          "account_type": "Current", "current_balance": 125000.0})
except ValueError as exc:
    print("bank:", exc)
print("extra demo data ready")
