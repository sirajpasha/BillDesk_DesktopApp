import os
import pytest
from app.services.billing_service import BillingService
from app.printing.consolidated import generate_consolidated_report_pdf
from app.ui.consolidated_view import ConsolidatedReportFrame, _normalize_date_to_iso, _format_iso_to_display


def test_date_helpers():
    assert _normalize_date_to_iso("30-08-2026") == "2026-08-30"
    assert _normalize_date_to_iso("30/08/2026") == "2026-08-30"
    assert _normalize_date_to_iso("2026-08-30") == "2026-08-30"
    assert _format_iso_to_display("2026-08-30") == "30-08-2026"


def test_consolidated_report_aggregation(fake_db):
    service = BillingService(fake_db)

    # 1. Setup Customers with shared bill_to_name
    fake_db.collection("customers").insert_one({
        "cust_id": "CUST_TEST_1",
        "name": "Branch Alpha",
        "bill_to_name": "Mega Hospitality Group",
        "bill_to_address": "Main Street, Chennai",
        "bill_to_phone": "9998887776",
        "is_deleted": 0,
        "status": "active"
    })
    fake_db.collection("customers").insert_one({
        "cust_id": "CUST_TEST_2",
        "name": "Branch Beta",
        "bill_to_name": "Mega Hospitality Group",
        "bill_to_address": "Main Street, Chennai",
        "bill_to_phone": "9998887776",
        "is_deleted": 0,
        "status": "active"
    })

    # 2. Setup Bills
    # Bill 1 for Branch Alpha: Onion 10kg @ 60 = 600, Potato 5kg @ 40 = 200 => Total 800
    fake_db.collection("bills").insert_one({
        "invoice_no": "INV-001",
        "invoice_date": "2026-09-01",
        "customer_id": "CUST_TEST_1",
        "customer_name": "Branch Alpha",
        "total_amount": 800.0,
        "status": "active",
        "is_deleted": 0,
        "items": [
            {"item_id": "ITM_ONION", "name": "Onion", "qty": 10.0, "unit": "kg", "rate": 60.0, "amount": 600.0},
            {"item_id": "ITM_POTATO", "name": "Potato", "qty": 5.0, "unit": "kg", "rate": 40.0, "amount": 200.0}
        ]
    })
    # Bill 2 for Branch Alpha: Onion 10kg @ 70 = 700 => Total 700.
    # Total Onion for Alpha: 20kg, Total amount: 1300, Avg Rate: 1300/20 = 65.0
    fake_db.collection("bills").insert_one({
        "invoice_no": "INV-002",
        "invoice_date": "2026-09-03",
        "customer_id": "CUST_TEST_1",
        "customer_name": "Branch Alpha",
        "total_amount": 700.0,
        "status": "active",
        "is_deleted": 0,
        "items": [
            {"item_id": "ITM_ONION", "name": "Onion", "qty": 10.0, "unit": "kg", "rate": 70.0, "amount": 700.0}
        ]
    })
    # Bill 3 for Branch Beta: Onion 10kg @ 50 = 500, Tomato 8kg @ 25 = 200 => Total 700
    fake_db.collection("bills").insert_one({
        "invoice_no": "INV-003",
        "invoice_date": "2026-09-04",
        "customer_id": "CUST_TEST_2",
        "customer_name": "Branch Beta",
        "total_amount": 700.0,
        "status": "active",
        "is_deleted": 0,
        "items": [
            {"item_id": "ITM_ONION", "name": "Onion", "qty": 10.0, "unit": "kg", "rate": 50.0, "amount": 500.0},
            {"item_id": "ITM_TOMATO", "name": "Tomato", "qty": 8.0, "unit": "kg", "rate": 25.0, "amount": 200.0}
        ]
    })
    # Cancelled bill that should be excluded
    fake_db.collection("bills").insert_one({
        "invoice_no": "INV-CANCELLED",
        "invoice_date": "2026-09-02",
        "customer_id": "CUST_TEST_1",
        "customer_name": "Branch Alpha",
        "total_amount": 9999.0,
        "status": "cancelled",
        "is_deleted": 0,
        "items": [
            {"item_id": "ITM_ONION", "name": "Onion", "qty": 100.0, "unit": "kg", "rate": 60.0, "amount": 6000.0}
        ]
    })

    # Test report by Bill To Name
    rep = service.get_consolidated_report(
        customer_id_or_name="Mega Hospitality Group",
        start_date="2026-09-01",
        end_date="2026-09-10"
    )

    assert rep["bill_to"] == "Mega Hospitality Group"
    assert rep["total_bill_amount"] == 2200.0  # 800 + 700 + 700
    assert len(rep["bill_summary"]) == 3
    assert len(rep["ship_to_reports"]) == 2

    # Check Branch Alpha consolidation
    alpha_rep = next(s for s in rep["ship_to_reports"] if s["ship_to"] == "Branch Alpha")
    assert alpha_rep["total_amount"] == 1500.0
    alpha_onion = next(i for i in alpha_rep["items"] if i["name"] == "Onion")
    assert alpha_onion["qty"] == 20.0
    assert alpha_onion["amount"] == 1300.0
    assert alpha_onion["rate"] == 65.0  # Weighted average

    # Check Grand Total consolidation
    grand_onion = next(i for i in rep["grand_total_consolidation"] if i["name"] == "Onion")
    assert grand_onion["qty"] == 30.0  # 20 + 10
    assert grand_onion["amount"] == 1800.0  # 1300 + 500
    assert grand_onion["rate"] == 60.0  # 1800 / 30 = 60.0


def test_unique_bill_to_entities(fake_db):
    service = BillingService(fake_db)
    fake_db.collection("customers").insert_one({
        "cust_id": "C1",
        "name": "Branch 1",
        "bill_to_name": "Parent Corp",
        "is_deleted": 0
    })
    fake_db.collection("customers").insert_one({
        "cust_id": "C2",
        "name": "Branch 2",
        "bill_to_name": "Parent Corp",
        "is_deleted": 0
    })
    fake_db.collection("customers").insert_one({
        "cust_id": "C3",
        "name": "Independent Hotel",
        "bill_to_name": "",
        "is_deleted": 0
    })
    fake_db.collection("customers").insert_one({
        "cust_id": "CASH",
        "name": "Cash Sale",
        "bill_to_name": "Cash",
        "is_deleted": 0
    })

    entities = service.get_unique_bill_to_entities()
    names = [e["name"] for e in entities]
    assert "Parent Corp" in names
    assert "Independent Hotel" in names
    assert "Cash" not in names
    assert names.count("Parent Corp") == 1


def test_generate_consolidated_pdf(tmp_path):
    report_mock = {
        "bill_to": "Mega Hospitality Group",
        "date_range": {"start": "2026-08-30", "end": "2026-10-05"},
        "bill_summary": [
            {"date": "2026-08-31", "invoice_no": "20260901-0002", "ship_to": "Benne & Kaaram", "amount": 4942.50},
            {"date": "2026-09-01", "invoice_no": "20260906-0002", "ship_to": "Chorum kootanum", "amount": 4315.00}
        ],
        "ship_to_reports": [
            {
                "ship_to": "Benne & Kaaram",
                "total_amount": 4942.50,
                "items": [
                    {"name": "Banana Nendram", "qty": 12.0, "unit": "kg", "rate": 77.50, "amount": 930.0},
                    {"name": "Avocado", "qty": 12.0, "unit": "kg", "rate": 308.33, "amount": 3700.0}
                ]
            }
        ],
        "grand_total_consolidation": [
            {"name": "Banana Nendram", "qty": 12.0, "unit": "kg", "rate": 77.50, "amount": 930.0},
            {"name": "Avocado", "qty": 12.0, "unit": "kg", "rate": 308.33, "amount": 3700.0}
        ],
        "total_bill_amount": 9257.50
    }

    out_file = str(tmp_path / "test_consolidated.pdf")
    res = generate_consolidated_report_pdf(report_mock, out_file)
    assert os.path.exists(res)
    assert os.path.getsize(res) > 2000


def test_consolidated_report_ui_frame(tk_root, fake_db):
    service = BillingService(fake_db)
    frame = ConsolidatedReportFrame(tk_root, fake_db, service)
    frame.update_idletasks()

    assert frame.generate_btn is not None
    assert frame.pdf_btn is not None
    assert frame.kpi_locs_val["text"] == "0"
    assert frame.kpi_amt_val["text"] == "₹0.00"
    frame.destroy()

