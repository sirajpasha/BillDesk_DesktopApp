from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional
from datetime import datetime
from app.config.settings import settings

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm

FONT_NORMAL = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
EMERALD_GREEN = colors.HexColor("#10b981")


def generate_consolidated_report_pdf(
    arg1: Any,
    arg2: Any,
    company: Optional[Dict[str, Any]] = None,
    customer: Optional[Dict[str, Any]] = None
) -> str:
    """Generate professional PDF for Consolidated Item-Wise Report.
    Supports either (report_data, output_path) or (output_path, report_data).
    Matches the 7-page reference PDF structure precisely.
    """
    if isinstance(arg1, str) and (isinstance(arg2, dict) or hasattr(arg2, "get")):
        output_path, report_data = arg1, arg2
    elif isinstance(arg2, str) and (isinstance(arg1, dict) or hasattr(arg1, "get")):
        report_data, output_path = arg1, arg2
    else:
        output_path, report_data = str(arg1), arg2

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    comp = dict(company) if company else {}
    cust = dict(customer) if customer else {}

    # Defaults for company
    comp_name = comp.get("name") or settings.default_company_name
    comp_addr = comp.get("address") or "No. E-2 Periyar Vegetable Market, Koyambedu, Chennai - 600092."
    comp_phone = comp.get("phone") or "9380645132 , 9382179443 , 9444042275"

    # Defaults for customer / bill_to
    bill_to_name = (
        report_data.get("bill_to")
        or cust.get("bill_to_name")
        or cust.get("name")
        or "Customer"
    )
    bill_to_addr = (
        cust.get("bill_to_address")
        or cust.get("address")
        or ""
    ).strip().replace("\n", " ")
    bill_to_phone = (
        cust.get("bill_to_phone")
        or cust.get("contact_person_phone")
        or cust.get("phone")
        or ""
    ).strip()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=75 * mm,  # Space reserved for header + Bill To box on every page
        bottomMargin=15 * mm
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom Typography Styles
    title_report_style = ParagraphStyle(
        name="RepTitle",
        parent=styles["Heading1"],
        fontSize=15,
        alignment=TA_CENTER,
        fontName=FONT_BOLD,
        textColor=EMERALD_GREEN,
        spaceAfter=6
    )
    table_text_style = ParagraphStyle(
        name="TabTxt",
        parent=styles["Normal"],
        fontSize=8.5,
        fontName=FONT_NORMAL,
        alignment=TA_LEFT,
        leading=11
    )
    group_header_style = ParagraphStyle(
        name="GrpHdr",
        parent=styles["Normal"],
        fontSize=10,
        fontName=FONT_BOLD,
        textColor=colors.black,
        leading=14,
        spaceBefore=4,
        spaceAfter=4
    )

    # Dynamic Header Drawer (called on first page and later pages)
    def draw_report_header(canvas, doc_ref):
        canvas.saveState()
        width, height = doc_ref.pagesize
        left_margin = doc_ref.leftMargin
        right_margin = doc_ref.rightMargin
        content_width = width - left_margin - right_margin

        # 1. Company Name (Center, Emerald Green)
        header_style = ParagraphStyle(
            name="HeaderC",
            parent=styles["Normal"],
            fontSize=16,
            alignment=TA_CENTER,
            fontName=FONT_BOLD,
            textColor=EMERALD_GREEN
        )
        p_company = Paragraph(comp_name, header_style)
        p_company.wrap(content_width, 25 * mm)
        p_company.drawOn(canvas, left_margin, height - 18 * mm)

        # 2. Company Address & Phone
        info_style = ParagraphStyle(
            name="InfoC",
            parent=styles["Normal"],
            fontSize=9.5,
            alignment=TA_CENTER,
            leading=12,
            textColor=EMERALD_GREEN
        )
        contact_info = f"{comp_addr}<br/>Ph: {comp_phone}"
        p_info = Paragraph(contact_info, info_style)
        p_info.wrap(content_width, 25 * mm)
        p_info.drawOn(canvas, left_margin, height - 28 * mm)

        # 3. Report Title & Date Range
        date_range = report_data.get("date_range", {})
        from_date = date_range.get("start", "")
        to_date = date_range.get("end", "")
        title_style = ParagraphStyle(
            name="TitleC",
            parent=styles["Normal"],
            fontSize=11,
            alignment=TA_CENTER,
            fontName=FONT_BOLD,
            textColor=EMERALD_GREEN
        )
        p_title = Paragraph(f"Consolidated Bills - From {from_date} To {to_date}", title_style)
        p_title.wrap(content_width, 15 * mm)
        p_title.drawOn(canvas, left_margin, height - 37 * mm)

        # 4. Bill To Box (Rectangle with black border)
        bill_to_html = f"<b>Bill To:</b><br/>{bill_to_name}"
        if bill_to_addr:
            bill_to_html += f"<br/>{bill_to_addr}"
        if bill_to_phone:
            bill_to_html += f"<br/>Ph: {bill_to_phone}"

        small_style = ParagraphStyle(
            "BillToText",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            fontName=FONT_NORMAL
        )
        grid_data = [[Paragraph(bill_to_html, small_style)]]
        grid_table = Table(grid_data, colWidths=[content_width])
        grid_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        grid_table.wrap(content_width, 35 * mm)
        grid_table.drawOn(canvas, left_margin, height - 67 * mm)

        canvas.restoreState()

    # ---------------- Section 1: Bill Summary ----------------
    elements.append(Paragraph("BILL SUMMARY", group_header_style))
    elements.append(Spacer(1, 2 * mm))

    summary_data = [["Inv. Date", "Inv. Number", "Ship TO: (Customer Name)", "Amount"]]
    for bill in report_data.get("bill_summary", []):
        inv_date = bill.get("date", "")
        try:
            dt = datetime.strptime(inv_date[:10], "%Y-%m-%d")
            inv_date = dt.strftime("%d/%m/%Y")
        except Exception:
            logging.getLogger(__name__).warning("Ignored error", exc_info=True)

        amt_val = float(bill.get("amount", 0.0))
        summary_data.append([
            inv_date,
            bill.get("invoice_no", ""),
            bill.get("ship_to", ""),
            f"{amt_val:.2f}"
        ])

    st = Table(summary_data, colWidths=[28 * mm, 34 * mm, 93 * mm, 35 * mm])
    st.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(st)
    elements.append(Spacer(1, 10 * mm))
    elements.append(PageBreak())

    # ---------------- Section 2: Ship To Itemized Groups ----------------
    ship_to_reports = report_data.get("ship_to_reports", [])
    for idx, ship_to in enumerate(ship_to_reports):
        ship_name = ship_to.get("ship_to", "Location")
        elements.append(Paragraph(f"Ship To: {ship_name}", group_header_style))
        elements.append(Spacer(1, 2 * mm))

        table_data = [["Sno", "Item Description", "Qty", "Unit", "Avg. Rate", "Amount"]]
        for i, item in enumerate(ship_to.get("items", []), 1):
            qty_val = float(item.get("qty", 0.0))
            rate_val = float(item.get("rate", 0.0))
            amt_val = float(item.get("amount", 0.0))
            table_data.append([
                str(i),
                Paragraph(item.get("name", ""), table_text_style),
                f"{qty_val:.3f}",
                item.get("unit", "kg"),
                f"{rate_val:.2f}",
                f"{amt_val:.2f}"
            ])

        tot_ship = float(ship_to.get("total_amount", 0.0))
        table_data.append(["", "Group Total", "", "", "", f"{tot_ship:.2f}"])

        t = Table(table_data, colWidths=[10 * mm, 85 * mm, 20 * mm, 15 * mm, 25 * mm, 35 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (2, 1), (2, -1), "RIGHT"),
            ("ALIGN", (3, 1), (3, -1), "CENTER"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
            ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        elements.append(t)
        elements.append(PageBreak())

    # ---------------- Section 3: Grand Total Consolidation ----------------
    elements.append(Paragraph("GRAND TOTAL CONSOLIDATION", title_report_style))
    elements.append(Spacer(1, 2 * mm))

    grant_table_data = [["Consolidated Item", "Total Qty", "Unit", "Rate", "Total Amount"]]
    for item in report_data.get("grand_total_consolidation", []):
        qty_val = float(item.get("qty", 0.0))
        rate_val = float(item.get("rate", 0.0))
        amt_val = float(item.get("amount", 0.0))
        grant_table_data.append([
            Paragraph(item.get("name", ""), table_text_style),
            f"{qty_val:.3f}",
            item.get("unit", "kg"),
            f"{rate_val:.2f}",
            f"{amt_val:.2f}"
        ])

    grand_total_val = float(report_data.get("total_bill_amount", 0.0))
    grant_table_data.append([
        "Report Period Net Total", "", "", "", f"{grand_total_val:.2f}"
    ])

    gt = Table(grant_table_data, colWidths=[95 * mm, 25 * mm, 15 * mm, 25 * mm, 30 * mm])
    gt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfdf5")),
        ("TEXTCOLOR", (0, -1), (-1, -1), EMERALD_GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(gt)

    # Build the PDF document
    doc.build(elements, onFirstPage=draw_report_header, onLaterPages=draw_report_header)
    return output_path
