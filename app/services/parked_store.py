"""Crash-safe local storage for parked (held) bills.

Parked bills are per-counter scratch data, so they live in a small JSON file on the counter PC rather than in the
shared MongoDB (which would need a new collection in the legacy schema). The file is rewritten atomically on every
change, so a crash or power cut leaves either the old or the new list - never a half-written one.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import json_util          # round-trips ObjectId / datetime found in customer documents


def default_parked_file() -> str:
    base = os.getenv("APPDATA") or str(Path.home())
    return str(Path(base) / "BillDesk" / "parked_bills.json")


class ParkedBillStore:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or default_parked_file())
        self._items: List[Dict[str, Any]] = self._load()

    # ------------------------------------------------------------------ persistence
    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json_util.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            # unreadable file: keep it for inspection instead of silently overwriting it
            try:
                self.path.replace(self.path.with_suffix(".corrupt"))
            except OSError:
                pass
            return []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json_util.dumps(self._items), encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ operations
    def add(self, bill: Dict[str, Any]) -> int:
        self._items.append(bill)
        try:
            self._save()
        except OSError:
            self._items.pop()               # do not report a bill as parked when it could not be stored
            raise
        return len(self._items)

    def all(self) -> List[Dict[str, Any]]:
        return self._items

    def discard(self, index: int) -> bool:
        if not (0 <= index < len(self._items)):
            return False
        removed = self._items.pop(index)
        try:
            self._save()
        except OSError:
            self._items.insert(index, removed)
            raise
        return True
