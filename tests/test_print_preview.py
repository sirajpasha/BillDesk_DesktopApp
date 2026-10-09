from app.ui.print_preview import show_print_preview
from app.printing.consolidated import generate_consolidated_report_pdf


def test_print_preview_dialog(tk_root, tmp_path):
    # 1. Create a dummy multi-page PDF
    report_mock = {
        "bill_to": "Mega Hospitality Group",
        "date_range": {"start": "2026-08-30", "end": "2026-10-05"},
        "bill_summary": [
            {"date": "2026-08-31", "invoice_no": "INV-001", "ship_to": "Branch Alpha", "amount": 100.0}
        ],
        "ship_to_reports": [
            {
                "ship_to": "Branch Alpha",
                "total_amount": 100.0,
                "items": [{"name": "Item A", "qty": 1.0, "unit": "kg", "rate": 100.0, "amount": 100.0}]
            }
        ],
        "grand_total_consolidation": [
            {"name": "Item A", "qty": 1.0, "unit": "kg", "rate": 100.0, "amount": 100.0}
        ],
        "total_bill_amount": 100.0
    }
    pdf_path = str(tmp_path / "preview_test.pdf")
    generate_consolidated_report_pdf(report_mock, pdf_path)

    # 2. Instantiate PrintPreviewDialog
    dlg = show_print_preview(tk_root, pdf_path, title="Test Preview", default_filename="test.pdf")
    dlg.update_idletasks()

    assert dlg.page_count >= 1
    assert dlg.current_page_idx == 0
    assert dlg.zoom_level == 1.0
    assert dlg.print_btn is not None
    assert dlg.save_btn is not None

    # Test zoom controls
    dlg._zoom_in()
    assert dlg.zoom_level > 1.0
    dlg._zoom_out()
    dlg._zoom_fit()
    assert dlg.zoom_level == 1.0

    # Test page navigation if multiple pages
    if dlg.page_count > 1:
        dlg._next_page()
        assert dlg.current_page_idx == 1
        dlg._prev_page()
        assert dlg.current_page_idx == 0

    dlg.destroy()
