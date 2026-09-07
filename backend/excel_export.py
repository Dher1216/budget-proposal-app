"""
Builds an .xlsx report that mirrors the province's existing format:
office header row, then a grouped-header table, then each classification's
accounts in ascending code order, with a subtotal row per classification and
a grand total row at the end.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

CLASSIFICATION_LABELS = {
    "PS": "PERSONAL SERVICES",
    "MOOE": "MAINTENANCE AND OTHER OPERATING EXPENDITURES",
    "FE": "FINANCIAL EXPENSES",
    "CO": "CAPITAL OUTLAY",
}
CLASSIFICATION_ORDER = ["PS", "MOOE", "FE", "CO"]

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
SECTION_FILL = PatternFill("solid", fgColor="EFEFEF")
CURRENCY_FMT = '#,##0.00;(#,##0.00);"-"'


def build_report_workbook(proposal: dict) -> io.BytesIO:
    """
    proposal: dict shaped like schemas.ProposalOut, e.g.
    {
      "office_name": ..., "office_code": ..., "office_sector": ...,
      "year": 2027, "budget_type": "annual",
      "lines": [ {classification, account_code, account_name,
                  prev_year_actual, current_annual, current_supplemental,
                  current_total, proposed_amount, difference, approved_amount}, ... ]
    }
    """
    year = proposal["year"]
    prev_year = year - 2
    current_year = year - 1

    wb = Workbook()
    ws = wb.active
    ws.title = "Budget Report"

    ncols = 11  # A..K (existing A..I, plus Remarks, Supporting Documents)

    # ---- Title row ----
    title_bits = [proposal["office_name"]]
    meta = []
    if proposal.get("office_code"):
        meta.append(proposal["office_code"])
    if proposal.get("office_sector"):
        meta.append(proposal["office_sector"])
    if meta:
        title_bits.append(f"({', '.join(meta)})")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=" ".join(title_bits))
    c.font = Font(name="Arial", bold=True, size=13)
    c.alignment = Alignment(horizontal="center")

    if proposal["budget_type"] == "annual":
        subtitle = f"ANNUAL BUDGET PROPOSAL - CY {year}"
    else:
        supp_no = proposal.get("supplemental_number") or 1
        subtitle = f"SUPPLEMENTAL BUDGET NO. {supp_no} PROPOSAL - CY {year}"
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font = Font(name="Arial", bold=True, size=11)
    c.alignment = Alignment(horizontal="center")

    # ---- Header rows (4 and 5) ----
    header_row_top = 4
    header_row_bot = 5

    ws.merge_cells(start_row=header_row_top, start_column=1, end_row=header_row_bot, end_column=1)
    ws.cell(row=header_row_top, column=1, value="Object of Expenditures")

    ws.merge_cells(start_row=header_row_top, start_column=2, end_row=header_row_bot, end_column=2)
    ws.cell(row=header_row_top, column=2, value="Account Code")

    ws.merge_cells(start_row=header_row_top, start_column=3, end_row=header_row_bot, end_column=3)
    ws.cell(row=header_row_top, column=3, value=f"Past Year {prev_year}\n(Actual)")

    ws.merge_cells(start_row=header_row_top, start_column=4, end_row=header_row_top, end_column=6)
    ws.cell(row=header_row_top, column=4, value=f"For the Year {current_year}")
    ws.cell(row=header_row_bot, column=4, value="Annual Budget")
    ws.cell(row=header_row_bot, column=5, value="Supplemental Budget")
    ws.cell(row=header_row_bot, column=6, value="Total (Annual + Supplemental)")

    ws.merge_cells(start_row=header_row_top, start_column=7, end_row=header_row_top, end_column=9)
    ws.cell(row=header_row_top, column=7, value=f"For the Year {year} Budget (Estimates)")
    ws.cell(row=header_row_bot, column=7, value="Budget Proposal")
    ws.cell(row=header_row_bot, column=8, value=f"Difference ({current_year} total vs Proposed)")
    ws.cell(row=header_row_bot, column=9, value="Approved")

    ws.merge_cells(start_row=header_row_top, start_column=10, end_row=header_row_bot, end_column=10)
    ws.cell(row=header_row_top, column=10, value="Remarks")

    ws.merge_cells(start_row=header_row_top, start_column=11, end_row=header_row_bot, end_column=11)
    ws.cell(row=header_row_top, column=11, value="Supporting Documents")

    for row in (header_row_top, header_row_bot):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = Font(name="Arial", bold=True, size=9)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.fill = HEADER_FILL
            cell.border = BORDER

    # ---- Body ----
    row_idx = header_row_bot + 1
    grand_totals = [0.0] * 7  # prev, curr_annual, curr_supp, curr_total, proposed, diff, approved

    lines_by_class = {k: [] for k in CLASSIFICATION_ORDER}
    for line in proposal["lines"]:
        lines_by_class.setdefault(line["classification"], []).append(line)

    for classification in CLASSIFICATION_ORDER:
        lines = lines_by_class.get(classification, [])
        if not lines:
            continue
        lines = sorted(lines, key=lambda l: (l["account_code"], l["account_name"]))

        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=ncols)
        cell = ws.cell(row=row_idx, column=1, value=CLASSIFICATION_LABELS[classification])
        cell.font = Font(name="Arial", bold=True, size=10)
        cell.fill = SECTION_FILL
        cell.border = BORDER
        row_idx += 1

        section_totals = [0.0] * 7
        for line in lines:
            approved = line.get("approved_amount")
            attachment_names = "; ".join(a["filename"] for a in line.get("attachments", []))
            values = [
                line["account_name"], line["account_code"],
                line["prev_year_actual"], line["current_annual"], line["current_supplemental"],
                line["current_total"], line["proposed_amount"], line["difference"],
                approved if approved is not None else "",
                line.get("remarks") or "",
                attachment_names,
            ]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.font = Font(name="Arial", size=9)
                cell.border = BORDER
                if 3 <= col <= 9:
                    cell.number_format = CURRENCY_FMT
                    cell.alignment = Alignment(horizontal="right")
                elif col in (10, 11):
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            for i, key in enumerate(["prev_year_actual", "current_annual", "current_supplemental",
                                      "current_total", "proposed_amount", "difference"]):
                section_totals[i] += line[key]
            if approved is not None:
                section_totals[6] += approved
            row_idx += 1

        subtotal_label = f"Total {CLASSIFICATION_LABELS[classification]}"
        ws.cell(row=row_idx, column=1, value=subtotal_label).font = Font(name="Arial", bold=True, size=9)
        ws.cell(row=row_idx, column=2).border = BORDER
        for i, col in enumerate(range(3, 10)):
            cell = ws.cell(row=row_idx, column=col, value=section_totals[i])
            cell.font = Font(name="Arial", bold=True, size=9)
            cell.number_format = CURRENCY_FMT
            cell.alignment = Alignment(horizontal="right")
            cell.border = BORDER
            cell.fill = SECTION_FILL
            grand_totals[i] += section_totals[i]
        for col in (10, 11):
            c2 = ws.cell(row=row_idx, column=col)
            c2.border = BORDER
            c2.fill = SECTION_FILL
        ws.cell(row=row_idx, column=1).border = BORDER
        ws.cell(row=row_idx, column=1).fill = SECTION_FILL
        row_idx += 1

    # ---- Grand total ----
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=2)
    cell = ws.cell(row=row_idx, column=1, value="GRAND TOTAL")
    cell.font = Font(name="Arial", bold=True, size=10)
    cell.fill = HEADER_FILL
    cell.border = BORDER
    ws.cell(row=row_idx, column=2).border = BORDER
    ws.cell(row=row_idx, column=2).fill = HEADER_FILL
    for i, col in enumerate(range(3, 10)):
        cell = ws.cell(row=row_idx, column=col, value=grand_totals[i])
        cell.font = Font(name="Arial", bold=True, size=10)
        cell.number_format = CURRENCY_FMT
        cell.alignment = Alignment(horizontal="right")
        cell.border = BORDER
        cell.fill = HEADER_FILL
    for col in (10, 11):
        c2 = ws.cell(row=row_idx, column=col)
        c2.border = BORDER
        c2.fill = HEADER_FILL

    # ---- Column widths ----
    widths = [42, 14, 14, 14, 16, 18, 14, 20, 14, 30, 30]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[header_row_top].height = 30
    ws.row_dimensions[header_row_bot].height = 42

    ws.freeze_panes = ws.cell(row=header_row_bot + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
