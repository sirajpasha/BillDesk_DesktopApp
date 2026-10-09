"""Where things are, for both a source checkout and a PyInstaller build.

* resource_path(rel)  - read-only files shipped with the app (assets, seed data, mongod.exe)
* user_data_dir()     - writable per-user data (%APPDATA%\\BillDesk): database, logs, backups, output, .env
* output_dir()        - generated PDFs
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Folder that holds the shipped resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    return app_root() / relative


def user_data_dir() -> Path:
    base = os.getenv("BILLDESK_DATA_DIR")
    if base:
        return Path(base)
    return Path(os.getenv("APPDATA") or Path.home()) / "BillDesk"


def output_dir() -> Path:
    """Generated invoices / challans. A source checkout keeps using Docs/Output; an installed build (Program Files is
    read-only) writes under the user's data folder."""
    if is_frozen() or os.getenv("BILLDESK_OUTPUT_DIR"):
        return Path(os.getenv("BILLDESK_OUTPUT_DIR") or user_data_dir() / "output")
    return Path.cwd() / "Docs" / "Output"


def env_file() -> Path:
    """The user-editable configuration file: <data dir>\\.env (a source checkout also reads ./.env)."""
    return user_data_dir() / ".env"
