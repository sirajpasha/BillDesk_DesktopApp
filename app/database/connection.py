from __future__ import annotations
from pymongo import MongoClient, ASCENDING, DESCENDING
import certifi

class MongoDatabase:
    def __init__(self, settings):
        self.settings = settings
        self.client: MongoClient | None = None
        self.db = None
        self.supports_transactions = False

    def connect(self) -> None:
        kwargs = {"serverSelectionTimeoutMS": 5000}
        if self.settings.mongodb_url.startswith("mongodb+srv://") or "tls=true" in self.settings.mongodb_url.lower():
            kwargs["tlsCAFile"] = certifi.where()
        self.client = MongoClient(self.settings.mongodb_url, **kwargs)
        self.client.admin.command("ping")
        hello = self.client.admin.command("hello")
        self.supports_transactions = bool(hello.get("setName"))
        self.db = self.client[self.settings.db_name]

    def _ensure_index(self, collection_name: str, keys, *, unique=False, sparse=False, name=None) -> None:
        """Create an index only when it does not already exist.

        The original BillDesk database may already contain indexes created by
        the web/FastAPI application. Calling create_index() again with the
        same generated name can raise IndexKeySpecsConflict when an older
        index has slightly different options. Reusing an existing index keeps
        the native app compatible with the existing database.
        """
        try:
            if self.db is None or collection_name not in self.db.list_collection_names():
                return
            collection = self.db[collection_name]
            existing = list(collection.list_indexes())
            desired_name = name or "_".join(f"{field}_{direction}" for field, direction in keys)

            for index in existing:
                if index.get("name") == desired_name:
                    return

            collection.create_index(
                keys,
                unique=unique,
                sparse=sparse,
                name=desired_name,
            )
        except Exception:
            pass

    def ensure_indexes(self) -> None:
        if self.db is None:
            raise RuntimeError("MongoDB is not connected")

        self._ensure_index("users", [("username", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("items", [("item_id", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("items", [("item_alias", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("customers", [("cust_id", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("bills", [("invoice_no", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("bills", [("created_at", DESCENDING)])
        self._ensure_index("stock_transactions", [("transaction_id", ASCENDING)], unique=True, sparse=True)
        self._ensure_index("bill_audits", [("audit_id", ASCENDING)], unique=True, sparse=True)

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.supports_transactions = False

    def collection(self, name: str):
        if self.db is None:
            raise RuntimeError("MongoDB is not connected")
        return self.db[name]
