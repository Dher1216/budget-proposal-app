"""
Builds the downloadable .xlsx reports:
  - build_report_workbook: one office's proposal, mirroring the province's
    existing format (office header, grouped columns, classification
    subtotals, grand total).
  - build_summary_workbook: a consolidated report totalling every office's
    proposal per account, for a given budget cycle.
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
    proposal: dict shaped like schemas.ProposalOut.
    """
    year = proposal["year"]
    prev_year = year - 2
    current_year = year - 1

    # How many "current year supplemental" reference columns does this
    # proposal actually use? Look at the widest line.
    max_supp = 0
    for line in proposal["lines"]:
        for s in line.get("current_supplementals", []):
            max_supp = max(max_supp, s["supplemental_number"])
    supp_col_count = max(max_supp, 1)  # always show at least one supplemental column

    wb = Workbook()
    ws = wb.active
    ws.title = "Budget Report"

    col_prev = 3
    col_annual = 4
    col_supp_start = 5
    col_supp_end = col_supp_start + supp_col_count - 1
    col_total = col_supp_end + 1
    col_proposed = col_total + 1
    col_diff = col_proposed + 1
    col_docs = col_diff + 1
    col_remarks = col_docs + 1
    col_adjusted = col_remarks + 1
    col_remarks_adj = col_adjusted + 1
    col_approved = col_remarks_adj + 1
    ncols = col_approved

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

    # ---- Header rows ----
    header_row_top = 4
    header_row_bot = 5

    def single_header(col, top_text):
        ws.merge_cells(start_row=header_row_top, start_column=col, end_row=header_row_bot, end_column=col)
        ws.cell(row=header_row_top, column=col, value=top_text)

    single_header(1, "Object of Expenditures")
    single_header(2, "Account Code")
    single_header(col_prev, f"{prev_year} Actual")
    single_header(col_annual, f"Current Year {current_year}")
    for i in range(supp_col_count):
        single_header(col_supp_start + i, f"{current_year} Supplemental Budget No.{i + 1}")
    single_header(col_total, f"{current_year} Total")
    single_header(col_proposed, "Proposed")
    single_header(col_diff, "Difference")
    single_header(col_docs, "Supporting Documents")
    single_header(col_remarks, "Remarks for Proposal")
    single_header(col_adjusted, "Adjusted Proposal")
    single_header(col_remarks_adj, "Remarks for Adjusted Proposal")
    single_header(col_approved, "Approved")

    for row in (header_row_top, header_row_bot):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = Font(name="Arial", bold=True, size=9)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.fill = HEADER_FILL
            cell.border = BORDER

    numeric_cols = [col_prev, col_annual] + list(range(col_supp_start, col_supp_end + 1)) + \
        [col_total, col_proposed, col_diff, col_adjusted, col_approved]
    text_cols = [col_docs, col_remarks, col_remarks_adj]

    # ---- Body ----
    row_idx = header_row_bot + 1
    grand_totals = {c: 0.0 for c in numeric_cols}

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

        section_totals = {c: 0.0 for c in numeric_cols}
        for line in lines:
            supp_by_num = {s["supplemental_number"]: s["amount"] for s in line.get("current_supplementals", [])}
            approved = line.get("approved_amount")
            adjusted = line.get("adjusted_proposal")
            attachment_names = "; ".join(a["filename"] for a in line.get("attachments", []))

            row_values = {1: line["account_name"], 2: line["account_code"]}
            row_values[col_prev] = line["prev_year_actual"]
            row_values[col_annual] = line["current_annual"]
            for i in range(supp_col_count):
                row_values[col_supp_start + i] = supp_by_num.get(i + 1, 0)
            row_values[col_total] = line["current_total"]
            row_values[col_proposed] = line["proposed_amount"]
            row_values[col_diff] = line["difference"]
            row_values[col_docs] = attachment_names
            row_values[col_remarks] = line.get("remarks") or ""
            row_values[col_adjusted] = adjusted if adjusted is not None else ""
            row_values[col_remarks_adj] = line.get("remarks_adjusted") or ""
            row_values[col_approved] = approved if approved is not None else ""

            for col in range(1, ncols + 1):
                cell = ws.cell(row=row_idx, column=col, value=row_values.get(col, ""))
                cell.font = Font(name="Arial", size=9)
                cell.border = BORDER
                if col in numeric_cols:
                    cell.number_format = CURRENCY_FMT
                    cell.alignment = Alignment(horizontal="right")
                elif col in text_cols:
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

            for col in numeric_cols:
                val = row_values.get(col)
                if isinstance(val, (int, float)):
                    section_totals[col] += val
            row_idx += 1

        subtotal_label = f"Total {CLASSIFICATION_LABELS[classification]}"
        ws.cell(row=row_idx, column=1, value=subtotal_label).font = Font(name="Arial", bold=True, size=9)
        ws.cell(row=row_idx, column=2).border = BORDER
        for col in range(3, ncols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.border = BORDER
            cell.fill = SECTION_FILL
            if col in numeric_cols:
                cell.value = section_totals[col]
                cell.font = Font(name="Arial", bold=True, size=9)
                cell.number_format = CURRENCY_FMT
                cell.alignment = Alignment(horizontal="right")
                grand_totals[col] += section_totals[col]
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
    for col in range(3, ncols + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.border = BORDER
        cell.fill = HEADER_FILL
        if col in numeric_cols:
            cell.value = grand_totals[col]
            cell.font = Font(name="Arial", bold=True, size=10)
            cell.number_format = CURRENCY_FMT
            cell.alignment = Alignment(horizontal="right")

    # ---- Column widths ----
    default_widths = {1: 42, 2: 14, col_prev: 14, col_annual: 16}
    for i in range(supp_col_count):
        default_widths[col_supp_start + i] = 18
    default_widths.update({
        col_total: 16, col_proposed: 14, col_diff: 16, col_docs: 28,
        col_remarks: 26, col_adjusted: 16, col_remarks_adj: 26, col_approved: 14,
    })
    for col in range(1, ncols + 1):
        ws.column_dimensions[get_column_letter(col)].width = default_widths.get(col, 14)
    ws.row_dimensions[header_row_top].height = 30
    ws.row_dimensions[header_row_bot].height = 42

    ws.freeze_panes = ws.cell(row=header_row_bot + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_summary_workbook(report: dict) -> io.BytesIO:
    """
    report: dict shaped like schemas.SummaryReportOut -- one row per account,
    totalled across every office for the given budget cycle.
    """
    year = report["year"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary Report"

    ncols = 9  # Object, Code, PrevActual, CurrAnnual, CurrTotal, Proposed, Adjusted, Approved, # Offices

    title = f"CONSOLIDATED BUDGET SUMMARY — ALL OFFICES — CY {year}"
    if report["budget_type"] == "supplemental":
        title = f"CONSOLIDATED SUPPLEMENTAL BUDGET NO. {report.get('supplemental_number') or 1} SUMMARY — ALL OFFICES — CY {year}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = Font(name="Arial", bold=True, size=13)
    c.alignment = Alignment(horizontal="center")

    subtitle = f"{report['offices_count']} office(s) included"
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font = Font(name="Arial", size=10)
    c.alignment = Alignment(horizontal="center")

    header_row = 4
    headers = [
        "Object of Expenditures", "Account Code", f"{year - 2} Actual (Total)",
        f"Current Year {year - 1} (Total)", f"{year - 1} Total (incl. Supplementals)",
        "Total Proposed (All Offices)", "Total Adjusted (All Offices)",
        "Total Approved (All Offices)", "# Offices with a Proposal",
    ]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=h)
        cell.font = Font(name="Arial", bold=True, size=9)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.fill = HEADER_FILL
        cell.border = BORDER

    row_idx = header_row + 1
    grand = [0.0] * 6
    rows_by_class = {k: [] for k in CLASSIFICATION_ORDER}
    for r in report["rows"]:
        rows_by_class.setdefault(r["classification"], []).append(r)

    for classification in CLASSIFICATION_ORDER:
        rows = rows_by_class.get(classification, [])
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: (r["account_code"], r["account_name"]))

        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=ncols)
        cell = ws.cell(row=row_idx, column=1, value=CLASSIFICATION_LABELS[classification])
        cell.font = Font(name="Arial", bold=True, size=10)
        cell.fill = SECTION_FILL
        cell.border = BORDER
        row_idx += 1

        section_totals = [0.0] * 6
        for r in rows:
            values = [
                r["account_name"], r["account_code"],
                r["total_prev_year_actual"], r["total_current_annual"], r["total_current_total"],
                r["total_proposed"], r["total_adjusted"], r["total_approved"], r["offices_included"],
            ]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.font = Font(name="Arial", size=9)
                cell.border = BORDER
                if 3 <= col <= 8:
                    cell.number_format = CURRENCY_FMT
                    cell.alignment = Alignment(horizontal="right")
                elif col == 9:
                    cell.alignment = Alignment(horizontal="center")
            for i, key in enumerate(["total_prev_year_actual", "total_current_annual", "total_current_total",
                                      "total_proposed", "total_adjusted", "total_approved"]):
                section_totals[i] += r[key]
            row_idx += 1

        ws.cell(row=row_idx, column=1, value=f"Total {CLASSIFICATION_LABELS[classification]}").font = Font(name="Arial", bold=True, size=9)
        ws.cell(row=row_idx, column=2).border = BORDER
        ws.cell(row=row_idx, column=1).border = BORDER
        ws.cell(row=row_idx, column=1).fill = SECTION_FILL
        for i, col in enumerate(range(3, 9)):
            cell = ws.cell(row=row_idx, column=col, value=section_totals[i])
            cell.font = Font(name="Arial", bold=True, size=9)
            cell.number_format = CURRENCY_FMT
            cell.alignment = Alignment(horizontal="right")
            cell.border = BORDER
            cell.fill = SECTION_FILL
            grand[i] += section_totals[i]
        ws.cell(row=row_idx, column=9).border = BORDER
        ws.cell(row=row_idx, column=9).fill = SECTION_FILL
        row_idx += 1

    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=2)
    cell = ws.cell(row=row_idx, column=1, value="GRAND TOTAL")
    cell.font = Font(name="Arial", bold=True, size=10)
    cell.fill = HEADER_FILL
    cell.border = BORDER
    ws.cell(row=row_idx, column=2).border = BORDER
    ws.cell(row=row_idx, column=2).fill = HEADER_FILL
    for i, col in enumerate(range(3, 9)):
        cell = ws.cell(row=row_idx, column=col, value=grand[i])
        cell.font = Font(name="Arial", bold=True, size=10)
        cell.number_format = CURRENCY_FMT
        cell.alignment = Alignment(horizontal="right")
        cell.border = BORDER
        cell.fill = HEADER_FILL
    ws.cell(row=row_idx, column=9).border = BORDER
    ws.cell(row=row_idx, column=9).fill = HEADER_FILL

    widths = [42, 14, 16, 16, 16, 18, 18, 16, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[header_row].height = 36
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
