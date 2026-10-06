import pytest
import os
import tempfile
from pypdf import PdfReader
from app.printing.invoice import generate_invoice_pdf, generate_dc_pdf, render_invoice_html, render_dc_html

@pytest.fixture
def sample_bill():
    return {
        "invoice_no": "20260911-0006",
        "invoice_date": "2026-09-11",
        "customer_id": "CUST0019",
        "customer_name": "Benne & Kaaram",
        "total_amount": 6398.50,
        "items": [
            {"sno": i, "item_id": f"ITM{i:03d}", "name": f"Produce Item {i}", "qty": 10.0 + i, "unit": "kg", "rate": 25.0, "amount": (10.0 + i) * 25.0}
            for i in range(1, 24)
        ]
    }

@pytest.fixture
def sample_company():
    return {
        "company_id": "Company0001",
        "name": "SV Vegetables & Fruits",
        "address": "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.",
        "phone": "9380645132 , 9382179443 , 9444042275",
        "email": "info@svveg.com",
        "gst_number": "33ABCDE1234F1Z5",
        "terms_and_conditions": "Goods once sold will not be taken back.",
        "signatory_label": "Authorized Signatory"
    }

@pytest.fixture
def sample_customer():
    return {
        "cust_id": "CUST0019",
        "name": "Benne & Kaaram",
        "address": "Ground floor, 4th Main Rd, Thiruvalluvar Nagar, Besant Nagar, Chennai, India 6000090",
        "contact_person_phone": "8919412775",
        "bill_to_name": "GENERATIONAL SOUTHSIDE HOSPITALITY PRIVATE LIMITED",
        "bill_to_address": "FLAT NO. 30 Sumithra Nagar 2nd Street Poonamallee Chennai - 600056",
        "gst_number": ""
    }

def test_render_invoice_html(sample_bill, sample_company, sample_customer):
    html = render_invoice_html(sample_bill, sample_company, sample_customer)
    assert "SV VEGETABLES &amp; FRUITS" in html or "SV Vegetables & Fruits" in html or "SV VEGETABLES & FRUITS" in html
    assert "INVOICE (CREDIT)" in html
    assert "GENERATIONAL SOUTHSIDE HOSPITALITY PRIVATE LIMITED" in html
    assert "Benne &amp; Kaaram" in html or "Benne & Kaaram" in html
    assert "20260911-0006" in html
    assert "Page 1 of 2" in html
    assert "Page 2 of 2" in html

def test_render_dc_html(sample_bill, sample_company, sample_customer):
    html = render_dc_html(sample_bill, sample_company, sample_customer)
    assert "DELIVERY CHALLAN (CREDIT)" in html
    assert "Benne &amp; Kaaram" in html or "Benne & Kaaram" in html
    assert "Receiver&#39;s Signature" in html or "Receiver's Signature" in html
    assert "GENERATIONAL SOUTHSIDE HOSPITALITY PRIVATE LIMITED" in html
    assert "Page 1 of 2" in html
    assert "Page 2 of 2" in html

def test_generate_invoice_pdf_file(sample_bill, sample_company, sample_customer):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        generate_invoice_pdf(pdf_path, sample_bill, company=sample_company, customer=sample_customer)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000
        reader = PdfReader(pdf_path)
        assert len(reader.pages) >= 1
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

def test_generate_dc_pdf_file(sample_bill, sample_company, sample_customer):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        generate_dc_pdf(pdf_path, sample_bill, company=sample_company, customer=sample_customer)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000
        reader = PdfReader(pdf_path)
        assert len(reader.pages) >= 1
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

def test_attached_anna_adarsh_dc():
    """Verify live Anna Adarsh College DC with SRINIVASA TRADERS header & SVT logo."""
    anna_bill = {
        "invoice_no": "20260212-0015",
        "invoice_date": "2026-02-12",
        "customer_id": "Cust0002",
        "customer_name": "Anna Adarsh College",
        "company_id": "Company0001",
        "items": [
            {"sno": 1, "name": "Onion", "qty": 20, "unit": "kg"},
            {"sno": 2, "name": "Tomatto (Country)", "qty": 10, "unit": "kg"},
            {"sno": 3, "name": "Carrot", "qty": 3, "unit": "kg"},
        ]
    }
    anna_cust = {
        "cust_id": "Cust0002",
        "name": "Anna Adarsh College",
        "address": "A-1, Off 9th Main Road, Anna Nagar, Chennai, Tamil Nadu - 600040",
        "bill_to_name": "SRINIVASA TRADERS",
        "dc_company_id": "Company0003",
    }
    srinivasa_comp = {
        "company_id": "Company0003",
        "name": "SRINIVASA TRADERS",
        "address": "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.",
        "phone": "9444434066 , 9382179443",
        "email": "kumar@yahoo.co.in",
        "gst_number": "",
        "logo_url": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
        "signatory_label": "Authorized Signatory"
    }

    html = render_dc_html(anna_bill, company=srinivasa_comp, customer=anna_cust)
    assert "SRINIVASA TRADERS" in html
    assert "DELIVERY CHALLAN (CREDIT)" in html
    assert "Anna Adarsh College" in html
    assert "20260212-0015" in html
    assert "GSTIN:" in html
    assert "For SRINIVASA TRADERS" in html

def test_attached_kids_clinic_dc_and_invoice():
    """Verify live Kids Clinic DC and Invoice with GK VEGETABLES & FRUITS header & logo."""
    kids_bill = {
        "invoice_no": "20260802-0002",
        "invoice_date": "2026-07-31",
        "customer_id": "Cust0018",
        "customer_name": "KIDS CLINIC INDIA LTD - OMR",
        "company_id": "Company0002",
        "total_amount": 42283.0,
        "items": [
            {"sno": 1, "name": "Apple", "qty": 11, "unit": "kg", "rate": 155.0, "amount": 1705.0},
            {"sno": 2, "name": "Avaraikkai", "qty": 3, "unit": "kg", "rate": 35.0, "amount": 105.0},
        ]
    }
    kids_cust = {
        "cust_id": "Cust0018",
        "name": "KIDS CLINIC INDIA LTD - OMR",
        "address": "148, Old Mahabalipuram Rd, Mettukuppam, Thoraipakkam, Tamil Nadu 600097",
        "bill_to_name": "KIDS CLINIC INDIA LTD - OMR",
        "bill_to_address": "148, Old Mahabalipuram Rd, Mettukuppam, Thoraipakkam, Tamil Nadu 600097",
        "company_id": "Company0002",
        "dc_company_id": "Company0002",
    }
    gk_comp = {
        "company_id": "Company0002",
        "name": "GK VEGETABLES & FRUITS",
        "address": "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.",
        "phone": "9677062919",
        "email": "info@gkveg.com",
        "gst_number": "33ABCDE1234F1Z5",
        "logo_url": "/images/gk_logo.png",
        "signatory_label": "Authorized Signatory"
    }

    # Test DC
    dc_html = render_dc_html(kids_bill, company=gk_comp, customer=kids_cust)
    assert "GK VEGETABLES &amp; FRUITS" in dc_html or "GK VEGETABLES & FRUITS" in dc_html
    assert "DELIVERY CHALLAN (CREDIT)" in dc_html
    assert "KIDS CLINIC INDIA LTD - OMR" in dc_html
    assert "For GK VEGETABLES &amp; FRUITS" in dc_html or "For GK VEGETABLES & FRUITS" in dc_html

    # Test Invoice
    inv_html = render_invoice_html(kids_bill, company=gk_comp, customer=kids_cust)
    assert "GK VEGETABLES &amp; FRUITS" in inv_html or "GK VEGETABLES & FRUITS" in inv_html
    assert "INVOICE (CREDIT)" in inv_html
    assert "BILL TO:" in inv_html
    assert "KIDS CLINIC INDIA LTD - OMR" in inv_html
    assert "33ABCDE1234F1Z5" in inv_html
