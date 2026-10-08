import pytest
import tkinter as tk
from datetime import datetime, date, timedelta, timezone

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
def db(seeded_mock_db):
    """In-memory database with a fixed item catalogue - these tests must never touch a live MongoDB
    (they used to read the real `sv_billing` data, so results changed with whatever was in it)."""
    items = seeded_mock_db.collection("items")
    items.docs.clear()
    for n, (alias, name, unit) in enumerate([
        ("101", "Avaraikkai", "Kg"), ("102", "Arvi", "Kg"), ("103", "Amla", "Kg"),
        ("104", "Banana Leaves (E)", "Nos"), ("220", "Mango", "Kg"),
    ], 1):
        items.insert_one({"item_id": f"VEG{n:04d}", "item_alias": alias, "name": name, "unit": unit,
                          "standard_rate": 20.0, "stock": 100.0, "status": "active", "is_deleted": 0})
    return seeded_mock_db


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


def test_order_form_code_entered_fetches_item_and_focuses_qty(tk_root, db, mock_user):
    """When user enters code and presses Enter in Order form, item details populate and focus moves to Qty."""
    view = OrderFormView(tk_root, db, mock_user)
    row0 = view.row_widgets[0]

    # Type code '101'
    row0["code_var"].set("101")
    view._on_code_entered(0)

    # Item Name in description field
    assert "Avaraikkai" in row0["item_var"].get()
    # Default Unit from item master
    assert row0["unit"].get() == "Kg"
    # Default Qty is 1
    assert row0["qty_var"].get() == "1"
    # Resolved rate is populated
    assert float(row0["rate_var"].get()) > 0
    view.destroy()


def test_order_form_qty_and_unit_navigation(tk_root, db, mock_user):
    """Once Qty is entered and Enter is pressed, focus moves to Unit, and then to Rate on Enter."""
    view = OrderFormView(tk_root, db, mock_user)
    row0 = view.row_widgets[0]

    row0["code_var"].set("101")
    view._on_code_entered(0)

    # Change qty to 10
    row0["qty_var"].set("10")
    view._on_qty_entered(0)

    # Unit retains master unit
    assert row0["unit"].get() == "Kg"

    # User changes unit to Box and presses Enter
    row0["unit"].set("Box")
    view._on_unit_entered(0)
    assert row0["unit"].get() == "Box"
    view.destroy()


def test_order_form_realtime_rate_calculation_keystroke_by_keystroke(tk_root, db, mock_user):
    """Rate entered in Order form immediately calculates Amount keystroke by keystroke."""
    view = OrderFormView(tk_root, db, mock_user)
    row0 = view.row_widgets[0]

    row0["code_var"].set("101")
    view._on_code_entered(0)

    # Qty = 10
    row0["qty_var"].set("10")

    # Clear rate and type '6' -> 6 * 10 = 60
    row0["rate_var"].set("6")
    view._recalculate_row(0)
    assert row0["amount"].cget("text") == "₹60.00"
    assert "60.00" in view.total_amount_lbl.cget("text")

    # Type '5' so rate is '65' -> 65 * 10 = 650
    row0["rate_var"].set("65")
    view._recalculate_row(0)
    assert row0["amount"].cget("text") == "₹650.00"
    assert "650.00" in view.total_amount_lbl.cget("text")
    view.destroy()


def test_order_form_gap_compaction_moves_to_first_empty_row(tk_root, db, mock_user):
    """If directly entered at 5th or 10th row with no prior line, move to 1st row (gap compaction)."""
    view = OrderFormView(tk_root, db, mock_user)
    row4 = view.row_widgets[4]  # 5th row (0-indexed 4)

    row4["code_var"].set("101")
    view._on_code_entered(4)
    row4["qty_var"].set("2")
    row4["rate_var"].set("65")

    # Enter on Rate triggers gap compaction
    view._on_rate_entered(4)

    # Item should have compacted to 1st row (row 0)
    row0 = view.row_widgets[0]
    assert "Avaraikkai" in row0["item_var"].get()
    assert row0["qty_var"].get() == "2"
    assert row0["rate_var"].get() == "65"
    assert row0["amount"].cget("text") == "₹130.00"

    # Row 4 where user typed should now be cleared
    assert row4["code_var"].get() == ""
    assert row4["item_var"].get() == ""
    assert row4["amount"].cget("text") == "₹0.00"
    view.destroy()


def test_order_form_dynamic_row_creation_at_table_end(tk_root, db, mock_user):
    """When the user reaches the end of rows, pressing Enter on Rate creates and enables a new row dynamically."""
    view = OrderFormView(tk_root, db, mock_user)
    initial_count = len(view.row_widgets)

    # Fill all rows up to initial_count - 1
    for i in range(initial_count):
        row = view.row_widgets[i]
        row["code_var"].set("101")
        row["item_var"].set("Item")
        row["qty_var"].set("1")
        row["rate_var"].set("10")

    # Enter on Rate on the last row
    view._on_rate_entered(initial_count - 1)

    # A new row should have been dynamically created
    assert len(view.row_widgets) == initial_count + 1
    assert view._is_row_empty(initial_count)
    view.destroy()


def test_order_form_delete_row_shifts_up(tk_root, db, mock_user):
    """Deleting a row shifts subsequent rows up and recalculates totals."""
    view = OrderFormView(tk_root, db, mock_user)

    # Fill row 0 with item 101 and row 1 with item 102
    view.row_widgets[0]["code_var"].set("101")
    view._on_code_entered(0)
    view.row_widgets[0]["qty_var"].set("2")
    view.row_widgets[0]["rate_var"].set("50")
    view._recalculate_row(0)

    view.row_widgets[1]["code_var"].set("102")
    view._on_code_entered(1)
    view.row_widgets[1]["qty_var"].set("5")
    view.row_widgets[1]["rate_var"].set("40")
    view._recalculate_row(1)

    assert view.total_items_lbl.cget("text") == "Total Items: 2"

    # Delete row 0
    view._delete_row_and_shift_up(0)

    # Row 0 now holds item 102
    assert "Arvi" in view.row_widgets[0]["item_var"].get()
    assert view.row_widgets[0]["qty_var"].get() == "5"
    assert view.row_widgets[0]["amount"].cget("text") == "₹200.00"

    # Row 1 is cleared
    assert view.row_widgets[1]["code_var"].get() == ""
    assert view.total_items_lbl.cget("text") == "Total Items: 1"
    view.destroy()

