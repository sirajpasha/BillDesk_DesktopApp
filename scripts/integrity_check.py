#!/usr/bin/env python3
"""
Read-only data-integrity report: do bills, payments, customer balances, stock and the ledger agree?

    python scripts/integrity_check.py                 # summary + first findings of each check
    python scripts/integrity_check.py --details       # every finding (capped at 200 per check)
    python scripts/integrity_check.py --out report.txt

Exit code 0 = no failures, 1 = at least one FAIL (warnings do not fail the run). Nothing is ever written.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings  # noqa: E402
from app.database.connection import MongoDatabase  # noqa: E402
from app.services.integrity_service import IntegrityService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--details", action="store_true", help="print every finding")
    ap.add_argument("--out", help="also write the report to this file")
    args = ap.parse_args()

    db = MongoDatabase(settings)
    db.connect()
    print(f"[INFO] checking {settings.mongodb_url} / {settings.db_name} (read-only)")
    report = IntegrityService(db).run_all()
    print(IntegrityService.format_report(report, with_details=args.details))
    if args.out:
        Path(args.out).write_text(IntegrityService.format_report(report), encoding="utf-8")
        print(f"[INFO] report saved to {args.out}")
    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
