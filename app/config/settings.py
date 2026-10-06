import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
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
    app_title: str = os.getenv("APP_TITLE", "BillDesk — Native Mandi POS & ERP")

settings = Settings()
