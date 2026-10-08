import os, sys
sys.path.insert(0, os.getcwd())
from pymongo import MongoClient
d = MongoClient(os.environ["MONGODB_URL"])[os.environ["DB_NAME"]]
assert "qa" in os.environ["DB_NAME"]
# normalise seeder output so the app can use it (see report defect D-03)
for c in ["users","items","customers","suppliers"]:
    d[c].update_many({"is_deleted": {"$exists": False}}, {"$set": {"is_deleted": 0}})
    d[c].update_many({"status": {"$exists": False}}, {"$set": {"status": "active"}})
d.items.update_many({"stock": {"$exists": False}}, {"$set": {"stock": 100.0}})
d.customers.update_one({"cust_id": "Cust0001"}, {"$set": {"payment_terms_days": 30, "bill_to_name": "Anna Adarsh Hostel"}})
d.suppliers.update_one({"supplier_id": "SUP001"}, {"$set": {"tds_applicable": True, "tds_rate": 2.0, "tds_section": "194C"}})
for c in ["bills","orders","payments","ledger_transactions","journal_entries","stock_transactions","bill_audits","crate_transactions","waste_logs",
          "purchase_orders","grns","purchase_bills","ap_payments","sessions","cashier_sessions","fixed_prices","user_activity_audits"]:
    d[c].delete_many({})
d.items.update_many({}, {"$set": {"stock": 100.0}})
d.customers.update_many({}, {"$set": {"current_balance": 0.0, "crate_balances": []}})
d.customers.update_one({"cust_id": "Cust0001"}, {"$set": {"credit_limit": 5000.0}})
d.suppliers.update_many({}, {"$set": {"current_balance": 0.0}})
d.users.delete_many({"username":{"$in":["tester","weak","longpw","rolex"]}}); d.items.delete_many({"item_id":{"$regex":"^QAI"}}); d.customers.delete_many({"cust_id":{"$regex":"^QAC"}})
d.users.update_many({}, {"$set": {"status": "active"}})
print("reset ok")
