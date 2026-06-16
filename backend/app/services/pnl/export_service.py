"""P&L export: CSV and PDF generation.

AI rules: never modifies source financial records. Read-only computation.
"""
import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.pnl import PnLReportResponse

# Tahinis brand colors
_NAVY = colors.HexColor("#1e2d6b")
_RED = colors.HexColor("#d42b2b")
_LIGHT_GREY = colors.HexColor("#f5f5f5")
_MID_GREY = colors.HexColor("#e0e0e0")


def _fmt_cad(val: Optional[Decimal], show_pct: Optional[Decimal] = None) -> str:
    if val is None:
        return "—"
    formatted = f"${val:,.2f}"
    if show_pct is not None:
        formatted += f"  ({show_pct:.1f}%)"
    return formatted


def _pct(val: Optional[Decimal]) -> str:
    if val is None:
        return "—"
    return f"{val:.1f}%"


def generate_csv(report: PnLReportResponse, location_name: str = "All Locations") -> bytes:
    """Return UTF-8 encoded CSV bytes for the P&L report."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    li = report.line_items

    writer.writerow(["Tahini's P&L Report"])
    writer.writerow(["Location", location_name])
    writer.writerow(["Period", f"{report.period_start} to {report.period_end}"])
    writer.writerow(["Currency", report.currency_code])
    writer.writerow(["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])

    writer.writerow(["Line Item", "Amount (CAD)", "% of Net Revenue"])
    writer.writerow(["Gross Revenue", _fmt_cad(li.gross_revenue), ""])
    writer.writerow(["Total Discounts", _fmt_cad(li.total_discounts), ""])
    writer.writerow(["Net Revenue", _fmt_cad(li.net_revenue), "100.0%"])
    writer.writerow([])
    writer.writerow(["COGS", _fmt_cad(li.cogs), _pct(li.cogs_pct)])
    writer.writerow(["Gross Profit", _fmt_cad(li.gross_profit), ""])
    writer.writerow([])
    writer.writerow(["Labor Cost", _fmt_cad(li.labor_cost), _pct(li.labor_pct)])
    writer.writerow(["Prime Cost", _fmt_cad(li.prime_cost), _pct(li.prime_cost_pct)])
    writer.writerow([])
    writer.writerow(["Operating Expenses", _fmt_cad(li.operating_expenses), ""])
    writer.writerow(["EBITDA", _fmt_cad(li.ebitda), _pct(li.ebitda_pct)])
    writer.writerow(["Net Profit", _fmt_cad(li.net_profit), _pct(li.net_profit_pct)])
    writer.writerow([])

    writer.writerow(["Orders", str(report.order_count)])
    writer.writerow([])

    if report.expense_breakdown:
        writer.writerow(["Expense Category Breakdown"])
        writer.writerow(["Category", "Amount (CAD)", "Count"])
        for cat in sorted(report.expense_breakdown, key=lambda x: float(x.total or 0), reverse=True):
            writer.writerow([cat.category, _fmt_cad(cat.total), str(cat.expense_count)])

    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


def generate_pdf(report: PnLReportResponse, location_name: str = "All Locations") -> bytes:
    """Return PDF bytes for the P&L report using reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TahiniTitle",
        parent=styles["Heading1"],
        textColor=_NAVY,
        fontSize=18,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "TahiniSubtitle",
        parent=styles["Normal"],
        textColor=colors.HexColor("#666666"),
        fontSize=10,
        spaceAfter=2,
    )
    section_style = ParagraphStyle(
        "TahiniSection",
        parent=styles["Heading2"],
        textColor=_NAVY,
        fontSize=12,
        spaceBefore=12,
        spaceAfter=4,
    )

    li = report.line_items
    story = []

    # Header
    story.append(Paragraph("Tahini's Restaurant", title_style))
    story.append(Paragraph("Profit & Loss Report", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Location: {location_name}", subtitle_style))
    story.append(
        Paragraph(f"Period: {report.period_start} to {report.period_end}", subtitle_style)
    )
    story.append(
        Paragraph(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 16))

    # P&L table
    story.append(Paragraph("Income Statement", section_style))

    pnl_rows = [
        ["Line Item", "Amount (CAD)", "% of Revenue"],
        ["Gross Revenue", _fmt_cad(li.gross_revenue), ""],
        ["  Less: Discounts", f"({_fmt_cad(li.total_discounts)})" if li.total_discounts else "—", ""],
        ["Net Revenue", _fmt_cad(li.net_revenue), "100.0%"],
        ["", "", ""],
        ["Cost of Goods Sold (COGS)", _fmt_cad(li.cogs), _pct(li.cogs_pct)],
        ["Gross Profit", _fmt_cad(li.gross_profit), ""],
        ["", "", ""],
        ["Labor Cost", _fmt_cad(li.labor_cost), _pct(li.labor_pct)],
        ["Prime Cost (COGS + Labor)", _fmt_cad(li.prime_cost), _pct(li.prime_cost_pct)],
        ["", "", ""],
        ["Operating Expenses", _fmt_cad(li.operating_expenses), ""],
        ["EBITDA", _fmt_cad(li.ebitda), _pct(li.ebitda_pct)],
        ["Net Profit", _fmt_cad(li.net_profit), _pct(li.net_profit_pct)],
    ]

    col_widths = [3.2 * inch, 2.2 * inch, 1.5 * inch]
    t = Table(pnl_rows, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
                # Body
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_GREY]),
                # Net Revenue bold
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                ("LINEBELOW", (0, 3), (-1, 3), 0.5, _MID_GREY),
                # Net Profit bold + red
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, -1), (-1, -1), _RED),
                ("LINEABOVE", (0, -1), (-1, -1), 1, _NAVY),
                ("LINEBELOW", (0, -1), (-1, -1), 1.5, _NAVY),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.25, _MID_GREY),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"Orders: {report.order_count:,}",
            ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
        )
    )

    # Expense breakdown
    if report.expense_breakdown:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Expense Category Breakdown", section_style))

        sorted_cats = sorted(
            report.expense_breakdown, key=lambda x: float(x.total or 0), reverse=True
        )
        exp_rows = [["Category", "Amount (CAD)", "# Expenses"]] + [
            [cat.category, _fmt_cad(cat.total), str(cat.expense_count)]
            for cat in sorted_cats
        ]

        et = Table(exp_rows, colWidths=[3.2 * inch, 2.2 * inch, 1.5 * inch])
        et.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT_GREY]),
                    ("GRID", (0, 0), (-1, -1), 0.25, _MID_GREY),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(et)

    # Footer
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "This report was generated by Tahini's Financial Intelligence Platform. "
            "All figures are in Canadian Dollars (CAD). For accounting purposes only.",
            ParagraphStyle(
                "footer",
                parent=styles["Normal"],
                fontSize=7,
                textColor=colors.HexColor("#999999"),
            ),
        )
    )

    doc.build(story)
    return buf.getvalue()
