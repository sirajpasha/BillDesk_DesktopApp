# BillDesk - Operations Guide

## Where things live (Windows)

| What | Where |
| :-- | :-- |
| Database files (bundled MongoDB) | `%APPDATA%\BillDesk\db` |
| Automatic and manual backups | `%APPDATA%\BillDesk\backups` (`billdesk_<db>_<date>_<time>_auto\|manual.zip`) |
| Application log | `%APPDATA%\BillDesk\logs\billdesk.log` (rotates at 2 MB, 5 files kept) |
| Parked bills | `%APPDATA%\BillDesk\parked_bills.json` |
| Invoice / challan PDFs | `Docs\Output` (installed build: `%APPDATA%\BillDesk\output`) |

## Backups

* **Automatic:** once a day while BillDesk is in use (a background thread; billing is never blocked). Each backup is a zip with one `<collection>.jsonl` per collection plus a `manifest.json`, and it is **verified** (re-read and counted) before it replaces the temporary file. Retention: the newest 14 automatic backups plus the newest one of each of the last 12 months. Manual backups are never deleted automatically.
* **Manual:** *Settings > Database Settings > Back Up Now*.
* **Where else:** copy `%APPDATA%\BillDesk\backups` to another disk / cloud folder regularly - a backup on the same disk does not protect against disk failure.
* A real production database (≈53,000 documents) backs up in about 2 seconds to a ≈2 MB file.

### Restore

```powershell
# Safe default: load into a NEW database, counts are verified
python scripts\restore_backup.py "%APPDATA%\BillDesk\backups\billdesk_sv_billing_20261010_020000_auto.zip" --target-db sv_billing_restored
# then set DB_NAME=sv_billing_restored in .env (after checking the data), or:

# Replace the live data (stop BillDesk first; you must type the database name to confirm)
python scripts\restore_backup.py <backup.zip> --target-db sv_billing --replace
```

Practise a restore into a spare database once, before you need it.

## Settings (`.env` or environment)

| Variable | Default | Meaning |
| :-- | :-- | :-- |
| `AUTO_BACKUP` | `true` | automatic daily backup |
| `BACKUP_DIR` | `%APPDATA%\BillDesk\backups` | where backups are written |
| `BACKUP_MAX_AGE_HOURS` | `24` | take an automatic backup when the last one is older than this |
| `BILLDESK_LOG_DIR` | `%APPDATA%\BillDesk\logs` | log folder |
| `PARKED_BILLS_FILE` | `%APPDATA%\BillDesk\parked_bills.json` | parked bills file |
| `COMMISSION_RATE`, `MANDI_FEE_RATE` | `0` | percent charged on orders/bills |
| `ALLOW_NEGATIVE_STOCK` | `true` | `false` refuses sales beyond recorded stock |

## When something goes wrong

1. Note what you were doing and the time.
2. *Settings > Database Settings > Open Log File* (or open `billdesk.log`) - unexpected errors are recorded with the full traceback. The app also shows a "Something went wrong" message with the log path (at most once every 5 seconds).
3. Do not delete the newest backup; send the log.

## Integrity check

*Accounts > Integrity Check* (or `python scripts/integrity_check.py`, exit code 1 if anything FAILS) runs 13 read-only checks: journal and trial-balance balance, balance sheet, Receivables ledger vs customer balances, each customer's balance vs open bills and payments, bill arithmetic and status, payment allocations, invoice numbering, ledger coverage, void reversals, dangling references, stock and supplier balances. Run it after a backfill, after restoring a backup, and from time to time.

* **FAIL** = the data contradicts itself - investigate. **WARNING** = needs a look (often legacy data or an opening balance). **NOTE** = information.
* It never writes anything.

## Moving existing data into the ledger (one time)

1. *Back Up Now* (Database Settings).
2. `python scripts/backfill_ledger.py` - dry run, shows what would be posted.
3. `python scripts/backfill_ledger.py --apply`.
4. Post cash/bank/stock/capital opening balances with *Accounting Dashboard > Set Opening Balance*.
5. Run the Integrity Check and read the Balance Sheet.

The backfill books each customer's recorded balance as their receivable. Where old bills minus recorded payments say the customer owes more or less than that balance, the difference is booked as an unrecorded receipt (assumed **Cash**; `--settle-method Bank`) or as an opening balance against Equity. `--no-settle` skips this. Because most historic payments were never recorded, the resulting **Cash on Hand is an assumption, not a count** - replace it with a real opening cash figure.

## Atomic saves (transactions)

Saving a bill touches several records (the bill, stock, the customer balance, the ledger, the payment). On a plain **standalone** MongoDB a crash in the middle leaves some of them written and some not - verified: a failed *void* left stock restored and the customer credited while the bill still showed as unpaid. On a **replica set** the whole save is one transaction: either everything is stored or nothing is.

* Turn it on: set `MONGO_REPLICA_SET=rs0` in `%APPDATA%\BillDesk\.env` (or `.env` in a source checkout) and start BillDesk. BillDesk starts its bundled MongoDB as a single-node replica set and initialises it by itself - no extra software, no cluster.
* **Existing data is kept**: the same data folder is simply started with `--replSet` (verified with an automated test that converts a standalone data folder and checks every record and index).
* If a standalone MongoDB is already running on that port (for example one started by `start.ps1`), BillDesk cannot convert it and logs a warning - stop that MongoDB, then start BillDesk.
* Nothing else changes for users. Operations covered: bill save (with payment, stock, ledger), void, payments (customer and supplier), order -> bill / purchase conversion, goods receipt, purchase bill, stock adjustment, waste.

## Installing and building (Windows)

**First start of a new installation:** BillDesk starts its own MongoDB (data in `%APPDATA%\BillDesk\db`), creates the company, roles and **one administrator with a random password that is shown once** - write it down. Forgot it later? `python scripts/reset_password.py --user admin`.

**Configuration** lives in `%APPDATA%\BillDesk\.env` (same variables as above; create the file if you need one).

**Building the installer** (needs Python 3.10+, `pip install -r requirements-dev.txt`, Inno Setup 6, and `resources\mongo\win32-x64\mongod.exe` - `scripts\fetch-mongod.ps1` downloads it):

```powershell
.\build_windows.ps1                 # tests -> PyInstaller -> self-test of the built exe -> dist\BillDesk-Setup.exe
.\build_windows.ps1 -SkipTests -Version 1.1.0
```

The build **fails** unless the packaged `dist\BillDesk\BillDesk.exe --selftest` passes: it starts a throw-away MongoDB replica set in a temp folder, runs first-run setup and login, saves a bill with a counter payment inside a transaction, proves a failed save leaves no trace, generates the invoice and delivery-challan PDFs, backs up and restores, and runs the integrity check. Run the same check on any installed copy: `BillDesk.exe --selftest` (output is also in the log folder).

* Installer: per-user by default (no administrator rights; the setup also offers an all-users install), Start Menu entry, optional desktop icon / start-with-Windows, refuses to install over a running BillDesk. **Uninstalling keeps `%APPDATA%\BillDesk`** (database, backups, logs).
* Silent install for scripts: `BillDesk-Setup.exe /VERYSILENT /CURRENTUSER /NORESTART /DIR="C:\BillDesk"` (`/CURRENTUSER` or `/ALLUSERS` is required, otherwise setup waits at its "install mode" dialog).
* Only one BillDesk window can run per computer.
* The 148 MB Tesseract OCR engine is **not** bundled (the OCR feature is not built yet); `INCLUDE_TESSERACT=1` adds it.
