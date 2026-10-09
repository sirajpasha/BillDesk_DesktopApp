"""First start of a fresh installation: create the company, roles and ONE administrator with a random password.

A fresh install must not ship with a known password (the repository's seed data uses admin123 for development only).
Nothing here runs against a database that already has users.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Dict, Optional

import bcrypt

from app import paths
from app.repositories.base import BaseRepository

log = logging.getLogger(__name__)

# Menu permissions understood by MainWindow (admin is always allowed everything).
DEFAULT_ROLE_PERMISSIONS = {
    "manager": ["/items", "/customers", "/suppliers", "/finance", "/accounting", "/ledger"],
    "user": [],
}


def needs_first_run(db: Any) -> bool:
    return db.collection("users").count_documents({}) == 0


def generate_password(length: int = 10) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # no look-alike characters
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _seed() -> Dict[str, Any]:
    f = paths.resource_path("data/seed_data.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def seed_first_run(db: Any, password: Optional[str] = None) -> Dict[str, str]:
    """Create companies, roles, default role permissions and the `admin` user. Returns {'username', 'password'}."""
    if not needs_first_run(db):
        raise RuntimeError("The database already has users; first-run setup refused")
    data = _seed()
    for comp in data.get("companies", []):
        q = {"company_id": comp["company_id"]} if comp.get("company_id") else {"name": comp.get("name")}
        if not db.collection("companies").find_one(q):
            db.collection("companies").insert_one(dict(comp))
    for role in data.get("roles", []):
        if not db.collection("roles").find_one({"name": role.get("name")}):
            db.collection("roles").insert_one(dict(role))
    for role, menus in DEFAULT_ROLE_PERMISSIONS.items():
        if not db.collection("role_permissions").find_one({"role": role}):
            db.collection("role_permissions").insert_one({"role": role, "menus": menus})

    password = password or generate_password()
    db.collection("users").insert_one({
        "user_id": "USER0001", "username": "admin", "roles": ["admin"], "email": "", "phone": "",
        "password_hash": bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8"),
        "status": "active", "is_deleted": 0,
    })
    log.info("First run: created the administrator account (password shown once to the user, not logged)")
    return {"username": "admin", "password": password}
