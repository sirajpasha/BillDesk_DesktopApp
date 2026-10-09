"""Regression tests for D-03 (seeded DB must be usable) and D-04 (role permissions enforced)."""
from tkinter import messagebox

import pytest

from app.repositories.master_repo import CustomerRepository, ItemRepository
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService

from conftest import SeederDbAdapter


@pytest.fixture
def seeded(seeder, fake_db):
    for name in ("items", "customers", "suppliers"):
        fake_db.collection(name).docs.clear()
    seeder.seed_collections(SeederDbAdapter(fake_db), seeder.load_seed_json(), [])
    return fake_db


def test_seeded_database_allows_login_and_billing_lookups(seeded):
    user = AuthService(seeded).login("admin", "admin123")
    assert user.username == "admin"
    assert ItemRepository(seeded).find_by_alias_or_id("101")["name"] == "Apple"
    assert CustomerRepository(seeded).search_customers("Anna")
    assert BillingService(seeded).search_items("apple")


def test_seed_is_idempotent_and_repairs_legacy_records(seeder, fake_db):
    for name in ("items", "customers", "suppliers"):
        fake_db.collection(name).docs.clear()
    # record written by the old seeder: no status / is_deleted
    fake_db.collection("users").insert_one({"user_id": "U9", "username": "legacy", "roles": ["user"]})
    seeder.seed_collections(SeederDbAdapter(fake_db), seeder.load_seed_json(), [])
    n_items = fake_db.collection("items").count_documents({})
    seeder.seed_collections(SeederDbAdapter(fake_db), seeder.load_seed_json(), [])
    assert fake_db.collection("items").count_documents({}) == n_items
    legacy = fake_db.collection("users").find_one({"username": "legacy"})
    assert legacy["status"] == "active" and legacy["is_deleted"] == 0


def test_seed_creates_default_role_permissions(seeded):
    mgr = seeded.collection("role_permissions").find_one({"role": "manager"})
    assert "/finance" in mgr["menus"]
    assert seeded.collection("role_permissions").find_one({"role": "user"})["menus"] == []


# ------------------------------------------------------------------ D-04
@pytest.fixture
def make_window(seeded, tk_root, monkeypatch):
    warnings = []
    monkeypatch.setattr(messagebox, "showwarning", lambda t=None, m=None, **k: warnings.append((t, m)))
    from app.ui.main_window import MainWindow

    def build(username, password):
        auth = AuthService(seeded)
        user = auth.login(username, password)
        win = MainWindow(tk_root, seeded, auth, BillingService(seeded), user)
        win.warnings = warnings
        return win
    return build


def test_basic_user_cannot_open_restricted_pages(make_window):
    win = make_window("user", "user123")
    win.show_page("New Bill")
    for page in ("Item Master", "Customer Master", "Finance", "Profit & Loss", "Trial Balance", "User Management", "DB Connection"):
        win.show_page(page)
        assert win.active_page == "New Bill", f"{page} opened for basic user"
    assert win.warnings and win.warnings[-1][0] == "Access Denied"
    assert not {"Masters", "Accounts", "Settings"} & set(win.menus_config)
    assert not {"Profit & Loss", "Balance Sheet"} & {m[1] for m in win.menus_config["Reports"]}


def test_basic_user_keyboard_shortcuts_are_blocked(make_window, tk_root):
    win = make_window("user", "user123")
    win.show_page("New Bill")
    for seq in ("<F10>", "<F11>", "<Control-d>"):
        tk_root.event_generate(seq)
        tk_root.update()
        assert win.active_page == "New Bill", f"{seq} bypassed access control"


def test_manager_can_open_masters_and_finance_but_not_settings(make_window):
    win = make_window("manager", "manager123")
    for page in ("Item Master", "Finance", "Profit & Loss"):
        win.show_page(page)
        assert win.active_page == page
    win.show_page("User Management")
    assert win.active_page != "User Management"
    assert "Settings" not in win.menus_config


def test_admin_can_open_everything(make_window):
    win = make_window("admin", "admin123")
    for page in ("Item Master", "Finance", "User Management", "DB Connection", "Profit & Loss"):
        win.show_page(page)
        assert win.active_page == page
