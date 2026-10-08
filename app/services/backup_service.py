"""Database backups: one verified .zip per backup (same `<collection>.jsonl` format as scripts/copy_db.py).

* create_backup  - export every collection, then re-open the zip and verify the document counts match
* backup_if_due  - at most one automatic backup per `max_age_hours`, with retention (daily + monthly)
* restore        - load a backup into a database that is EMPTY (or replace=True after explicit confirmation)
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import json_util

from app.config.settings import settings

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^billdesk_(?P<db>.+)_(?P<ts>\d{8}_\d{6})_(?P<label>[a-z]+)\.zip$")
BATCH = 1000


def default_backup_dir() -> Path:
    return Path(settings.backup_dir) if settings.backup_dir else Path(os.getenv("APPDATA") or Path.home()) / "BillDesk" / "backups"


class BackupError(RuntimeError):
    pass


class BackupService:
    def __init__(self, db: Any, backup_dir: Optional[str | Path] = None, keep_daily: int = 14, keep_monthly: int = 12):
        self.db = db
        self.dir = Path(backup_dir) if backup_dir else default_backup_dir()
        self.keep_daily = keep_daily
        self.keep_monthly = keep_monthly

    # ------------------------------------------------------------------ helpers
    def _db_name(self) -> str:
        return getattr(getattr(self.db, "settings", None), "db_name", None) or settings.db_name

    def _collection_names(self) -> List[str]:
        names = self.db.list_collection_names() if hasattr(self.db, "list_collection_names") else self.db.db.list_collection_names()
        return sorted(n for n in names if not n.startswith("system."))

    # ------------------------------------------------------------------ create
    def create_backup(self, label: str = "auto") -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final = self.dir / f"billdesk_{self._db_name()}_{stamp}_{label}.zip"
        fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=self.dir)
        os.close(fd)
        tmp = Path(tmp_name)
        counts: Dict[str, int] = {}
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for name in self._collection_names():
                    n = 0
                    with z.open(f"{name}.jsonl", "w") as out:
                        for doc in self.db.collection(name).find({}):
                            out.write((json_util.dumps(doc) + "\n").encode("utf-8"))
                            n += 1
                    counts[name] = n
                manifest = {"app": "BillDesk", "database": self._db_name(), "created": datetime.now(timezone.utc).isoformat(),
                            "label": label, "collections": counts}
                z.writestr("manifest.json", json.dumps(manifest, indent=1))
            self._verify(tmp, counts)
            os.replace(tmp, final)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        log.info("Backup written: %s (%d collections, %d documents)", final, len(counts), sum(counts.values()))
        return final

    @staticmethod
    def _verify(path: Path, expected: Dict[str, int]) -> None:
        """Re-read the finished archive: it must be intact and hold exactly the exported documents."""
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                raise BackupError(f"Backup is corrupt (first bad member: {bad})")
            for name, n in expected.items():
                with z.open(f"{name}.jsonl") as f:
                    got = sum(1 for line in io.TextIOWrapper(f, encoding="utf-8") if line.strip())
                if got != n:
                    raise BackupError(f"Backup verification failed for {name}: wrote {n}, read back {got}")

    # ------------------------------------------------------------------ listing, schedule, retention
    def list_backups(self) -> List[Dict[str, Any]]:
        out = []
        if self.dir.exists():
            for p in self.dir.glob("billdesk_*.zip"):
                m = NAME_RE.match(p.name)
                if m:
                    out.append({"path": p, "db": m["db"], "label": m["label"], "size": p.stat().st_size,
                                "created": datetime.strptime(m["ts"], "%Y%m%d_%H%M%S")})
        return sorted(out, key=lambda b: b["created"], reverse=True)

    def last_backup(self) -> Optional[Dict[str, Any]]:
        mine = [b for b in self.list_backups() if b["db"] == self._db_name()]
        return mine[0] if mine else None

    def backup_if_due(self, max_age_hours: float = 24.0) -> Optional[Path]:
        last = self.last_backup()
        if last and datetime.now() - last["created"] < timedelta(hours=max_age_hours):
            return None
        path = self.create_backup("auto")
        self.prune()
        return path

    def prune(self) -> List[Path]:
        """Keep the newest `keep_daily` automatic backups plus the newest one of each of the last `keep_monthly` months."""
        autos = [b for b in self.list_backups() if b["label"] == "auto" and b["db"] == self._db_name()]
        keep = {b["path"] for b in autos[: self.keep_daily]}
        seen_months: List[str] = []
        for b in autos:                                   # newest first
            month = b["created"].strftime("%Y-%m")
            if month not in seen_months and len(seen_months) < self.keep_monthly:
                seen_months.append(month)
                keep.add(b["path"])
        removed = []
        for b in autos:
            if b["path"] not in keep:
                b["path"].unlink(missing_ok=True)
                removed.append(b["path"])
        return removed

    # ------------------------------------------------------------------ restore
    def restore(self, zip_path: str | Path, target_db: Any, replace: bool = False) -> Dict[str, int]:
        """Load a backup into `target_db`. Refuses non-empty collections unless replace=True."""
        zip_path = Path(zip_path)
        with zipfile.ZipFile(zip_path) as z:
            if z.testzip():
                raise BackupError("Backup file is corrupt")
            manifest = json.loads(z.read("manifest.json"))
            expected: Dict[str, int] = manifest["collections"]
            for name in expected:
                col = target_db.collection(name)
                if col.count_documents({}) and not replace:
                    raise BackupError(f"Target collection '{name}' is not empty; restore into an empty database or pass replace=True")
            restored: Dict[str, int] = {}
            for name, n in expected.items():
                col = target_db.collection(name)
                if replace:
                    col.delete_many({})
                batch: List[Any] = []
                count = 0
                with z.open(f"{name}.jsonl") as f:
                    for line in io.TextIOWrapper(f, encoding="utf-8"):
                        if not line.strip():
                            continue
                        batch.append(json_util.loads(line))
                        count += 1
                        if len(batch) >= BATCH:
                            self._insert(col, batch)
                            batch = []
                if batch:
                    self._insert(col, batch)
                if count != n:
                    raise BackupError(f"Restore of {name} incomplete: expected {n}, read {count}")
                restored[name] = count
        log.info("Restored %s into %s: %d documents", zip_path.name, getattr(getattr(target_db, 'settings', None), 'db_name', '?'), sum(restored.values()))
        return restored

    @staticmethod
    def _insert(col: Any, docs: List[Any]) -> None:
        if hasattr(col, "insert_many"):
            col.insert_many(docs)
        else:
            for d in docs:
                col.insert_one(d)
