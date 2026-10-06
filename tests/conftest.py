import os
import sys
import re
import copy
from datetime import datetime, timezone
import pytest

# Ensure Windows TCL/TK paths are reliably discovered
tcl_candidate = os.path.join(sys.prefix, "tcl", "tcl8.6")
tk_candidate = os.path.join(sys.prefix, "tcl", "tk8.6")
if os.path.exists(tcl_candidate) and "TCL_LIBRARY" not in os.environ:
    os.environ["TCL_LIBRARY"] = tcl_candidate
if os.path.exists(tk_candidate) and "TK_LIBRARY" not in os.environ:
    os.environ["TK_LIBRARY"] = tk_candidate

@pytest.fixture(scope="session")
def tk_root():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass

class MockCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key_or_list, direction=1):
        if isinstance(key_or_list, list):
            for k, d in reversed(key_or_list):
                self._docs.sort(key=lambda x: x.get(k, 0), reverse=(d == -1))
        else:
            self._docs.sort(key=lambda x: x.get(key_or_list, 0), reverse=(direction == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)

    def __list__(self):
        return list(self._docs)

class MockCollection:
    def __init__(self, name):
        self.name = name
        self.docs = []

    def _matches(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, branch) for branch in v):
                    return False
            elif isinstance(v, dict):
                val = doc.get(k)
                for op, target in v.items():
                    if op == "$regex":
                        flags = re.IGNORECASE if v.get("$options") == "i" else 0
                        if not re.search(str(target), str(val or ""), flags):
                            return False
                    elif op == "$lte":
                        if val is None or val > target:
                            return False
                    elif op == "$gte":
                        if val is None or val < target:
                            return False
                    elif op == "$in":
                        if val not in target:
                            return False
                    elif op == "$nin":
                        if val in target:
                            return False
                    elif op == "$ne":
                        if val == target:
                            return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def find_one(self, query=None, sort=None):
        docs = [copy.deepcopy(d) for d in self.docs if self._matches(d, query or {})]
        if sort:
            cursor = MockCursor(docs).sort(sort)
            docs = cursor._docs
        return docs[0] if docs else None

    def find(self, query=None, sort=None):
        docs = [copy.deepcopy(d) for d in self.docs if self._matches(d, query or {})]
        cursor = MockCursor(docs)
        if sort:
            cursor.sort(sort)
        return cursor

    def insert_one(self, doc, session=None):
        stored = copy.deepcopy(doc)
        if "_id" not in stored:
            stored["_id"] = f"id_{len(self.docs) + 1}"
        self.docs.append(stored)
        return stored

    def update_one(self, filter_query, update_doc, session=None):
        for doc in self.docs:
            if self._matches(doc, filter_query):
                if "$inc" in update_doc:
                    for field, inc_val in update_doc["$inc"].items():
                        doc[field] = doc.get(field, 0.0) + inc_val
                if "$set" in update_doc:
                    for field, set_val in update_doc["$set"].items():
                        doc[field] = copy.deepcopy(set_val)
                if "$push" in update_doc:
                    for field, push_val in update_doc["$push"].items():
                        if field not in doc:
                            doc[field] = []
                        doc[field].append(copy.deepcopy(push_val))
                return True
        return False

    def count_documents(self, query=None):
        return len([d for d in self.docs if self._matches(d, query or {})])

    def delete_one(self, filter_query):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, filter_query):
                del self.docs[idx]
                return True
        return False

    def delete_many(self, filter_query):
        initial = len(self.docs)
        self.docs = [d for d in self.docs if not self._matches(d, filter_query)]
        return len(self.docs) < initial

class MockMongoDatabase:
    def __init__(self):
        import types
        self._collections = {}
        self.supports_transactions = False
        self.client = None
        self.settings = types.SimpleNamespace(mongodb_url="mongodb://127.0.0.1:27018", db_name="sv_billing")

    def collection(self, name: str) -> MockCollection:
        if name not in self._collections:
            self._collections[name] = MockCollection(name)
        return self._collections[name]

    def list_collection_names(self):
        return list(self._collections.keys())

@pytest.fixture
def fake_db():
    db = MockMongoDatabase()
    # Seed default collections
    db.collection("items").insert_one({
        "item_id": "ITEM001",
        "item_alias": "TOM",
        "name": "Tomato",
        "unit": "kg",
        "category": "Vegetables",
        "stock": 100.0,
        "status": "active",
        "is_deleted": 0,
    })
    db.collection("customers").insert_one({
        "cust_id": "CUST001",
        "name": "Metro Retailers",
        "credit_limit": 50000.0,
        "current_balance": 10000.0,
        "payment_terms_days": 30,
        "status": "active",
        "is_deleted": 0,
        "crate_balances": [],
    })
    db.collection("suppliers").insert_one({
        "supplier_id": "SUP001",
        "name": "Green Farms Ltd",
        "tds_applicable": True,
        "tds_rate": 2.0,
        "tds_section": "194C",
        "current_balance": 0.0,
        "status": "active",
        "is_deleted": 0,
    })
    return db
