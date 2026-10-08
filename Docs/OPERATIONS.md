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
