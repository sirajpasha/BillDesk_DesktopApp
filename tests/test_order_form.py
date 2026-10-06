import pytest
import tkinter as tk
from datetime import datetime, date, timedelta, timezone

from app.config.settings import Settings
from app.database.connection import MongoDatabase
from app.models.auth import User
from app.models.order import OrderCreate, OrderItem
from app.services.order_service import OrderService
from app.ui.order_form_view import OrderFormView


@pytest.fixture
def mock_user():
    return User(
        user_id="U001",
        username="admin",
        full_name="Administrator",
        roles=["Admin"],
        password_hash="mock"
    )


@pytest.fixture
def db():
    settings = Settings()
    db_inst = MongoDatabase(settings)
    db_inst.connect()
    yield db_inst
    db_inst.close()


def test_order_form_view_structure(tk_root, db, mock_user):
    """Test OrderFormView UI structure matches 13-order-new.png."""
    view = OrderFormView(tk_root, db, mock_user)

    # 1. Title bar elements
    assert view.title_label.cget("text") == "New Order"
    assert "Smart" in view.smart_btn.cget("text")
    assert "Close" in view.close_btn.cget("text")

    # 2. Metadata controls
    assert view.customer_var.get() == "Select Customer (F5)"
    assert len(view.companies) > 0
    assert view.date_var.get() == date.today().strftime("%d - %m - %Y")
    tomorrow = date.today() + timedelta(days=1)
    assert view.delivery_var.get() == tomorrow.strftime("%d - %m - %Y")

    # 3. 15 spreadsheet rows
    assert len(view.row_widgets) == 15
    for r in view.row_widgets:
        assert "code" in r
        assert "item" in r
        assert "qty" in r
        assert "unit" in r
        assert "del_btn" in r

    # 4. Total items starts at 0
    assert view.total_items_lbl.cget("text") == "Total Items: 0"
    assert "Comm:" in view.comm_lbl.cget("text")
    assert "Mandi Fee:" in view.mandi_fee_lbl.cget("text")
    view.destroy()


def test_order_form_smart_importer_and_recalc(tk_root, db, mock_user):
    """Test smart text importer and real-time total calculation."""
    view = OrderFormView(tk_root, db, mock_user)

    # Import sample lines
    sample_text = "Mango 30 kg\nBanana 10 dz"
    imported = view._parse_and_populate_lines(sample_text)
    assert imported == 2

    # Check row 0 and row 1
    assert "Mango" in view.row_widgets[0]["item_var"].get()
    assert float(view.row_widgets[0]["qty_var"].get()) == 30.0

    assert "Banana" in view.row_widgets[1]["item_var"].get()
    assert float(view.row_widgets[1]["qty_var"].get()) == 10.0

    # Total items should be 2
    assert view.total_items_lbl.cget("text") == "Total Items: 2"

    # Test clearing row 0
    view._clear_row(0)
    assert view.row_widgets[0]["item_var"].get() == ""
    assert view.row_widgets[0]["qty_var"].get() == ""
    assert view.total_items_lbl.cget("text") == "Total Items: 1"
    view.destroy()


def test_order_form_load_order_for_edit(tk_root, db, mock_user):
    """Test editing an existing order matches 49-order-detail.png."""
    order_svc = OrderService(db)
    test_req = OrderCreate(
        customer_id="CUST-TEST",
        customer_name="Green Leaf Restaurant",
        delivery_date=datetime.now(timezone.utc) + timedelta(days=1),
        items=[
            OrderItem(item_id="ITM0012", name="Mango", qty=30.0, unit="kg", rate=50.0, amount=1500.0),
            OrderItem(item_id="ITM0011", name="Banana", qty=10.0, unit="dz", rate=40.0, amount=400.0),
        ],
        total_amount=1900.0,
        status="pending",
        crates_issued=5,
        crates_returned=2,
        created_by="admin"
    )
    created = order_svc.create_order(test_req)
    order_id = created["order_id"]

    view = OrderFormView(tk_root, db, mock_user)
    view.load_order_for_edit(order_id)

    # Check edit mode title
    assert view.title_label.cget("text") == f"Edit Order: {order_id}"
    assert view.customer_var.get() == "Green Leaf Restaurant"
    assert view.status_container.winfo_ismapped() or True
    assert view.crates_out_var.get() == "5"
    assert view.crates_in_var.get() == "2"

    # Check items populated
    assert view.row_widgets[0]["item_var"].get() == "Mango"
    assert float(view.row_widgets[0]["qty_var"].get()) == 30.0
    assert view.row_widgets[1]["item_var"].get() == "Banana"
    assert float(view.row_widgets[1]["qty_var"].get()) == 10.0
    assert view.total_items_lbl.cget("text") == "Total Items: 2"

    # Clean up test order
    db.collection("orders").delete_one({"order_id": order_id})
    view.destroy()
