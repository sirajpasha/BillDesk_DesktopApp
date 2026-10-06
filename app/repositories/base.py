from __future__ import annotations
from typing import Any, Dict, List, Optional
import copy

class BaseRepository:
    """Base repository directly attached to an already-created MongoDB collection.
    Guarantees zero collection creation and encapsulates PyMongo operations.
    """
    def __init__(self, db: Any, collection_name: str):
        self.db = db
        self.collection_name = collection_name

    @property
    def col(self):
        """Return the pre-existing collection handle."""
        return self.db.collection(self.collection_name)

    def find_one(self, filter_query: Optional[Dict[str, Any]] = None, sort: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        kwargs = {}
        if sort:
            kwargs["sort"] = sort
        return self.col.find_one(filter_query or {}, **kwargs)

    def find(
        self,
        filter_query: Optional[Dict[str, Any]] = None,
        sort: Optional[Any] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        cursor = self.col.find(filter_query or {})
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def insert_one(self, doc: Dict[str, Any], session: Optional[Any] = None) -> Dict[str, Any]:
        kw = {"session": session} if session else {}
        self.col.insert_one(doc, **kw)
        return doc

    def update_one(
        self,
        filter_query: Dict[str, Any],
        update_doc: Dict[str, Any],
        session: Optional[Any] = None
    ) -> bool:
        kw = {"session": session} if session else {}
        res = self.col.update_one(filter_query, update_doc, **kw)
        return getattr(res, "modified_count", 1) > 0 if hasattr(res, "modified_count") else bool(res)

    def delete_one(self, filter_query: Dict[str, Any], session: Optional[Any] = None) -> bool:
        kw = {"session": session} if session else {}
        res = self.col.delete_one(filter_query, **kw)
        return getattr(res, "deleted_count", 1) > 0 if hasattr(res, "deleted_count") else bool(res)

    def count_documents(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        return self.col.count_documents(filter_query or {})
