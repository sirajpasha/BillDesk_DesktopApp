from __future__ import annotations
from typing import Any, Dict, List, Optional
import bcrypt
import uuid
from app.repositories.admin_repo import AdminRepository

class AdminService:
    def __init__(self, db: Any):
        self.db = db
        self.admin_repo = AdminRepository(db)

    # ---------------- USERS ----------------
    def get_users(self) -> List[Dict[str, Any]]:
        users = self.admin_repo.users.find({"is_deleted": 0}, sort=[("username", 1)])
        # Strip password hashes from user-facing lists
        for u in users:
            u.pop("password_hash", None)
            u.pop("password_plain", None)
        return users

    def create_user(self, username: str, password: str, roles: List[str], email: str = "", phone: str = "") -> Dict[str, Any]:
        if not username or not password:
            raise ValueError("Username and password are required")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        if len(password.encode("utf-8")) > 72:
            raise ValueError("Password is too long (maximum 72 bytes)")
        known_roles = {r.get("name") for r in self.admin_repo.roles.find({}, limit=0)}
        unknown = [r for r in roles if r not in known_roles]
        if unknown:
            raise ValueError(f"Unknown role(s): {', '.join(unknown)}")
        if self.admin_repo.users.find_one({"username": username, "is_deleted": 0}):
            raise ValueError(f"User '{username}' already exists")

        pw_hash = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")
        user_id = f"USR-{uuid.uuid4().hex[:6].upper()}"
        doc = {
            "user_id": user_id,
            "username": username,
            "password_hash": pw_hash,
            "roles": roles,
            "email": email,
            "phone": phone,
            "status": "active",
            "is_deleted": 0,
        }
        self.admin_repo.users.insert_one(doc)
        doc.pop("password_hash", None)
        return doc

    def set_password(self, username: str, new_password: str) -> bool:
        """Set a new password (used by scripts/reset_password.py); applies the same rules as create_user."""
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters")
        if len(new_password.encode("utf-8")) > 72:
            raise ValueError("Password is too long (maximum 72 bytes)")
        user = self.admin_repo.users.find_one({"username": username, "is_deleted": 0})
        if not user:
            raise ValueError(f"User '{username}' not found")
        pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        self.admin_repo.users.update_one({"username": username}, {"$set": {"password_hash": pw_hash}})
        return True

    def update_user_status(self, user_id: str, status: str) -> bool:
        return self.admin_repo.users.update_one({"user_id": user_id}, {"$set": {"status": status}})

    # ---------------- ROLES & PERMISSIONS ----------------
    def get_roles(self) -> List[Dict[str, Any]]:
        return self.admin_repo.roles.find({})

    def get_permissions(self, role: str) -> List[str]:
        doc = self.admin_repo.role_permissions.find_one({"role": role})
        return doc.get("menus", []) if doc else []

    def set_permissions(self, role: str, menus: List[str]) -> bool:
        existing = self.admin_repo.role_permissions.find_one({"role": role})
        if existing:
            return self.admin_repo.role_permissions.update_one({"role": role}, {"$set": {"menus": menus}})
        else:
            self.admin_repo.role_permissions.insert_one({"role": role, "menus": menus})
            return True

    # ---------------- SETTINGS ----------------
    def get_settings(self) -> Dict[str, Any]:
        return self.admin_repo.get_settings()

    def update_settings(self, settings_data: Dict[str, Any]) -> bool:
        return self.admin_repo.settings.update_one(
            {"setting_key": "general_config"},
            {"$set": settings_data}
        )
