"""Credit note (goods returned by a customer) and debit note (goods returned to a supplier) PDFs."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.config.settings import settings
from app.printing.invoice import _pdf_fonts
from app.utils.currency import amount_in_words
from app.utils.formatters import format_date


def _build_note_pdf(path: str, *, title: str, number_label: str, doc: Dict[str, Any], reference_label: str, reference: str,
                    party_label: str, party: Dict[str, Any], company: Optional[Dict[str, Any]], money_rows: list,
                    total_label: str, total: float, footer_note: str, show_waste: bool = False) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    comp = company or {}
    reg, bold, sym = _pdf_fonts()
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NNormal", parent=styles["Normal"], fontName=reg, fontSize=9, leading=12)
    head = ParagraphStyle("NHead", parent=styles["Heading1"], fontName=bold, fontSize=18, leading=22, textColor=colors.HexColor("#b45309"), alignment=1)
    sub = ParagraphStyle("NSub", parent=normal, alignment=1)
    doc_pdf = SimpleDocTemplate(path, pagesize=A4, rightMargin=10 * mm, leftMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm)
    story = []

    name = comp.get("name") or settings.default_company_name.upper()
    story.append(Paragraph(name, head))
    story.append(Paragraph(f"{comp.get('address') or ''}<br/>Ph: {comp.get('phone') or ''} | Email: {comp.get('email') or ''}", sub))
    story.append(Spacer(1, 4 * mm))

    banner = Table([[title]], colWidths=[190 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#b45309")), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                                ("FONTNAME", (0, 0), (-1, -1), bold), ("FONTSIZE", (0, 0), (-1, -1), 11), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    story.append(banner)
    story.append(Spacer(1, 3 * mm))

    p_name = party.get("bill_to_name") or party.get("name") or doc.get("customer_name") or doc.get("supplier_name") or ""
    p_addr = party.get("bill_to_address") or party.get("address") or ""
    p_phone = party.get("bill_to_phone") or party.get("contact_person_phone") or party.get("phone") or ""
    details = Table([[Paragraph(f"<b>{party_label}:</b><br/><b>{p_name}</b><br/>{p_addr}<br/>Ph: {p_phone}", normal),
                      Paragraph(f"<b>{number_label}:</b> {doc.get('return_id')}<br/>Date: {format_date(doc.get('return_date'))}<br/>"
                                f"{reference_label}: <b>{reference}</b><br/>Reason: {doc.get('notes') or '-'}", normal)]],
                    colWidths=[95 * mm, 95 * mm])
    details.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(details)
    story.append(Spacer(1, 4 * mm))

    header = ["Sno", "Description", "Qty", "Unit", f"Rate ({sym})", f"Amount ({sym})"]
    if show_waste:
        header.insert(4, "Condition")
    data = [header]
    for n, it in enumerate(doc.get("items", []), 1):
        row = [str(n), it.get("name", ""), f"{float(it.get('qty', 0)):g}", it.get("unit", ""), f"{float(it.get('rate', 0)):.2f}", f"{float(it.get('amount', 0)):.2f}"]
        if show_waste:
            row.insert(4, "Spoiled" if it.get("is_waste") else "Good")
        data.append(row)
    widths = [12 * mm, 72 * mm, 18 * mm, 16 * mm, 22 * mm, 26 * mm, 24 * mm] if show_waste else [12 * mm, 82 * mm, 18 * mm, 18 * mm, 26 * mm, 34 * mm]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black), ("FONTNAME", (0, 0), (-1, -1), reg), ("FONTNAME", (0, 0), (-1, 0), bold),
                               ("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (2, 0), (2, -1), "RIGHT"), ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    if money_rows:
        rows = Table([[Paragraph(label, normal), Paragraph(f"{sym}{value:,.2f}", ParagraphStyle("R", parent=normal, alignment=2))] for label, value in money_rows],
                     colWidths=[150 * mm, 40 * mm])
        story.append(rows)
    story.append(Paragraph(f"<b>Amount in Words:</b> {amount_in_words(total)}", normal))
    story.append(Paragraph(f"<b>{total_label}: {sym}{total:,.2f}</b>", ParagraphStyle("Tot", parent=normal, fontName=reg, fontSize=12, alignment=2)))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(footer_note, normal))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(f"<b>For {name}</b><br/><br/><br/>{comp.get('signatory_label') or 'Authorized Signatory'}",
                           ParagraphStyle("Sig", parent=normal, alignment=2)))
    doc_pdf.build(story)
    return path


def generate_credit_note_pdf(path: str, ret: Dict[str, Any], company: Optional[Dict[str, Any]] = None,
                             customer: Optional[Dict[str, Any]] = None) -> str:
    """Credit note for goods a customer returned against an invoice."""
    total = float(ret.get("total_refund_amount", 0.0))
    walk_in = not ret.get("customer_id") or ret.get("customer_id") == "CASH"
    footer = (f"Refunded by {ret.get('refund_method') or 'Cash'}." if walk_in else
              "Credited to the customer's account." if "applied_to_bill" not in ret else
              f"Credited to the customer's account: Rs {float(ret.get('applied_to_bill', 0.0)):,.2f} against the invoice"
              + (f", Rs {float(ret.get('credit_amount', 0.0)):,.2f} held as credit." if float(ret.get("credit_amount", 0.0)) > 0 else "."))
    return _build_note_pdf(path, title="CREDIT NOTE", number_label="Credit note no", doc=ret, reference_label="Against invoice",
                           reference=ret.get("original_invoice_no", ""), party_label="CREDITED TO", party=customer or {}, company=company,
                           money_rows=[], total_label="Credit total", total=total, footer_note=footer, show_waste=True)


def generate_debit_note_pdf(path: str, ret: Dict[str, Any], company: Optional[Dict[str, Any]] = None,
                            supplier: Optional[Dict[str, Any]] = None) -> str:
    """Debit note for goods sent back to a supplier against their invoice."""
    gross, tds, net = float(ret.get("gross_amount", 0.0)), float(ret.get("tds_amount", 0.0)), float(ret.get("net_amount", 0.0))
    rows = [("Value of goods returned", gross)]
    if tds:
        rows.append(("Less: TDS that comes back", -tds))
    credit = float(ret.get("credit_amount", 0.0))
    footer = (f"Reduces the amount payable against vendor bill {ret.get('supplier_bill_no') or ret.get('purchase_id')}: Rs {float(ret.get('applied_to_bill', 0.0)):,.2f}"
              + (f"; Rs {credit:,.2f} remains as credit with the supplier." if credit > 0 else "."))
    return _build_note_pdf(path, title="DEBIT NOTE", number_label="Debit note no", doc=ret, reference_label="Against vendor bill",
                           reference=f"{ret.get('supplier_bill_no') or ''} ({ret.get('purchase_id')})", party_label="RETURNED TO",
                           party=supplier or {}, company=company, money_rows=rows, total_label="Debit note total", total=net, footer_note=footer)
