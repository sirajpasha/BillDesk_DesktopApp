#!/usr/bin/env python3
"""
Post general-ledger journal entries for transactions that were recorded before automatic posting existed.

* Idempotent: every entry is keyed by (reference, source_type); anything already journaled is skipped.
* DRY RUN by default. Nothing is written unless you pass --apply.
* Entries carry the ORIGINAL document date, so period reports stay meaningful.

What it posts   : sales invoices (+ reversal for void bills), customer receipts, vendor purchase bills,
                  supplier payments, waste logs.
What it cannot  : cost of goods sold (historic bills have no item cost), opening balances (cash/bank/
                  stock/capital before the first bill) and counter payments that were never recorded as
                  `payments` documents. Post those with the "Set Opening Balance" journal in
                  Accounts > Accounting Dashboard, then review the Trial Balance and Balance Sheet.

Usage:  python scripts/backfill_ledger.py            # report what would be posted
        python scripts/backfill_ledger.py --apply    # post it
Back up the database (scripts/copy_db.py) before using --apply on production data.
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app.repositories.base import BaseRepository  # noqa: E402
from app.services.ledger_service import LedgerService  # noqa: E402


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value[:10].count("-") == 2:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def backfill(db: Any, apply: bool = False) -> Dict[str, int]:
    """`db` needs .collection(name) (MongoDatabase or the test mock). Returns counts of entries (to be) posted."""
    led = LedgerService(db)
    rows = lambda name, q, sort: BaseRepository(db, name).find(q, sort=sort, limit=0)  # noqa: E731
    counts = {"sale": 0, "sale_reversal": 0, "receipt": 0, "purchase": 0, "supplier_payment": 0, "waste": 0, "skipped_existing": 0}

    def post(kind: str, ref: str, source: str, fn) -> None:
        if led.has_entry(ref, source):
            counts["skipped_existing"] += 1
            return
        counts[kind] += 1
        if apply:
            fn()

    for b in rows("bills", {"is_deleted": 0}, [("created_at", 1)]):
        when = _dt(b.get("created_at")) or _dt(b.get("invoice_date"))
        cash_walk_in = b.get("customer_id") == "CASH" and b.get("status") in ("paid", "void")
        received = float(b.get("total_amount") or 0.0) if cash_walk_in else 0.0
        post("sale", b["invoice_no"], "sale",
             lambda b=b, when=when, received=received: led.post_sale(b, received=received, user_id="backfill", entry_date=when))
        if b.get("status") == "void" and not led.has_entry(b["invoice_no"], "sale_reversal"):
            counts["sale_reversal"] += 1
            if apply:
                led.reverse_entries(b["invoice_no"], ["sale"], "backfill", entry_date=when)

    for p in rows("payments", {"party_type": "customer", "is_deleted": 0}, [("payment_date", 1)]):
        post("receipt", p.get("payment_id", ""), "receipt",
             lambda p=p: led.post_receipt(p, user_id="backfill", entry_date=_dt(p.get("payment_date")) or _dt(p.get("created_at"))))

    for pb in rows("purchase_bills", {"is_deleted": 0}, [("bill_date", 1)]):
        post("purchase", pb.get("purchase_id", ""), "purchase",
             lambda pb=pb: led.post_purchase_bill(pb, user_id="backfill", entry_date=_dt(pb.get("bill_date"))))

    for ap in rows("ap_payments", {"is_deleted": 0}, [("payment_date", 1)]):
        post("supplier_payment", ap.get("payment_id", ""), "supplier_payment",
             lambda ap=ap: led.post_supplier_payment(ap, user_id="backfill", entry_date=_dt(ap.get("payment_date"))))

    for w in rows("waste_logs", {"is_deleted": 0}, [("date", 1)]):
        post("waste", w.get("waste_id", ""), "waste",
             lambda w=w: led.post_waste(w, user_id="backfill", entry_date=_dt(w.get("date"))))
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write the journal entries (default: dry run)")
    args = ap.parse_args()

    from app.config.settings import settings
    from app.database.connection import MongoDatabase

    print(f"[INFO] {'APPLY' if args.apply else 'DRY RUN'} against {settings.mongodb_url} / {settings.db_name}")
    mgr = MongoDatabase(settings)
    mgr.connect()
    counts = backfill(mgr, apply=args.apply)
    verb = "posted" if args.apply else "would post"
    for k, v in counts.items():
        if k != "skipped_existing":
            print(f"  {verb:>10} {v:>6}  {k}")
    print(f"  {'already journaled':>10} {counts['skipped_existing']:>6}")
    if not args.apply:
        print("[INFO] Nothing was written. Re-run with --apply to post.")
    print("[NOTE] Cost of goods sold and opening balances are NOT backfilled - see the script header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
