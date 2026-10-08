import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

from app import paths

ROOT = paths.app_root()
# precedence: real environment > %APPDATA%\BillDesk\.env (installed build) > ./.env (source checkout)
load_dotenv(paths.env_file())
load_dotenv(ROOT / ".env")

@dataclass
class Settings:
    mongodb_url: str = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27018")
    db_name: str = os.getenv("DB_NAME", "sv_billing")
    invoice_prefix_format: str = os.getenv("INVOICE_PREFIX_FORMAT", "{date}-{seq:04d}")
    default_company_name: str = os.getenv("DEFAULT_COMPANY_NAME", "SV Vegetables & Fruits")
    default_currency_symbol: str = os.getenv("DEFAULT_CURRENCY_SYMBOL", "₹")
    default_unit: str = os.getenv("DEFAULT_UNIT", "Kg")
    default_rate: float = float(os.getenv("DEFAULT_RATE", "20.0"))
    default_num_rows: int = int(os.getenv("DEFAULT_NUM_ROWS", "20"))
    # Percent of the order/bill items total charged as commission / mandi fee. 0 = none (no real order or bill
    # has ever carried either). Set e.g. COMMISSION_RATE=5 in .env to charge 5 %.
    commission_rate: float = float(os.getenv("COMMISSION_RATE", "0") or 0)
    mandi_fee_rate: float = float(os.getenv("MANDI_FEE_RATE", "0") or 0)
    parked_bills_file: str = os.getenv("PARKED_BILLS_FILE", "")      # default: %APPDATA%\BillDesk\parked_bills.json
    backup_dir: str = os.getenv("BACKUP_DIR", "")                      # default: %APPDATA%\\BillDesk\\backups
    backup_enabled: bool = os.getenv("AUTO_BACKUP", "true").strip().lower() in ("1", "true", "yes")
    backup_max_age_hours: float = float(os.getenv("BACKUP_MAX_AGE_HOURS", "24") or 24)
    # Name of a single-node replica set to run the bundled MongoDB as (e.g. rs0). Required for transactions: a failure
    # in the middle of saving a bill then leaves no half-written data. Empty = plain standalone server.
    mongo_replica_set: str = os.getenv("MONGO_REPLICA_SET", "")
    allow_negative_stock: bool = os.getenv("ALLOW_NEGATIVE_STOCK", "true").strip().lower() in ("1", "true", "yes")
    app_title: str = os.getenv("APP_TITLE", "BillDesk — Native Mandi POS & ERP")

settings = Settings()
