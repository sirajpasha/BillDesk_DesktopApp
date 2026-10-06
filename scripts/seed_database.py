#!/usr/bin/env python3
"""
Seed MongoDB database with master items, customers, suppliers, companies, and roles.
Idempotent: Only inserts records that do not already exist.
Values are dynamically read from configuration (settings.py / .env) and data/seed_data.json.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app.config.settings import settings
from app.database.connection import MongoDatabase
import bcrypt


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def load_seed_json() -> dict:
    seed_file = root_dir / "data" / "seed_data.json"
    if not seed_file.exists():
        print(f"[WARN] Seed file {seed_file} not found.")
        return {}
    with open(seed_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_extra_items() -> list[dict]:
    items_file = root_dir / "data" / "items.json"
    if not items_file.exists():
        return []
    with open(items_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def seed_database():
    print(f"[INFO] Connecting to MongoDB: {settings.mongodb_url} (DB: {settings.db_name})...")
    db_mgr = MongoDatabase(settings)
    try:
        db_mgr.connect()
    except Exception as e:
        print(f"[ERROR] Failed to connect to MongoDB: {e}")
        sys.exit(1)

    db = db_mgr.db
    data = load_seed_json()
    stats = {}

    # 1. Companies
    companies = data.get("companies", [])
    inserted_companies = 0
    for comp in companies:
        query = {"company_id": comp.get("company_id")} if comp.get("company_id") else {"name": comp.get("name")}
        if not db.companies.find_one(query):
            db.companies.insert_one(comp)
            inserted_companies += 1
    stats["companies"] = inserted_companies

    # 2. Items
    items = data.get("items", [])
    extra_items = load_extra_items()
    all_items = items + extra_items
    inserted_items = 0
    for item in all_items:
        item_id = item.get("item_id")
        alias = item.get("item_alias")
        query = {}
        if item_id:
            query = {"item_id": item_id}
        elif alias:
            query = {"item_alias": alias}
        else:
            query = {"name": item.get("name")}

        if not db.items.find_one(query):
            # Ensure price if not present
            if "default_rate" not in item:
                item["default_rate"] = settings.default_rate
            db.items.insert_one(item)
            inserted_items += 1
    stats["items"] = inserted_items

    # 3. Customers
    customers = data.get("customers", [])
    inserted_cust = 0
    for cust in customers:
        cid = cust.get("cust_id")
        query = {"cust_id": cid} if cid else {"name": cust.get("name")}
        if not db.customers.find_one(query):
            db.customers.insert_one(cust)
            inserted_cust += 1
    stats["customers"] = inserted_cust

    # 4. Suppliers
    suppliers = data.get("suppliers", [])
    inserted_supp = 0
    for supp in suppliers:
        sid = supp.get("supplier_id")
        query = {"supplier_id": sid} if sid else {"name": supp.get("name")}
        if not db.suppliers.find_one(query):
            db.suppliers.insert_one(supp)
            inserted_supp += 1
    stats["suppliers"] = inserted_supp

    # 5. Roles & Permissions
    roles = data.get("roles", [])
    inserted_roles = 0
    for role in roles:
        rname = role.get("name")
        if not db.roles.find_one({"name": rname}):
            db.roles.insert_one(role)
            inserted_roles += 1
    stats["roles"] = inserted_roles

    # 6. Users
    users = data.get("users", [])
    inserted_users = 0
    for u in users:
        uname = u.get("username")
        if not db.users.find_one({"username": uname}):
            raw_pwd = u.get("password", "")
            doc = {k: v for k, v in u.items() if k != "password"}
            doc["password_hash"] = hash_password(raw_pwd) if raw_pwd else ""
            db.users.insert_one(doc)
            inserted_users += 1
    stats["users"] = inserted_users

    print("[SUCCESS] Database seeding complete!")
    for k, v in stats.items():
        print(f"  - {k}: {v} new records added (existing retained).")


if __name__ == "__main__":
    seed_database()
