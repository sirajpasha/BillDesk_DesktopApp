from app.services.billing_service import BillingService
from app.services.auth_service import AuthService
from app.models.common import CurrentUser
from app.ui.login_window import LoginWindow
from app.ui.dashboard import DashboardFrame
from app.ui.billing import BillingFrame
from app.ui.history import BillHistoryFrame
from app.ui.masters_view import MastersView
from app.ui.orders_view import OrdersView
from app.ui.finance_view import FinanceView

def test_all_ui_views_visual_structure(fake_db, tk_root):
    """Verify that all views matching Docs/user-guide/img instantiate with expected KPI cards and tables."""
    root = tk_root
    user = CurrentUser(user_id="USR-ADMIN", username="admin", roles=["Admin"], company_id="Company0001")
    billing = BillingService(fake_db)
    auth = AuthService(fake_db)

    # 1. LoginWindow (01-login.png)
    login_win = LoginWindow(root, auth, on_login_success=lambda u: None)
    assert login_win.username_entry is not None
    assert login_win.password_entry is not None

    # 2. DashboardFrame (02-dashboard.png)
    dash = DashboardFrame(root, fake_db, billing, user)
    assert len(dash.card_widgets) >= 6
    dash.refresh()

    # 3. BillingFrame (04-billing-empty.png, 06-billing-filled.png)
    billing_frame = BillingFrame(root, fake_db, billing, user)
    assert len(billing_frame.rows) >= 15
    assert hasattr(billing_frame, "total_label")

    # 4. BillHistoryFrame (08-bills-history.png)
    hist = BillHistoryFrame(root, fake_db, billing, current_user=user)
    assert hist.card_total_bills_val is not None
    assert hist.card_total_rev_val is not None
    assert hist.card_today_bills_val is not None
    hist.refresh()

    # 5. MastersView (09-customers.png, 10-items.png, 11-suppliers.png)
    masters = MastersView(root, fake_db)
    assert hasattr(masters, "items_tree")
    assert hasattr(masters, "cust_tree")
    assert hasattr(masters, "supp_tree")
    assert hasattr(masters, "pricing_tree")

    # 6. OrdersView (12-orders.png, 24-order-matrix.png)
    orders = OrdersView(root, fake_db, current_user=user)
    assert hasattr(orders, "orders_tree")
    assert hasattr(orders, "matrix_tree_frame")

    # 7. FinanceView (25-accounting-home.png)
    fin = FinanceView(root, fake_db, current_user=user)
    assert hasattr(fin, "kpi_home_ar")
    assert hasattr(fin, "kpi_home_ap")
    assert hasattr(fin, "kpi_home_bank")
    assert hasattr(fin, "kpi_home_profit")

def test_customer_master_dc_company_fetching(fake_db, tk_root):
    """Verify that DC Company Name column in Customer master fetches bill_to_name from DB."""
    fake_db.collection("companies").insert_one({
        "company_id": "Company0001",
        "name": "SV Vegetables & Fruits"
    })
    fake_db.collection("customers").insert_one({
        "cust_id": "Cust0002",
        "name": "Anna Adarsh College",
        "company_id": "Company0001",
        "dc_company_id": "Company0003",
        "bill_to_name": "SRINIVASA TRADERS",
        "phone": "9444434066",
        "address": "Anna Nagar, Chennai",
        "current_balance": 0.0,
        "is_deleted": 0
    })

    masters = MastersView(tk_root, fake_db)
    masters.load_customers()

    item = masters.cust_tree.item("Cust0002")
    assert item is not None
    vals = item["values"]
    # ("company", "dc_company", "name", "phone", "address", "balance", "status")
    assert vals[0] == "SV Vegetables & Fruits"
    assert vals[1] == "SRINIVASA TRADERS"
    assert vals[2] == "Anna Adarsh College"
    assert str(vals[3]) == "9444434066"
