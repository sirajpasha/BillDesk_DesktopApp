#!/usr/bin/env python3
"""
Restore a BillDesk backup (.zip made by the app or scripts/copy_db.py-style folders are not supported here).

    python scripts/restore_backup.py "C:\\...\\billdesk_sv_billing_20261010_020000_auto.zip" --target-db sv_billing_restored
    python scripts/restore_backup.py backup.zip --target-db sv_billing --replace     # DANGEROUS: replaces the live data

The default is safe: the backup is loaded into a NEW (empty) database and the document counts are verified.
Point BillDesk at it afterwards by setting DB_NAME in .env (or compare it with the live data first).
--replace is required to load into a database that already has data, and asks you to type the database name.
Stop BillDesk before restoring over a live database.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import Settings, settings  # noqa: E402
from app.database.connection import MongoDatabase  # noqa: E402
from app.services.backup_service import BackupError, BackupService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup", help="path to a billdesk_*.zip backup")
    ap.add_argument("--target-db", required=True, help="database to restore into")
    ap.add_argument("--url", default=settings.mongodb_url, help=f"MongoDB URL (default {settings.mongodb_url})")
    ap.add_argument("--replace", action="store_true", help="allow replacing existing data in the target database")
    args = ap.parse_args()

    target = MongoDatabase(Settings(mongodb_url=args.url, db_name=args.target_db))
    target.connect()
    if args.replace:
        typed = input(f"This REPLACES all data in database '{args.target_db}'. Type its name to continue: ")
        if typed.strip() != args.target_db:
            print("Cancelled.")
            return 1
    try:
        restored = BackupService(target).restore(args.backup, target, replace=args.replace)
    except BackupError as exc:
        print(f"[ERROR] {exc}")
        return 2
    for name, n in sorted(restored.items()):
        print(f"  {n:>8}  {name}")
    print(f"[OK] Restored {sum(restored.values())} documents into '{args.target_db}' and verified the counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
