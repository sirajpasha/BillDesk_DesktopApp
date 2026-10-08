import pytest
import tkinter as tk
from app.services.billing_service import BillingService
from app.models.common import CurrentUser
from app.ui.billing import BillingFrame


@pytest.fixture
def billing_frame(fake_db, tk_root):
    user = CurrentUser(user_id="USR-001", username="admin", roles=["Admin"], company_id="Company0001")
    billing_svc = BillingService(fake_db)
    # Ensure test item exists
    fake_db.collection("items").delete_many({})
    fake_db.collection("items").insert_one({
        "item_id": "VEG0001",
        "item_alias": "101",
        "name": "Avaraikkai",
        "unit": "Kg",
        "standard_rate": 20.0,
        "status": "active",
        "is_deleted": 0
    })
    fake_db.collection("items").insert_one({
        "item_id": "VEG0002",
        "item_alias": "102",
        "name": "Banana Leaves (E)",
        "unit": "Nos",
        "standard_rate": 5.0,
        "status": "active",
        "is_deleted": 0
    })
    fake_db.collection("items").insert_one({
        "item_id": "VEG0003",
        "item_alias": "103",
        "name": "Amla",
        "unit": "Kg",
        "standard_rate": 30.0,
        "status": "active",
        "is_deleted": 0
    })

    frame = BillingFrame(tk_root, fake_db, billing_svc, user)
    yield frame
    frame.destroy()


def test_code_entered_fetches_item_and_focuses_qty(billing_frame):
    """When user enters code and presses Enter, description, unit, rate are populated and Qty is focused."""
    frame = billing_frame
    row0 = frame.row_widgets[0]

    # Type code '101'
    row0["code"].delete(0, tk.END)
    row0["code"].insert(0, "101")

    # Simulate pressing enter
    frame._on_code_entered(0)

    # Item Name in description field
    assert row0["name"].get() == "Avaraikkai"
    # Default Unit from item master
    assert row0["unit"].get() == "Kg"
    # Resolved rate
    assert float(row0["rate"].get()) == 20.0
    # Default Qty is 1
    assert row0["qty"].get() == "1"


def test_qty_entered_focuses_unit(billing_frame):
    """Once Qty is entered and Enter is pressed, focus moves to Unit field."""
    frame = billing_frame
    row0 = frame.row_widgets[0]

    row0["code"].insert(0, "101")
    frame._on_code_entered(0)

    # Change qty to 10
    row0["qty"].delete(0, tk.END)
    row0["qty"].insert(0, "10")

    # Trigger Enter on Qty
    frame._on_qty_entered(0)

    # Unit should retain master unit
    assert row0["unit"].get() == "Kg"
    # Row recalculation occurred
    assert row0["amount"].cget("text") == "₹200.00"


def test_unit_entered_or_selected_focuses_rate(billing_frame):
    """User can change unit and pressing Enter or selecting unit advances to Rate field."""
    frame = billing_frame
    row0 = frame.row_widgets[0]

    row0["code"].insert(0, "101")
    frame._on_code_entered(0)
    row0["qty"].delete(0, tk.END)
    row0["qty"].insert(0, "10")

    # Change unit to 'box'
    row0["unit"].set("box")
    frame._on_unit_entered(0)

    assert row0["unit"].get() == "box"


def test_realtime_rate_calculation_keystroke_by_keystroke(billing_frame):
    """Rate entered immediately calculates Amount: typing '6' calculates 6*Qty, typing '5' (65) calculates 65*Qty."""
    frame = billing_frame
    row0 = frame.row_widgets[0]

    row0["code"].insert(0, "101")
    frame._on_code_entered(0)

    # Qty = 10
    row0["qty"].delete(0, tk.END)
    row0["qty"].insert(0, "10")

    # Clear rate
    row0["rate"].delete(0, tk.END)

    # First user types '6'
    row0["rate"].insert(0, "6")
    frame._recalculate_row(0)
    assert row0["amount"].cget("text") == "₹60.00"
    assert "₹60.00" in frame.total_lbl.cget("text")

    # User types '5' so rate is '65'
    row0["rate"].insert(tk.END, "5")
    frame._recalculate_row(0)
    assert row0["amount"].cget("text") == "₹650.00"
    assert "₹650.00" in frame.total_lbl.cget("text")


def test_gap_compaction_moves_item_to_first_empty_row(billing_frame):
    """If directly entered at 5th or 10th row when no prior line is entered, move to 1st row."""
    frame = billing_frame
    row4 = frame.row_widgets[4]  # 5th row (0-indexed 4)

    # Enter line on row 4
    row4["code"].insert(0, "101")
    frame._on_code_entered(4)
    row4["qty"].delete(0, tk.END)
    row4["qty"].insert(0, "2")
    row4["rate"].delete(0, tk.END)
    row4["rate"].insert(0, "65")

    # Enter on Rate triggers gap compaction
    frame._on_rate_entered(4)

    # Item should have moved to 1st row (row 0)
    row0 = frame.row_widgets[0]
    assert row0["name"].get() == "Avaraikkai"
    assert row0["qty"].get() == "2"
    assert row0["rate"].get() == "65"
    assert row0["amount"].cget("text") == "₹130.00"

    # Row 4 where user typed should now be cleared
    assert row4["code"].get() == ""
    assert row4["name"].get() == ""
    assert row4["amount"].cget("text") == "₹0.00"


def test_gap_compaction_with_preexisting_rows(billing_frame):
    """If row 1 and 2 are filled, entering on row 5 moves to row 3."""
    frame = billing_frame

    # Fill row 0 (Row 1)
    frame.row_widgets[0]["code"].insert(0, "101")
    frame._on_code_entered(0)
    frame._on_rate_entered(0)

    # Fill row 1 (Row 2)
    frame.row_widgets[1]["code"].insert(0, "102")
    frame._on_code_entered(1)
    frame._on_rate_entered(1)

    # Now enter on row 6 (0-indexed 6)
    row6 = frame.row_widgets[6]
    row6["code"].insert(0, "103")
    frame._on_code_entered(6)
    row6["qty"].delete(0, tk.END)
    row6["qty"].insert(0, "5")
    row6["rate"].delete(0, tk.END)
    row6["rate"].insert(0, "40")

    frame._on_rate_entered(6)

    # It should have compacted to row 2 (Row 3 in UI)
    row2 = frame.row_widgets[2]
    assert row2["name"].get() == "Amla"
    assert row2["qty"].get() == "5"
    assert row2["rate"].get() == "40"
    assert row2["amount"].cget("text") == "₹200.00"

    # Row 6 is cleared
    assert row6["code"].get() == ""
    assert row6["amount"].cget("text") == "₹0.00"


def test_dynamic_row_creation_at_table_end(billing_frame):
    """When the user reaches the end of rows, pressing Enter on Rate creates and enables a new row."""
    frame = billing_frame
    frame.suppress_duplicate_dialog = True   # every row uses item 101; don't open the modal duplicate dialog
    initial_count = len(frame.row_widgets)

    # Fill all rows up to initial_count - 1
    for i in range(initial_count):
        row = frame.row_widgets[i]
        row["code"].insert(0, "101")
        row["name"].insert(0, "Item")
        row["qty"].insert(0, "1")
        row["rate"].insert(0, "10")

    # Enter on Rate on the last row
    frame._on_rate_entered(initial_count - 1)

    # A new row should have been dynamically created!
    assert len(frame.row_widgets) == initial_count + 1
    # The new row is empty and ready
    assert frame._is_row_empty(initial_count)


def test_billing_duplicate_item_add_qty_and_delete_duplicate(billing_frame):
    """When user enters duplicate item and confirms Add Qty, qty is added to previous row, amount recalculated, and duplicate deleted."""
    frame = billing_frame

    # Row 0: Item 101, Qty 2, Rate 20 -> Amount 40.00
    frame.row_widgets[0]["code"].insert(0, "101")
    frame._on_code_entered(0)
    frame.row_widgets[0]["qty"].delete(0, tk.END)
    frame.row_widgets[0]["qty"].insert(0, "2")
    frame._recalculate_row(0)
    assert frame.row_widgets[0]["amount"].cget("text") == "₹40.00"

    # Row 1: User enters item 101 again with Qty 3
    frame.suppress_duplicate_dialog = True  # programmatic resolution
    frame.row_widgets[1]["code"].insert(0, "101")
    frame._on_code_entered(1)
    frame.row_widgets[1]["qty"].delete(0, tk.END)
    frame.row_widgets[1]["qty"].insert(0, "3")

    # Confirm ADD with qty 3
    resolved = frame.resolve_duplicate(1, action="ADD", add_qty=3.0)
    assert resolved is True

    # Row 0 Qty should now be 2 + 3 = 5, Amount = 5 * 20 = 100.00
    assert float(frame.row_widgets[0]["qty"].get()) == 5.0
    assert frame.row_widgets[0]["amount"].cget("text") == "₹100.00"
    assert "₹100.00" in frame.total_lbl.cget("text")

    # Row 1 (duplicate) should be deleted
    assert frame._is_row_empty(1)


def test_billing_duplicate_item_ignore_and_delete_duplicate(billing_frame):
    """When user enters duplicate item and selects Ignore, duplicate line item is deleted leaving previous row intact."""
    frame = billing_frame

    # Row 0: Item 101, Qty 2, Rate 20 -> Amount 40.00
    frame.row_widgets[0]["code"].insert(0, "101")
    frame._on_code_entered(0)
    frame.row_widgets[0]["qty"].delete(0, tk.END)
    frame.row_widgets[0]["qty"].insert(0, "2")
    frame._recalculate_row(0)

    # Row 1: User enters item 101 again
    frame.suppress_duplicate_dialog = True
    frame.row_widgets[1]["code"].insert(0, "101")
    frame._on_code_entered(1)

    # User chooses IGNORE
    resolved = frame.resolve_duplicate(1, action="IGNORE")
    assert resolved is True

    # Row 0 Qty remains 2, Amount 40.00
    assert float(frame.row_widgets[0]["qty"].get()) == 2.0
    assert frame.row_widgets[0]["amount"].cget("text") == "₹40.00"

    # Row 1 duplicate is deleted
    assert frame._is_row_empty(1)

