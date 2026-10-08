from __future__ import annotations
import os
import sys
import subprocess
import tempfile
import base64
import math
import shutil
import time
from typing import Any, Dict, Optional, List
from app.config.settings import settings
from app.utils.currency import format_inr, amount_in_words
from app.utils.formatters import format_date

ITEMS_PER_PAGE = 19

def _get_edge_path() -> Optional[str]:
    """Locate Microsoft Edge executable on Windows for headless printing."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def _get_logo_base64(filename: str = "logo.png") -> str:
    """Find and base64-encode company logo from app/assets."""
    if not filename:
        filename = "logo.png"
    search_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", filename),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "desktopapp_native", "app", "assets", filename),
    ]
    for p in search_paths:
        if os.path.exists(p):
            try:
                ext = os.path.splitext(p)[1].lower().replace(".", "")
                mime = "image/png" if ext == "png" else ("image/jpeg" if ext in ["jpg", "jpeg"] else "image/png")
                with open(p, "rb") as f:
                    return f"data:{mime};base64," + base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    if filename != "logo.png":
        return _get_logo_base64("logo.png")
    return ""

def _resolve_company_logo(company: Optional[Dict[str, Any]]) -> str:
    if not company:
        return _get_logo_base64("logo.png")
    logo_url = company.get("logo_url") or company.get("logo") or ""
    if isinstance(logo_url, str) and logo_url.startswith("data:image"):
        return logo_url
    filename = os.path.basename(logo_url) if logo_url else "logo.png"
    return _get_logo_base64(filename)

def _resolve_company_and_customer(
    bill: Dict[str, Any],
    company: Optional[Dict[str, Any]] = None,
    customer: Optional[Dict[str, Any]] = None,
    is_dc: bool = False
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    cust = dict(customer) if customer else {}
    comp = dict(company) if company else {}

    # Attempt to fetch customer from DB if missing or incomplete
    cust_id = cust.get("cust_id") or bill.get("customer_id")
    if cust_id and cust_id != "CASH" and (not cust or not cust.get("bill_to_name") or not cust.get("dc_company_id")):
        try:
            from app.config.settings import settings
            from app.database.connection import MongoDatabase
            db = MongoDatabase(settings)
            db.connect()
            db_cust = db.db["customers"].find_one({"cust_id": cust_id})
            if db_cust:
                for k, v in db_cust.items():
                    if k not in cust or not cust[k]:
                        cust[k] = v
        except Exception:
            pass

    # Resolve company based on DC vs Invoice
    target_comp_id = None
    if is_dc:
        target_comp_id = cust.get("dc_company_id") or bill.get("company_id")
    else:
        target_comp_id = bill.get("company_id") or cust.get("company_id")

    # If company is not provided or differs from target_comp_id
    if target_comp_id and (not comp or comp.get("company_id") != target_comp_id):
        try:
            from app.config.settings import settings
            from app.database.connection import MongoDatabase
            db = MongoDatabase(settings)
            db.connect()
            db_comp = db.db["companies"].find_one({"company_id": target_comp_id})
            if db_comp:
                comp = db_comp
        except Exception:
            pass

    if not comp:
        comp = {
            "company_id": "Company0001",
            "name": settings.default_company_name,
            "address": "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092.",
            "phone": "9380645132 , 9382179443 , 9444042275",
            "email": "info@svveg.com",
            "gst_number": "33ABCDE1234F1Z5",
            "terms_and_conditions": "",
            "signatory_label": "Authorized Signatory",
            "logo_url": "/images/logo.png"
        }

    return comp, cust

def _format_phone(phone: Any) -> str:
    if not phone or str(phone).strip() in ["-", "None", ""]:
        return ""
    return str(phone).strip()

def render_invoice_html(bill: Dict[str, Any], company: Optional[Dict[str, Any]] = None, customer: Optional[Dict[str, Any]] = None) -> str:
    """Render HTML for Tax Invoice matching 48-invoice-print.png and Inv- 20260911-0006.pdf."""
    comp = company or {}
    cust = customer or {}

    comp_name = comp.get("name") or settings.default_company_name.upper()
    comp_addr = comp.get("address") or "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092."
    comp_phone = comp.get("phone") or "9380645132 , 9382179443 , 9444042275"
    comp_email = comp.get("email") or "info@svveg.com"
    comp_gst = comp.get("gst_number")
    gst_str = f" | GSTIN: {comp_gst}" if comp_gst else (" | GSTIN: " if comp_gst == "" else "")

    bill_to_name = cust.get("bill_to_name") or cust.get("name") or bill.get("customer_name") or "Cash"
    bill_to_addr = (cust.get("bill_to_address") or cust.get("address") or "").replace("\n", "<br>")
    bill_to_phone = _format_phone(cust.get("bill_to_phone") or cust.get("contact_person_phone"))
    bill_to_gst = cust.get("gst_number") or ""

    ship_to_name = cust.get("name") or bill.get("customer_name") or "Cash"
    ship_to_addr = (cust.get("address") or "").replace("\n", "<br>")
    ship_to_phone = _format_phone(cust.get("contact_person_phone"))

    inv_no = bill.get("invoice_no") or "NEW"
    inv_date = format_date(bill.get("invoice_date"))
    place = cust.get("state") or "Local"

    items: List[Dict[str, Any]] = bill.get("items", [])
    total_pages = math.ceil(len(items) / ITEMS_PER_PAGE) or 1
    pages_chunks = [items[i:i + ITEMS_PER_PAGE] for i in range(0, len(items), ITEMS_PER_PAGE)] or [[]]

    tot_amt = float(bill.get("total_amount", 0.0))
    words = amount_in_words(tot_amt)
    payment_mode = "CASH" if str(bill.get("customer_name", "")).lower() == "cash" else "CREDIT"
    logo_b64 = _resolve_company_logo(comp)

    html_pages = []
    for p_idx, chunk in enumerate(pages_chunks):
        rows_html = ""
        for r_idx, itm in enumerate(chunk):
            sno = (p_idx * ITEMS_PER_PAGE) + r_idx + 1
            qty_val = float(itm.get("qty", 0))
            qty_str = f"{qty_val:g}"
            rate_str = f"{float(itm.get('rate', 0)):.2f}"
            amt_str = f"{float(itm.get('amount', 0)):.2f}"
            rows_html += f"""
            <tr>
                <td style="text-align: center;">{sno}</td>
                <td style="text-align: left;">{itm.get('name', '')}</td>
                <td style="text-align: right;">{qty_str}</td>
                <td style="text-align: center;">{itm.get('unit', 'kg')}</td>
                <td style="text-align: right;">{rate_str}</td>
                <td style="text-align: right;">{amt_str}</td>
            </tr>
            """

        footer_html = ""
        if p_idx == total_pages - 1:
            terms = (comp.get("terms_and_conditions") or "").replace("\n", "<br>")
            sig_label = comp.get("signatory_label") or "Authorized Signatory"
            footer_html = f"""
            <div class="totals-section">
                <div class="amount-words"><strong>Amount in Words:</strong> {words}</div>
                <div class="grand-total">Total: ₹{tot_amt:,.2f}</div>
                <div class="signatures">
                    <div class="terms">
                        <strong>Terms & Conditions:</strong>
                        <div style="font-size: 10px; margin-top: 3px;">{terms}</div>
                    </div>
                    <div class="sign-box">
                        <p style="margin: 0; font-weight: bold;">For {comp_name}</p>
                        <div style="height: 38px;"></div>
                        <p style="margin: 0;">{sig_label}</p>
                    </div>
                </div>
            </div>
            """

        logo_img_tag = f'<img src="{logo_b64}" class="company-logo">' if logo_b64 else ""

        page_html = f"""
        <div class="a4-page">
            <div class="page-header">
                <div class="header-left">{logo_img_tag}</div>
                <div class="header-center">
                    <h1>{comp_name}</h1>
                    <p>
                        {comp_addr}<br>
                        Ph: {comp_phone} | Email: {comp_email}{gst_str}
                    </p>
                </div>
                <div class="header-right"></div>
            </div>

            <div class="invoice-title">INVOICE ({payment_mode})</div>

            <div class="details-grid">
                <div class="detail-box">
                    <span class="detail-label">BILL TO:</span>
                    <div class="detail-content">
                        <strong>{bill_to_name}</strong><br>
                        {bill_to_addr}<br>
                        {'Ph: ' + bill_to_phone if bill_to_phone else ''}
                        {('<br>GSTIN: ' + bill_to_gst) if bill_to_gst else ''}
                    </div>
                </div>
                <div class="detail-box">
                    <span class="detail-label">SHIP TO:</span>
                    <div class="detail-content">
                        <strong>{ship_to_name}</strong><br>
                        {ship_to_addr}<br>
                        {'Ph: ' + ship_to_phone if ship_to_phone else ''}
                    </div>
                </div>
                <div class="detail-box">
                    <span class="detail-label">INVOICE DETAILS:</span>
                    <div class="detail-content">
                        <strong>No:</strong> {inv_no}<br>
                        <strong>Date:</strong> {inv_date}<br>
                        <strong>Place:</strong> {place}
                    </div>
                </div>
            </div>

            <table class="print-table">
                <thead>
                    <tr>
                        <th style="width: 5%; text-align: center;">Sno</th>
                        <th style="width: 45%; text-align: left;">Description</th>
                        <th style="width: 10%; text-align: right;">Qty</th>
                        <th style="width: 10%; text-align: center;">Unit</th>
                        <th style="width: 15%; text-align: right;">Rate (₹)</th>
                        <th style="width: 15%; text-align: right;">Amount (₹)</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>

            {footer_html}

            <div class="page-bottom-info">
                Page {p_idx + 1} of {total_pages}
            </div>
        </div>
        """
        html_pages.append(page_html)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4 portrait;
    margin: 8mm 10mm;
}}
* {{
    box-sizing: border-box;
}}
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 0;
    padding: 0;
    color: #000;
    font-size: 11px;
    background: #fff;
}}
.a4-page {{
    width: 100%;
    min-height: 275mm;
    max-height: 275mm;
    position: relative;
    page-break-after: always;
    page-break-inside: avoid;
    display: flex;
    flex-direction: column;
}}
.a4-page:last-child {{
    page-break-after: auto;
}}
.page-header {{
    display: flex;
    align-items: center;
    margin-bottom: 8px;
}}
.header-left {{
    width: 80px;
    flex-shrink: 0;
}}
.company-logo {{
    width: 75px;
    height: auto;
}}
.header-center {{
    flex-grow: 1;
    text-align: center;
}}
.header-center h1 {{
    margin: 0;
    font-size: 19px;
    font-weight: bold;
    color: #008000;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.header-center p {{
    margin: 3px 0 0;
    font-size: 10.5px;
    color: #000;
    line-height: 1.35;
}}
.header-right {{
    width: 80px;
    flex-shrink: 0;
}}
.invoice-title {{
    text-align: center;
    font-weight: bold;
    padding: 5px;
    margin-bottom: 8px;
    text-transform: uppercase;
    font-size: 13px;
    background-color: #009e49;
    color: white;
    border: 1px solid #000;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}
.details-grid {{
    display: flex;
    width: 100%;
    border: 1px solid #000;
    margin-bottom: 8px;
}}
.detail-box {{
    flex: 1;
    padding: 6px 8px;
    border-right: 1px solid #000;
    display: flex;
    flex-direction: column;
}}
.detail-box:last-child {{
    border-right: none;
}}
.detail-label {{
    font-size: 10px;
    font-weight: bold;
    color: #008a5e;
    text-transform: uppercase;
    margin-bottom: 4px;
}}
.detail-content {{
    font-size: 10.5px;
    line-height: 1.35;
}}
.print-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 6px;
    font-size: 10.5px;
}}
.print-table th {{
    border: 1px solid #000;
    background-color: #fff;
    padding: 4px 6px;
    font-weight: bold;
}}
.print-table td {{
    border: 1px solid #000;
    padding: 3px 6px;
}}
.totals-section {{
    border: 1px solid #000;
    padding: 8px;
    margin-top: 6px;
}}
.amount-words {{
    font-size: 10.5px;
    margin-bottom: 4px;
}}
.grand-total {{
    font-weight: bold;
    font-size: 13px;
    text-align: right;
    margin-top: 4px;
    margin-bottom: 8px;
}}
.signatures {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 15px;
    font-size: 10.5px;
}}
.terms {{
    width: 60%;
}}
.sign-box {{
    width: 35%;
    text-align: center;
}}
.page-bottom-info {{
    text-align: right;
    font-size: 9.5px;
    color: #555;
    margin-top: auto;
    padding-top: 6px;
}}
</style>
</head>
<body>
{''.join(html_pages)}
</body>
</html>
"""

def render_dc_html(bill: Dict[str, Any], company: Optional[Dict[str, Any]] = None, customer: Optional[Dict[str, Any]] = None) -> str:
    """Render HTML for Delivery Challan matching DC- 20260911-0006.pdf."""
    comp = company or {}
    cust = customer or {}

    comp_name = comp.get("name") or settings.default_company_name.upper()
    comp_addr = comp.get("address") or "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092."
    comp_phone = comp.get("phone") or "9380645132 , 9382179443 , 9444042275"
    comp_email = comp.get("email") or "info@svveg.com"
    comp_gst = comp.get("gst_number")
    gst_str = f" | GSTIN: {comp_gst}" if comp_gst else (" | GSTIN: " if comp_gst == "" else "")

    bill_to_name = cust.get("bill_to_name") or cust.get("name") or bill.get("customer_name") or "Cash"
    ship_to_name = cust.get("name") or bill.get("customer_name") or "Cash"
    ship_to_addr = (cust.get("address") or "").replace("\n", "<br>")
    ship_to_phone = _format_phone(cust.get("contact_person_phone"))

    inv_no = bill.get("invoice_no") or "NEW"
    inv_date = format_date(bill.get("invoice_date"))

    # Signatory company for DC:
    if comp.get("company_id") in ["Company0002", "Company0003"]:
        dc_for_company = comp.get("name") or comp_name
    elif cust.get("bill_to_name") and cust.get("bill_to_name") != cust.get("name") and cust.get("bill_to_name") != "Cash":
        dc_for_company = cust.get("bill_to_name")
    else:
        dc_for_company = comp.get("name") or comp_name
    sig_label = comp.get("signatory_label") or "Authorized Signatory"
    payment_mode = "CASH" if str(bill.get("customer_name", "")).lower() == "cash" else "CREDIT"

    items: List[Dict[str, Any]] = bill.get("items", [])
    total_pages = math.ceil(len(items) / ITEMS_PER_PAGE) or 1
    pages_chunks = [items[i:i + ITEMS_PER_PAGE] for i in range(0, len(items), ITEMS_PER_PAGE)] or [[]]

    logo_b64 = _resolve_company_logo(comp)
    logo_img_tag = f'<img src="{logo_b64}" class="company-logo">' if logo_b64 else ""

    html_pages = []
    for p_idx, chunk in enumerate(pages_chunks):
        rows_html = ""
        for r_idx, itm in enumerate(chunk):
            sno = (p_idx * ITEMS_PER_PAGE) + r_idx + 1
            qty_val = float(itm.get("qty", 0))
            qty_str = f"{qty_val:g}"
            rows_html += f"""
            <tr>
                <td style="text-align: center;">{sno}</td>
                <td style="text-align: left;">{itm.get('name', '')}</td>
                <td style="text-align: right;">{qty_str}</td>
                <td style="text-align: center;">{itm.get('unit', 'kg')}</td>
            </tr>
            """

        footer_html = ""
        if p_idx == total_pages - 1:
            footer_html = f"""
            <div style="margin-top: 35px; width: 100%;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="width: 45%; vertical-align: bottom;">
                            <div style="border-top: 1px solid #333; width: 200px; text-align: center; padding-top: 5px; font-weight: bold; font-size: 10px;">
                                Receiver's Signature
                            </div>
                        </td>
                        <td style="width: 10%;"></td>
                        <td style="width: 45%; vertical-align: bottom; text-align: right;">
                            <div style="font-weight: bold; margin-bottom: 45px; font-size: 10.5px;">For {dc_for_company}</div>
                            <div style="border-top: 1px solid #333; width: 180px; text-align: center; float: right; padding-top: 5px; font-weight: bold; font-size: 10px;">
                                {sig_label}
                            </div>
                        </td>
                    </tr>
                </table>
            </div>
            """

        page_html = f"""
        <div class="a4-page">
            <div class="page-header">
                <div class="header-left">{logo_img_tag}</div>
                <div class="header-center">
                    <h1>{comp_name}</h1>
                    <p>
                        {comp_addr}<br>
                        Ph: {comp_phone} | Email: {comp_email}{gst_str}
                    </p>
                </div>
                <div class="header-right"></div>
            </div>

            <div class="invoice-title">DELIVERY CHALLAN ({payment_mode})</div>

            <div class="details-grid">
                <div class="detail-box" style="flex: 1.5; border-right: 1px solid #000;">
                    <span class="detail-label">SHIP TO:</span>
                    <div class="detail-content">
                        <strong>{ship_to_name}</strong><br>
                        {ship_to_addr}<br>
                        {'Ph: ' + ship_to_phone if ship_to_phone else ''}
                    </div>
                </div>
                <div class="detail-box" style="flex: 1;">
                    <span class="detail-label">CHALLAN DETAILS:</span>
                    <div class="detail-content">
                        <strong>No:</strong> {inv_no}<br>
                        <strong>Date:</strong> {inv_date}
                    </div>
                </div>
            </div>

            <table class="print-table">
                <thead>
                    <tr>
                        <th style="width: 8%; text-align: center;">Sno</th>
                        <th style="width: 62%; text-align: left;">Description</th>
                        <th style="width: 15%; text-align: right;">Qty</th>
                        <th style="width: 15%; text-align: center;">Unit</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>

            {footer_html}

            <div class="page-bottom-info">
                Page {p_idx + 1} of {total_pages}
            </div>
        </div>
        """
        html_pages.append(page_html)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4 portrait;
    margin: 8mm 10mm;
}}
* {{
    box-sizing: border-box;
}}
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 0;
    padding: 0;
    color: #000;
    font-size: 11px;
    background: #fff;
}}
.a4-page {{
    width: 100%;
    min-height: 275mm;
    max-height: 275mm;
    position: relative;
    page-break-after: always;
    page-break-inside: avoid;
    display: flex;
    flex-direction: column;
}}
.a4-page:last-child {{
    page-break-after: auto;
}}
.page-header {{
    display: flex;
    align-items: center;
    margin-bottom: 8px;
}}
.header-left {{
    width: 80px;
    flex-shrink: 0;
}}
.company-logo {{
    width: 75px;
    height: auto;
}}
.header-center {{
    flex-grow: 1;
    text-align: center;
}}
.header-center h1 {{
    margin: 0;
    font-size: 19px;
    font-weight: bold;
    color: #008000;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.header-center p {{
    margin: 3px 0 0;
    font-size: 10.5px;
    color: #000;
    line-height: 1.35;
}}
.header-right {{
    width: 80px;
    flex-shrink: 0;
}}
.invoice-title {{
    text-align: center;
    font-weight: bold;
    padding: 5px;
    margin-bottom: 8px;
    text-transform: uppercase;
    font-size: 13px;
    background-color: #009e49;
    color: white;
    border: 1px solid #000;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}
.details-grid {{
    display: flex;
    width: 100%;
    border: 1px solid #000;
    margin-bottom: 8px;
}}
.detail-box {{
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
}}
.detail-label {{
    font-size: 10px;
    font-weight: bold;
    color: #008a5e;
    text-transform: uppercase;
    margin-bottom: 4px;
}}
.detail-content {{
    font-size: 10.5px;
    line-height: 1.35;
}}
.print-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 6px;
    font-size: 10.5px;
}}
.print-table th {{
    border: 1px solid #000;
    background-color: #fff;
    padding: 4px 6px;
    font-weight: bold;
}}
.print-table td {{
    border: 1px solid #000;
    padding: 3px 6px;
}}
.page-bottom-info {{
    text-align: right;
    font-size: 9.5px;
    color: #555;
    margin-top: auto;
    padding-top: 6px;
}}
</style>
</head>
<body>
{''.join(html_pages)}
</body>
</html>
"""

def _generate_pdf_via_browser(html_content: str, output_path: str, timeout: float = 25.0) -> bool:
    """Print HTML to PDF using headless Edge or Chrome.

    A throw-away --user-data-dir is essential: with the default profile, an already-running
    Edge/Chrome swallows the command (exit code 0, no PDF). The browser also writes the PDF
    after the launcher process has returned, so we poll for the finished file.
    """
    browser_exe = _get_edge_path()
    if not browser_exe:
        return False

    abs_output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix="billdesk_pdf_")
    temp_html = os.path.join(work_dir, "doc.html")
    profile_dir = os.path.join(work_dir, "profile")

    try:
        if os.path.exists(abs_output):
            os.remove(abs_output)          # never mistake a stale PDF for the new one
        with open(temp_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        cmd = [
            browser_exe,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile_dir}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={abs_output}",
            temp_html,
        ]
        ret = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if ret.returncode != 0:
            return False

        deadline = time.monotonic() + timeout
        last_size = -1
        while time.monotonic() < deadline:
            if os.path.exists(abs_output):
                size = os.path.getsize(abs_output)
                if size > 0 and size == last_size:      # size stable across two polls => fully written
                    return True
                last_size = size
            time.sleep(0.25)
        return False
    except Exception as ex:
        print(f"Browser PDF generation error: {ex}")
        return False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

_PDF_FONTS: Optional[tuple] = None

def _pdf_fonts() -> tuple:
    """(regular, bold, rupee_symbol) for ReportLab output; a TTF with U+20B9 if one is installed."""
    global _PDF_FONTS
    if _PDF_FONTS is not None:
        return _PDF_FONTS
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pairs = [
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ]
    result = ("Helvetica", "Helvetica-Bold", "Rs.")      # built-in fonts have no rupee glyph
    for reg_path, bold_path in pairs:
        if not (os.path.exists(reg_path) and os.path.exists(bold_path)):
            continue
        try:
            reg = TTFont("BillDeskSans", reg_path)
            if 0x20B9 not in reg.face.charToGlyph:
                continue
            pdfmetrics.registerFont(reg)
            pdfmetrics.registerFont(TTFont("BillDeskSans-Bold", bold_path))
            pdfmetrics.registerFontFamily("BillDeskSans", normal="BillDeskSans", bold="BillDeskSans-Bold",
                                          italic="BillDeskSans", boldItalic="BillDeskSans-Bold")
            result = ("BillDeskSans", "BillDeskSans-Bold", "\u20b9")
            break
        except Exception:
            continue
    _PDF_FONTS = result
    return result

def _generate_reportlab_invoice_fallback(path: str, bill: Dict[str, Any], company: Optional[Dict[str, Any]] = None, customer: Optional[Dict[str, Any]] = None, is_dc: bool = False) -> None:
    """Fallback ReportLab generator (Tax Invoice, or Delivery Challan without rates/amounts) used when no headless browser works."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm

    comp = company or {}
    cust = customer or {}
    styles = getSampleStyleSheet()
    reg_font, bold_font, sym = _pdf_fonts()
    normal = ParagraphStyle("BDNormal", parent=styles["Normal"], fontName=reg_font)

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm
    )
    story = []

    comp_name = comp.get("name") or settings.default_company_name.upper()
    comp_addr = comp.get("address") or "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092."
    comp_phone = comp.get("phone") or "9380645132"
    comp_email = comp.get("email") or "info@svveg.com"
    comp_gst = comp.get("gst_number") or "33ABCDE1234F1Z5"

    header_style = ParagraphStyle("H1", parent=styles["Heading1"], fontName=bold_font, fontSize=18, leading=22, textColor=colors.HexColor("#008000"), alignment=1)
    sub_style = ParagraphStyle("Sub", parent=normal, fontName=reg_font, fontSize=9, leading=12, textColor=colors.HexColor("#1a1a1a"), alignment=1)

    story.append(Paragraph(comp_name, header_style))
    story.append(Paragraph(f"{comp_addr}<br/>Ph: {comp_phone} | Email: {comp_email} | GSTIN: {comp_gst}", sub_style))
    story.append(Spacer(1, 4 * mm))

    pm = "CASH" if str(bill.get("customer_name", "")).strip().lower().startswith("cash") else "CREDIT"
    banner_data = [["DELIVERY CHALLAN"]] if is_dc else [[f"INVOICE ({pm})"]]
    banner_table = Table(banner_data, colWidths=[190 * mm])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#009e49")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), bold_font),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 3 * mm))

    # Details grid
    bill_to_name = cust.get("bill_to_name") or cust.get("name") or bill.get("customer_name") or "Cash"
    bill_to_addr = cust.get("bill_to_address") or cust.get("address") or ""
    bill_to_phone = cust.get("bill_to_phone") or cust.get("contact_person_phone") or ""

    ship_to_name = cust.get("name") or bill.get("customer_name") or "Cash"
    ship_to_addr = cust.get("address") or ""
    ship_to_phone = cust.get("contact_person_phone") or ""

    c1 = f"<b>BILL TO:</b><br/><b>{bill_to_name}</b><br/>{bill_to_addr}<br/>Ph: {bill_to_phone}"
    c2 = f"<b>SHIP TO:</b><br/><b>{ship_to_name}</b><br/>{ship_to_addr}<br/>Ph: {ship_to_phone}"
    c3 = f"<b>{"DELIVERY DETAILS" if is_dc else "INVOICE DETAILS"}:</b><br/>No: <b>{bill.get('invoice_no')}</b><br/>Date: {format_date(bill.get('invoice_date'))}<br/>Place: Local"

    grid_table = Table([[
        Paragraph(c1, normal),
        Paragraph(c2, normal),
        Paragraph(c3, normal)
    ]], colWidths=[65 * mm, 65 * mm, 60 * mm])
    grid_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(grid_table)
    story.append(Spacer(1, 4 * mm))

    # Items table
    items = bill.get("items", [])
    if is_dc:
        data = [["Sno", "Description", "Qty", "Unit"]]
    else:
        data = [["Sno", "Description", "Qty", "Unit", f"Rate ({sym})", f"Amount ({sym})"]]
    for i, itm in enumerate(items, 1):
        row = [str(i), itm.get("name", ""), f"{float(itm.get('qty', 0)):g}", itm.get("unit", "kg")]
        if not is_dc:
            row += [f"{float(itm.get('rate', 0)):.2f}", f"{float(itm.get('amount', 0)):.2f}"]
        data.append(row)

    col_widths = [12 * mm, 118 * mm, 30 * mm, 30 * mm] if is_dc else [12 * mm, 82 * mm, 18 * mm, 18 * mm, 26 * mm, 34 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (-1, -1), reg_font),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    # Total and Footer
    if not is_dc:
        tot_amt = float(bill.get("total_amount", 0.0))
        words = amount_in_words(tot_amt)
        story.append(Paragraph(f"<b>Amount in Words:</b> {words}", normal))
        story.append(Paragraph(f"<b>Total: {sym}{tot_amt:,.2f}</b>", ParagraphStyle("Tot", parent=normal, fontName=reg_font, fontSize=12, alignment=2)))
    story.append(Spacer(1, 6 * mm))

    terms = comp.get("terms_and_conditions") or "1. Goods once sold will not be taken back."
    sig_label = comp.get("signatory_label") or "Authorized Signatory"
    foot = [[
        Paragraph(f"<b>Terms & Conditions:</b><br/>{terms}", normal),
        Paragraph(f"<b>For {comp_name}</b><br/><br/><br/>{sig_label}", ParagraphStyle("Sig", parent=normal, fontName=reg_font, alignment=2))
    ]]
    foot_table = Table(foot, colWidths=[110 * mm, 80 * mm])
    foot_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(foot_table)

    doc.build(story)

def generate_invoice_pdf(arg1: Any, arg2: Any, company: Optional[Dict[str, Any]] = None, customer: Optional[Dict[str, Any]] = None) -> str:
    """Generate Tax Invoice PDF matching 48-invoice-print.png and Inv- 20260911-0006.pdf.
    Supports either (path, bill) or (bill, path) calling conventions.
    """
    if isinstance(arg1, str) and (isinstance(arg2, dict) or hasattr(arg2, "get")):
        output_path, bill = arg1, arg2
    elif isinstance(arg2, str) and (isinstance(arg1, dict) or hasattr(arg1, "get")):
        bill, output_path = arg1, arg2
    else:
        output_path, bill = str(arg1), arg2

    comp, cust = _resolve_company_and_customer(bill, company=company, customer=customer, is_dc=False)
    html = render_invoice_html(bill, company=comp, customer=cust)
    success = _generate_pdf_via_browser(html, output_path)
    if not success:
        _generate_reportlab_invoice_fallback(output_path, bill, company=comp, customer=cust)

    return output_path

def generate_dc_pdf(arg1: Any, arg2: Any, company: Optional[Dict[str, Any]] = None, customer: Optional[Dict[str, Any]] = None) -> str:
    """Generate Delivery Challan PDF matching DC- 20260911-0006.pdf.
    Supports either (path, bill) or (bill, path) calling conventions.
    """
    if isinstance(arg1, str) and (isinstance(arg2, dict) or hasattr(arg2, "get")):
        output_path, bill = arg1, arg2
    elif isinstance(arg2, str) and (isinstance(arg1, dict) or hasattr(arg1, "get")):
        bill, output_path = arg1, arg2
    else:
        output_path, bill = str(arg1), arg2

    comp, cust = _resolve_company_and_customer(bill, company=company, customer=customer, is_dc=True)
    html = render_dc_html(bill, company=comp, customer=cust)
    success = _generate_pdf_via_browser(html, output_path)
    if not success:
        _generate_reportlab_invoice_fallback(output_path, bill, company=comp, customer=cust, is_dc=True)

    return output_path
