from __future__ import annotations
import contextlib
import contextvars
import functools
import logging
from typing import Any, Callable, Iterator, Optional

import certifi
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

log = logging.getLogger(__name__)

# The transaction (ClientSession) the current thread/context is running in, if any.
_active_session: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar("billdesk_active_session", default=None)

# Collection methods that must take part in an ambient transaction.
_SESSION_METHODS = frozenset({
    "find", "find_one", "count_documents", "aggregate", "distinct",
    "insert_one", "insert_many", "update_one", "update_many", "replace_one", "delete_one", "delete_many",
    "find_one_and_update", "find_one_and_delete", "find_one_and_replace",
})


class _SessionCollection:
    """Thin proxy over a pymongo Collection: while a transaction is active every operation joins it automatically,
    so services can be made atomic with a single `with db.transaction():` without threading `session=` everywhere."""

    __slots__ = ("_coll",)

    def __init__(self, coll):
        object.__setattr__(self, "_coll", coll)

    def __getattr__(self, name: str):
        attr = getattr(self._coll, name)
        if name in _SESSION_METHODS and callable(attr):
            @functools.wraps(attr)
            def with_session(*args, **kwargs):
                session = _active_session.get()
                if session is not None and kwargs.get("session") is None:
                    kwargs["session"] = session
                return attr(*args, **kwargs)
            return with_session
        return attr

    def __getitem__(self, name):
        return _SessionCollection(self._coll[name])

    def __repr__(self) -> str:
        return f"<session-aware {self._coll!r}>"


def transactional(fn: Callable) -> Callable:
    """Decorator for service methods: run the whole method in one database transaction (when the server supports
    them; on a standalone MongoDB it simply runs). Nested calls join the outer transaction."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        tx = getattr(self.db, "transaction", None)
        with (tx() if tx else contextlib.nullcontext()):
            return fn(self, *args, **kwargs)
    return wrapper


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

    # collections BillDesk itself creates on first use; their indexes are created up front
    OWN_COLLECTIONS = ("journal_entries",)

    def _ensure_index(self, collection_name: str, keys, *, unique=False, sparse=False, name=None) -> None:
        """Create an index only when it does not already exist.

        The original BillDesk database may already contain indexes created by
        the web/FastAPI application. Calling create_index() again with the
        same generated name can raise IndexKeySpecsConflict when an older
        index has slightly different options. Reusing an existing index keeps
        the native app compatible with the existing database.
        """
        try:
            if self.db is None:
                return
            exists = collection_name in self.db.list_collection_names()
            if not exists and collection_name not in self.OWN_COLLECTIONS:
                return
            collection = self.db[collection_name]
            existing = list(collection.list_indexes()) if exists else []
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
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

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

        # Lookups the application does on every save / screen (found by the integrity review): without these they
        # scan the whole collection, which is fine at hundreds of rows and slow at tens of thousands.
        self._ensure_index("journal_entries", [("reference", ASCENDING), ("source_type", ASCENDING)])   # idempotent posting
        self._ensure_index("journal_entries", [("date", DESCENDING)])
        self._ensure_index("bills", [("customer_id", ASCENDING), ("status", ASCENDING)])               # open bills per customer
        self._ensure_index("bills", [("invoice_date", DESCENDING)])
        self._ensure_index("payments", [("party_id", ASCENDING), ("created_at", DESCENDING)])
        self._ensure_index("orders", [("status", ASCENDING), ("customer_id", ASCENDING)])
        self._ensure_index("stock_transactions", [("item_id", ASCENDING), ("date", DESCENDING)])
        self._ensure_index("purchase_bills", [("supplier_id", ASCENDING)])
        self._ensure_index("user_activity_audits", [("timestamp", DESCENDING)])

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.supports_transactions = False

    def list_collection_names(self):
        if self.db is None:
            raise RuntimeError("MongoDB is not connected")
        return self.db.list_collection_names()

    def collection(self, name: str):
        if self.db is None:
            raise RuntimeError("MongoDB is not connected")
        return _SessionCollection(self.db[name])

    @contextlib.contextmanager
    def transaction(self) -> Iterator[Optional[Any]]:
        """All-or-nothing block. Needs a replica set (check `supports_transactions`); on a standalone server it runs
        the block without atomicity. Re-entrant: a nested block joins the transaction that is already open."""
        outer = _active_session.get()
        if outer is not None or not self.supports_transactions or self.client is None:
            yield outer
            return
        session = self.client.start_session()
        token = _active_session.set(session)
        try:
            session.start_transaction()
            yield session
            self._commit(session)
        except BaseException:
            try:
                session.abort_transaction()
            except PyMongoError:
                log.warning("Could not abort the transaction cleanly", exc_info=True)
            raise
        finally:
            _active_session.reset(token)
            session.end_session()

    @staticmethod
    def _commit(session) -> None:
        for attempt in range(5):
            try:
                session.commit_transaction()
                return
            except PyMongoError as exc:
                if exc.has_error_label("UnknownTransactionCommitResult") and attempt < 4:
                    continue                    # the commit may or may not have happened: committing again is safe
                raise
