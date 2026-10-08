"""Regression tests for D-05 (PDF generation while Edge is running / fallback layout) and D-12 (amount in words)."""
import os
import shutil
import subprocess
import time

import pytest

fitz = pytest.importorskip("fitz")

from app.printing import invoice as inv
from app.utils.currency import amount_in_words

BILL = {
    "invoice_no": "20261008-0001", "invoice_date": "2026-10-08", "customer_id": "C1", "customer_name": "Anna Adarsh Hostel",
    "total_amount": 542.62,
    "items": [
        {"item_id": "A", "name": "Apple", "qty": 12.5, "unit": "kg", "rate": 33.33, "amount": 416.62},
        {"item_id": "B", "name": "Avarai", "qty": 7, "unit": "kg", "rate": 18.0, "amount": 126.0},
    ],
}
COMPANY = {"name": "SV Vegetables & Fruits", "address": "Koyambedu", "phone": "1", "email": "a@b.c", "gst_number": "X"}


def _text(path):
    with fitz.open(path) as doc:
        return "".join(p.get_text() for p in doc)


@pytest.fixture
def no_browser(monkeypatch):
    monkeypatch.setattr(inv, "_generate_pdf_via_browser", lambda *a, **k: False)


def test_fallback_delivery_challan_has_no_prices_and_is_titled_challan(tmp_path, no_browser):
    out = inv.generate_dc_pdf(str(tmp_path / "dc.pdf"), BILL, company=COMPANY, customer={"name": "Anna Adarsh Hostel"})
    text = _text(out)
    assert "DELIVERY CHALLAN" in text and "INVOICE" not in text
    assert "Apple" in text and "12.5" in text
    for forbidden in ("33.33", "416.62", "542.62", "Amount in Words", "Rate", "Rupees"):
        assert forbidden not in text, f"delivery challan leaks {forbidden!r}"


def test_fallback_invoice_still_shows_rates_total_and_words(tmp_path, no_browser):
    out = inv.generate_invoice_pdf(str(tmp_path / "inv.pdf"), BILL, company=COMPANY, customer={"name": "Anna Adarsh Hostel"})
    text = _text(out)
    assert "INVOICE" in text and "33.33" in text and "542.62" in text
    assert "Five Hundred Forty Two Rupees and Sixty Two Paise Only" in text


def test_fallback_uses_a_font_that_can_render_the_rupee_sign(tmp_path, no_browser):
    out = inv.generate_invoice_pdf(str(tmp_path / "inv.pdf"), BILL, company=COMPANY, customer={})
    text = _text(out)
    reg, _bold, sym = inv._pdf_fonts()
    assert (sym in text) and (sym == "₹" or "Rs." in text)
    if sym == "₹":
        assert reg != "Helvetica"          # built-in Helvetica would print a black box


@pytest.mark.skipif(inv._get_edge_path() is None, reason="needs Edge/Chrome")
def test_browser_pdf_is_written_even_when_a_browser_instance_is_already_running(tmp_path):
    exe = inv._get_edge_path()
    prof = tmp_path / "running_profile"
    keeper = subprocess.Popen([exe, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        out = inv.generate_dc_pdf(str(tmp_path / "dc.pdf"), BILL, company=COMPANY, customer={"name": "Anna Adarsh Hostel"})
        assert os.path.getsize(out) > 0
        text = _text(out)
        assert "Apple" in text and "INVOICE (CREDIT)" not in text      # real DC layout, not the invoice fallback
    finally:
        keeper.kill()
        shutil.rmtree(prof, ignore_errors=True)


@pytest.mark.parametrize("amount,words", [
    (1, "One Rupee Only"), (2, "Two Rupees Only"), (0, "Zero Rupees Only"), (-50, "Minus Fifty Rupees Only"),
    (1234.5, "One Thousand Two Hundred Thirty Four Rupees and Fifty Paise Only"),
    (99.999, "One Hundred Rupees Only"), (0.995, "One Rupee Only"), (0.5, "Fifty Paise Only"),
    (1.01, "One Rupee and One Paise Only"),
    (12345678, "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Rupees Only"),
    (1000000000, "One Hundred Crore Rupees Only"),
])
def test_amount_in_words_edge_cases(amount, words):
    assert amount_in_words(amount) == words
