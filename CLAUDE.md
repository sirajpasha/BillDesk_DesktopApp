# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BillDesk Native: a keyboard-driven Tkinter/ttk desktop POS + ERP for wholesale produce mandis. It binds directly to a **pre-existing MongoDB database** (`sv_billing`, default `mongodb://127.0.0.1:27018`) that was created by an older web/FastAPI BillDesk app. That older app's source lives in `_ref_billdesk/` (git-ignored, reference only — do not edit or import from it).

## Commands

```bash
python -m pip install -r requirements.txt   # note: ocr_service.py also imports pytesseract, which is not in requirements.txt
python scripts/seed_database.py             # idempotent; only inserts missing records (reads data/seed_data.json)
python main.py                              # run the app (needs MongoDB reachable)
./start.ps1 | start.bat | ./start.sh        # self-healing launchers: check deps, start local mongod on 27018, run app

python -m pytest tests/ -v                  # full suite (48 mapped tests)
python -m pytest tests/test_order_form.py::test_order_form_delete_row_shifts_up -v   # single test
python tests/run_traceability_tests.py      # standalone runner with traceability report
```

Configuration comes from `.env` (see `.env.example`) via `app/config/settings.py`: `MONGODB_URL`, `DB_NAME`, invoice format, company name, default unit/rate/row count. Bundled binaries (`resources/mongo/`, `resources/tesseract/`) are fetched by `scripts/fetch-mongod.ps1` / `fetch-tesseract.ps1`; `.cache/` and `resources/mongo/` are git-ignored.

## Architecture

Strict three-layer, fully synchronous, in-process (no web server):

`app/ui/*` (Tkinter views) → `app/services/*` (business rules, cascades) → `app/repositories/*` (PyMongo, extend `BaseRepository`) → MongoDB.

- `main.py` wires it up: `MongoDatabase.connect()` + `ensure_indexes()`, then `LoginWindow` (auth gate), then `MainWindow(root, db, auth, billing, user)`, which owns the navigation frames (Dashboard, Billing, History, Orders, Masters, Inventory, Procurement, Finance, Admin, Consolidated report).
- `MongoDatabase` (`app/database/connection.py`) exposes `collection(name)`; services/repositories only ever call that. `supports_transactions` is true only on replica sets, so multi-document writes must **gracefully fall back** when it's false (standalone mongod is the normal case).
- **Never create collections or break existing schemas** — repositories attach to existing collections, and `_ensure_index` deliberately skips already-present/conflicting indexes. Field names (`item_alias`, `cust_id`, `bill_to_name`, `invoice_no`, …) follow the legacy schema; `app/models/*` are Pydantic models for these documents.
- Money-moving operations cascade across collections: a bill mutation updates stock (`stock_transactions`), customer balance, ledger journal entries (`ledger_service`, double-entry: debits must equal credits), and `bill_audits`. Voiding a bill posts reversals/contra entries and restores stock. Change these via the services, not by writing collections directly from UI code.
- Pricing resolution (`pricing_service`): customer fixed/contract rate takes precedence over item default rate.
- Invoice numbers follow `YYYYMMDD-XXXX` (`INVOICE_PREFIX_FORMAT`).
- Printing (`app/printing/invoice.py`, `consolidated.py`): ReportLab generates Invoice / Delivery Challan / consolidated statement PDFs (HTML fallback renderers exist); `app/ui/print_preview.py` renders them with PyMuPDF (`fitz`). `ocr_service.py` resolves a Tesseract binary (bundled in `resources/tesseract/win32-x64/`, then PATH, then standard install dirs).
- Billing and Order entry grids (`app/ui/billing.py`, `order_form_view.py`) share the same behavior contract: Code→Qty→Unit→Rate Enter-key traversal, keystroke-by-keystroke line-total recalculation, **gap compaction** (an item entered in a later empty row is moved to the first empty row), and dynamic row append at the table end. Keep the two views behaviorally in sync (recent commits aligned them).

## Testing

- Tests use `fake_db` (an in-memory `MockMongoDatabase`/`MockCollection` in `tests/conftest.py`) and a session-scoped `tk_root` (withdrawn real Tk root — a display/Tk install is required). The mock supports only a subset of Mongo operators (`$or`, `$regex`, `$lte/$gte/$in/$nin/$ne`, `$inc/$set/$push`); extend `MockCollection` if code under test uses other operators or methods (e.g. `skip`, `delete_one` result objects, `aggregate`).
- `conftest.py` contains `TRACEABILITY_MAP` mapping each test function name to an Epic/Story/Task and GitHub issue (sirajpasha/BillDesk_DesktopApp), printed in the pytest terminal summary. **When adding a test, add its entry there** (and the README traceability table) or it won't appear in the report.
- `main.py` and `conftest.py` both set `TCL_LIBRARY`/`TK_LIBRARY` from `sys.prefix` to make Tk reliable on Windows; keep that when creating new entry points.

## Docs

`Docs/` holds the PRD, implementation plan, user guide (with screenshots in `Docs/user-guide/img/`, which UI tests reference, e.g. `13-order-new.png`), and the epics/traceability matrices. `README.ipynb` is generated by `scripts/build_readme_notebook.py`.
