#!/usr/bin/env python3
"""
Reset a user's password (e.g. the administrator forgot the one shown at first start).

    python scripts/reset_password.py --user admin

Prompts for the new password (not echoed). Needs access to the database, like the application itself.
"""
from __future__ import annotations
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings  # noqa: E402
from app.database.connection import MongoDatabase  # noqa: E402
from app.services.admin_service import AdminService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", required=True)
    args = ap.parse_args()
    pw = getpass.getpass(f"New password for '{args.user}': ")
    if pw != getpass.getpass("Repeat it: "):
        print("[ERROR] The two passwords differ.")
        return 1
    db = MongoDatabase(settings)
    db.connect()
    try:
        AdminService(db).set_password(args.user, pw)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 2
    print(f"[OK] Password for '{args.user}' changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
