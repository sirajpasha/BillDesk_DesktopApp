from __future__ import annotations
from datetime import datetime, timezone
import uuid
import bcrypt
from app.models.common import CurrentUser

class AuthService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def login(self, username: str, password: str) -> CurrentUser:
        user = self.db.collection("users").find_one({"username": username, "status": "active", "is_deleted": 0})
        if not user or not self.verify_password(password, user.get("password_hash", "")):
            raise ValueError("Invalid username or password")
        current = CurrentUser(
            user_id=user["user_id"], username=user["username"], roles=user.get("roles", []), company_id=user.get("company_id")
        )
        self.db.collection("user_activity_audits").insert_one({
            "audit_id": f"AUD-{uuid.uuid4().hex[:10].upper()}",
            "user_id": current.user_id,
            "username": current.username,
            "timestamp": datetime.now(timezone.utc),
            "action": "login",
            "details": {"method": "password", "client": "native"},
            "ip_address": "local",
            "device_type": "Desktop",
            "user_agent": "BillDesk Native",
        })
        return current

    def permissions_for(self, user: CurrentUser) -> set[str]:
        permissions = set()
        for role in user.roles:
            doc = self.db.collection("role_permissions").find_one({"role": role})
            if doc:
                permissions.update(doc.get("menus", []))
        # Admin-like roles are allowed through the native app shell.
        if any(r.lower() in {"admin", "super admin"} for r in user.roles):
            return {"*"}
        return permissions
