"""P&L export: CSV and PDF generation.

AI rules: never modifies source financial records. Read-only computation.
"""
import csv
import io
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
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

_DEFAULT_TIMEZONE = "America/Toronto"
# White/red mark on a transparent background — drawn onto a reportlab-filled _NAVY
# banner rather than baked into a navy JPG, so the two navy shades never mismatch.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "static" / "tahinis-mark.png"
_LOGO_ASPECT = 435 / 1052  # height / width of the source asset


def _resolve_timezone(tz_name: Optional[str]) -> ZoneInfo:
    """Locations default to UTC in the DB until an owner sets one in Settings."""
    try:
        return ZoneInfo(tz_name) if tz_name and tz_name != "UTC" else ZoneInfo(_DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(_DEFAULT_TIMEZONE)


def _generated_at(tz_name: Optional[str]) -> str:
    local = datetime.now(dt_timezone.utc).astimezone(_resolve_timezone(tz_name))
    return local.strftime("%Y-%m-%d %H:%M %Z")


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


def generate_csv(
    report: PnLReportResponse,
    location_name: str = "All Locations",
    location_timezone: Optional[str] = None,
) -> bytes:
    """Return UTF-8 encoded CSV bytes for the P&L report."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    li = report.line_items

    writer.writerow(["Tahini's P&L Report"])
    writer.writerow(["Location", location_name])
    writer.writerow(["Period", f"{report.period_start} to {report.period_end}"])
    writer.writerow(["Currency", report.currency_code])
    writer.writerow(["Generated", _generated_at(location_timezone)])
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


def _money(v) -> str:
    if v is None:
        return ""
    return f"${Decimal(str(v)):,.2f}"


def generate_bank_csv(
    report: dict,
    location_name: str = "All Locations",
    location_timezone: Optional[str] = None,
) -> bytes:
    """Bank-statement-basis P&L as CSV.

    Fixed 4-column grid (Line, Before HST, After HST, Note) so every row lines up
    in a spreadsheet — no ragged/empty trailing cells."""
    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["Tahini's P&L Report — Bank Statement Basis", "", "", ""])
    w.writerow(["Location", location_name, "", ""])
    w.writerow(["Period", f"{report['period_start']} to {report['period_end']}", "", ""])
    w.writerow(["Generated", _generated_at(location_timezone), "", ""])
    w.writerow(["", "", "", ""])

    before, after = report["before_hst"], report["after_hst"]
    w.writerow(["Line", "Before HST", "After HST", ""])
    w.writerow(["Revenue", _money(before["revenue"]), _money(after["revenue"]), ""])
    w.writerow(["COGS", _money(report["cogs"]), _money(report["cogs"]), ""])
    w.writerow(["Labor", _money(report["labor"]), _money(report["labor"]), ""])
    w.writerow(["Operating Expenses", _money(report["operating_expenses"]), _money(report["operating_expenses"]), ""])
    w.writerow(["EBITDA", _money(before["ebitda"]), _money(after["ebitda"]), ""])
    w.writerow(["Interest & Financing", _money(report["interest"]), _money(report["interest"]), ""])
    w.writerow(["Net Profit", _money(before["net_profit"]), _money(after["net_profit"]), ""])
    w.writerow(["", "", "", ""])

    hst = report["hst"]
    w.writerow(["HST", "Amount", "", ""])
    w.writerow(["Collected on sales", _money(hst["collected_on_sales"]), "", ""])
    w.writerow(["Input tax credits (ITC)", _money(hst["input_tax_credits"]), "", ""])
    w.writerow(["Net HST owed to CRA", _money(hst["net_remittance"]), "", ""])
    w.writerow(["", "", "", ""])

    w.writerow(["Revenue by channel", "Amount", "", ""])
    for ch, amt in sorted(report["revenue_by_channel"].items(), key=lambda x: -float(x[1] or 0)):
        w.writerow([ch, _money(amt), "", ""])
    w.writerow(["Total revenue", _money(report["revenue"]), "", ""])
    w.writerow(["", "", "", ""])

    w.writerow(["Expense category", "Amount", "", ""])
    for cat, amt in sorted(report["expense_by_category"].items(), key=lambda x: -float(x[1] or 0)):
        w.writerow([cat, _money(amt), "", ""])
    if float(report.get("principal_excluded") or 0) > 0:
        w.writerow(["Loan principal (excluded, balance-sheet)", _money(report["principal_excluded"]), "", ""])
    w.writerow(["", "", "", ""])

    # Partner distribution — mirrors the three P&L tables exactly (period net +
    # QTD + YTD), for each HST basis: After HST, Before HST, 33% HST remitted.
    quarter = report.get("quarter") or {}
    ytd = report.get("ytd") or {}

    def _find(rep: dict, name: str) -> dict | None:
        for row in rep.get("partner_split", []):
            if row["name"] == name:
                return row
        return None

    def _net(rep: dict, name: str, key: str):
        row = _find(rep, name)
        return row[key] if row else None

    def _net33(rep: dict, share_pct) -> Decimal | None:
        """Net at the 33%-of-collected-HST remittance, per partner share."""
        if not rep:
            return None
        collected = Decimal(str(rep["hst"]["collected_on_sales"]))
        net_co = Decimal(str(rep["before_hst"]["net_profit"])) - collected * Decimal("0.33")
        return net_co * (Decimal(str(share_pct)) / Decimal("100"))

    def _partner_block(title: str, key: str | None) -> None:
        w.writerow([title, "Net", "QTD", "YTD"])
        for p in report["partner_split"]:
            name = p["name"]
            label = f"{name} ({Decimal(str(p['share_pct'])):g}%)"
            if key is not None:  # After / Before HST — read net straight from split
                w.writerow([
                    label,
                    _money(p[key]),
                    _money(_net(quarter, name, key)),
                    _money(_net(ytd, name, key)),
                ])
            else:  # 33% HST — derived from collected HST + share
                w.writerow([
                    label,
                    _money(_net33(report, p["share_pct"])),
                    _money(_net33(quarter, p["share_pct"])),
                    _money(_net33(ytd, p["share_pct"])),
                ])
        w.writerow(["", "", "", ""])

    _partner_block("Partner distribution (After HST)", "net_after_hst")
    _partner_block("Partner distribution (Before HST)", "net_before_hst")
    _partner_block("Partner distribution (33% HST remitted)", None)

    # Partner revenue split (before / after HST) for reference.
    w.writerow(["Partner", "Revenue (before)", "Revenue (after)", ""])
    for p in report["partner_split"]:
        w.writerow([
            f"{p['name']} ({Decimal(str(p['share_pct'])):g}%)",
            _money(p["revenue_before_hst"]), _money(p["revenue_after_hst"]), "",
        ])

    return buf.getvalue().encode("utf-8-sig")


def generate_pdf(
    report: PnLReportResponse,
    location_name: str = "All Locations",
    location_timezone: Optional[str] = None,
) -> bytes:
    """Return PDF bytes for the P&L report using reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TahiniTitle",
        parent=styles["Heading1"],
        textColor=colors.white,
        fontSize=19,
        alignment=2,  # right
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "TahiniSubtitle",
        parent=styles["Normal"],
        textColor=colors.HexColor("#c7cbe8"),
        fontSize=10,
        alignment=2,  # right
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

    # Letterhead — full-width navy banner: logo left, title + meta right in white, red accent below
    content_width = letter[0] - doc.leftMargin - doc.rightMargin
    logo_width = 2.1 * inch
    meta_lines = [
        Paragraph("Profit & Loss Report", title_style),
        Paragraph(f"Location: {location_name}", subtitle_style),
        Paragraph(f"Period: {report.period_start} to {report.period_end}", subtitle_style),
        Paragraph(f"Generated: {_generated_at(location_timezone)}", subtitle_style),
    ]
    if _LOGO_PATH.exists():
        logo = Image(str(_LOGO_PATH), width=logo_width, height=logo_width * _LOGO_ASPECT)
        header = Table(
            [[logo, meta_lines]],
            colWidths=[logo_width + 0.5 * inch, content_width - logo_width - 0.5 * inch],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (0, 0), 20),
                    ("RIGHTPADDING", (1, 0), (1, 0), 20),
                    ("TOPPADDING", (0, 0), (-1, -1), 18),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
                ]
            )
        )
        story.append(header)
    else:
        story.extend(meta_lines)
    story.append(HRFlowable(width=content_width, thickness=3, color=_RED, spaceBefore=0, spaceAfter=16))

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
