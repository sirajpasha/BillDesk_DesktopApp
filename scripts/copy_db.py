"""
Copy every collection of one MongoDB database into another (e.g. Railway production -> local BillDesk).

    python scripts/copy-db.py --source-db billdesk_sv_prod --target-db sv_billing            # asks before replacing
    python scripts/copy-db.py ... --dry-run                                                  # counts only, writes nothing
    python scripts/copy-db.py ... --yes                                                      # no prompt

The SOURCE is only ever read. For the TARGET, each collection that exists in the source is dropped and
re-created from it (a copy, not a merge), after the target's current contents are exported to JSON in
--backup-dir so the replacement can be undone.

Connection strings (keep passwords out of shell history / the repo):
    SOURCE_MONGODB_URL   env var, or --source-file PATH (one line), or --source-url
    TARGET_MONGODB_URL   defaults to BillDesk's local MongoDB: mongodb://127.0.0.1:27018

Stop BillDesk before running (the target collections are replaced underneath it).
Run with the backend venv:  backend\\.venv-build\\Scripts\\python scripts\\copy-db.py ...
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

from bson import json_util
from pymongo import MongoClient, errors

SKIP_DBS = {"admin", "config", "local"}


def mask(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]*(@)", r"\1***\2", url)


def read_source_url(a) -> str:
    if a.source_url:
        return a.source_url.strip()
    if a.source_file:
        return Path(a.source_file).read_text(encoding="utf-8").strip().splitlines()[0].strip()
    v = os.environ.get("SOURCE_MONGODB_URL")
    if v:
        return v.strip()
    sys.exit("No source connection string: set SOURCE_MONGODB_URL, or use --source-file / --source-url")


def connect(url: str, label: str) -> MongoClient:
    c = MongoClient(url, serverSelectionTimeoutMS=15000)
    try:
        c.admin.command("ping")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Cannot connect to {label} {mask(url)}: {type(e).__name__}: {str(e)[:300]}")
    return c


def user_collections(db):
    return sorted(n for n in db.list_collection_names() if not n.startswith("system."))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-url")
    ap.add_argument("--source-file")
    ap.add_argument("--source-db", required=True)
    ap.add_argument("--target-url", default=os.environ.get("TARGET_MONGODB_URL", "mongodb://127.0.0.1:27018"))
    ap.add_argument("--target-db", required=True)
    ap.add_argument("--backup-dir", default=str(Path(os.environ.get("APPDATA", ".")) / "BillDesk" / "backups"))
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    if a.source_db in SKIP_DBS or a.target_db in SKIP_DBS:
        sys.exit("Refusing to use admin/config/local")

    src_url = read_source_url(a)
    if mask(src_url) == mask(a.target_url) and a.source_db == a.target_db:
        sys.exit("Source and target are the same database")

    print(f"source : {mask(src_url)}  db={a.source_db}")
    print(f"target : {mask(a.target_url)}  db={a.target_db}")
    src_c = connect(src_url, "source")
    dst_c = connect(a.target_url, "target")
    src, dst = src_c[a.source_db], dst_c[a.target_db]

    names = user_collections(src)
    if not names:
        sys.exit(f"Source database '{a.source_db}' has no collections (wrong db name or no permission?). "
                 f"Databases visible: {[d for d in src_c.list_database_names() if d not in SKIP_DBS]}")

    print(f"\n{'collection':32} {'source':>10} {'target now':>12}")
    total = 0
    plan = []
    for n in names:
        s, t = src[n].estimated_document_count(), dst[n].estimated_document_count() if n in dst.list_collection_names() else 0
        s = src[n].count_documents({})
        total += s
        plan.append((n, s))
        print(f"{n:32} {s:>10} {t:>12}")
    extra = [n for n in user_collections(dst) if n not in names]
    if extra:
        print(f"\nTarget-only collections (left untouched): {extra}")
    print(f"\n{len(names)} collections, {total} documents to copy.")
    if a.dry_run:
        print("Dry run: nothing written.")
        return

    if not a.yes:
        ans = input(f"Replace these collections in '{a.target_db}' on {mask(a.target_url)}? [y/N] ").strip().lower()
        if ans != "y":
            sys.exit("Aborted.")

    # 1) back up what is about to be replaced
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = Path(a.backup_dir) / f"pre-copy_{a.target_db}_{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    for n in names:
        if n in dst.list_collection_names():
            with open(bdir / f"{n}.jsonl", "w", encoding="utf-8") as f:
                for d in dst[n].find():
                    f.write(json_util.dumps(d) + "\n")
    print(f"\nTarget backup written to {bdir}")

    # 2) copy
    failures = []
    for n, expected in plan:
        dst[n].drop()
        buf, done = [], 0
        for d in src[n].find(no_cursor_timeout=False):
            buf.append(d)
            if len(buf) >= a.batch:
                dst[n].insert_many(buf, ordered=False)
                done += len(buf)
                buf = []
        if buf:
            dst[n].insert_many(buf, ordered=False)
            done += len(buf)
        # indexes (the _id index already exists)
        for name, info in src[n].index_information().items():
            if name == "_id_":
                continue
            opts = {k: v for k, v in info.items() if k in ("unique", "sparse", "expireAfterSeconds", "partialFilterExpression")}
            try:
                dst[n].create_index(info["key"], name=name, **opts)
            except errors.PyMongoError as e:
                print(f"   ! index {name} on {n}: {str(e)[:120]}")
        got = dst[n].count_documents({})
        ok = got == expected
        print(f"  {'ok ' if ok else 'BAD'} {n:32} {got}/{expected}")
        if not ok:
            failures.append(n)

    if failures:
        sys.exit(f"\nCount mismatch in: {failures}. Target backup is in {bdir}")
    print(f"\nDone: {total} documents copied into {a.target_db}. Undo: restore from {bdir}")


if __name__ == "__main__":
    main()
