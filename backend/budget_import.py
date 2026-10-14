"""
Importing a provincial "Programmed Appropriation and Obligation by Object
of Expenditure" (LBP Form No. 2 style) workbook into the budget system.

The workbook this was built against (and tested exhaustively against) has
one worksheet per office, each shaped like:

    Row with "<OFFICE NAME> (<code>, <SECTOR>)"   <- office header
    Row with column headers (Object of Expenditures / Account Code / ...)
    "1.1 Personal Services:" / "1.2 Maintenance and Other Operating
      Expenditures" / "2.0 Capital Outlay" / financial-expenses section
      headers, each followed by its account rows
    "Total ... ►" subtotal rows, "TOTAL APPROPRIATION ►" grand total

Any worksheet that doesn't match this shape (summary tabs, charts, SPA
breakdown sheets, etc.) is skipped automatically -- detection is generic
(no hardcoded sheet names), so this keeps working on next year's workbook
even if sheet names/order change, as long as the overall layout doesn't.

Column layout (0-indexed, as read by openpyxl with values_only=True):
    0 = section header (e.g. "1.1 Personal Services:") or office header
    1 = account/object name (most rows)
    2 = account/object name, used instead of col 1 on a few indented rows;
        also holds the "Total ... ►" label for subtotal/total rows
    3 = account code
    4 = past year actual (e.g. 2025 Actual)
    5,6 = current year first/second semester (not used individually)
    7 = current year total (e.g. 2026 Total)
    8 = budget year proposed amount (e.g. 2027 Proposed) -- the authoritative
        final figure, verified column-by-column against each sheet's own
        "TOTAL APPROPRIATION" grand total (see tests)
"""
import re
from typing import Optional

import openpyxl

HEADER_RE = re.compile(r'^(.*?)\s*\(([^,()]+),\s*([^()]+)\)\s*$')
TOTAL_RE = re.compile(r'^\s*TOTAL\b.*[►>]\s*$', re.IGNORECASE)


def _classify(label: str) -> Optional[str]:
    u = label.upper()
    if "PERSONAL SERVICES" in u:
        return "PS"
    if "MAINTENANCE" in u and "OPERATING" in u:
        return "MOOE"
    if "CAPITAL OUTLAY" in u:
        return "CO"
    if "FINANCIAL EXPENSE" in u:
        return "FE"
    if "SPECIAL PURPOSE" in u:
        # "Special Purpose Appropriations" (e.g. "3.0 SPECIAL PURPOSE
        # APPROPRIATIONS") is its own classification, same as the file --
        # not folded into whichever section happened to come right before
        # it (previously Capital Outlay, since SPA usually follows it).
        return "SPA"
    return None


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def _parse_office_sheet(ws):
    """Returns (office_name, office_code, office_sector, lines, control_total)
    or (None, None, None, [], None) if this sheet doesn't look like an
    office budget sheet at all."""
    office_name = office_code = office_sector = None
    cur_class = None
    lines = []
    control_total = None

    for row in ws.iter_rows(values_only=True):
        a = row[0] if len(row) > 0 else None
        b = row[1] if len(row) > 1 else None
        c = row[2] if len(row) > 2 else None
        d = row[3] if len(row) > 3 else None
        e = row[4] if len(row) > 4 else None
        h = row[7] if len(row) > 7 else None
        i = row[8] if len(row) > 8 else None

        if office_name is None and isinstance(a, str) and a.strip():
            m = HEADER_RE.match(a.strip())
            if m:
                office_name = m.group(1).strip()
                office_code = m.group(2).strip()
                office_sector = m.group(3).strip()
                continue

        if isinstance(a, str) and a.strip():
            cls = _classify(a)
            if cls:
                cur_class = cls
                continue

        name = None
        if not _is_blank(b):
            name = str(b).strip()
        elif not _is_blank(c):
            name = str(c).strip()

        if name is None or _is_blank(d):
            if name and TOTAL_RE.match(name) and "APPROPRIATION" in name.upper():
                control_total = _num(i)
            continue

        if TOTAL_RE.match(name):
            if "APPROPRIATION" in name.upper():
                control_total = _num(i)
            continue

        lines.append({
            "classification": cur_class,
            "code": str(d).strip(),
            "name": name,
            "prev_year_actual": _num(e),
            "current_annual": _num(h),
            "proposed_amount": _num(i),
        })

    return office_name, office_code, office_sector, lines, control_total


def parse_workbook(file_bytes) -> dict:
    """Parses the whole uploaded workbook. Returns a dict with an 'offices'
    list (one entry per detected office sheet) and a 'skipped_sheets' list
    (every other sheet, for transparency -- these are the summary/report
    tabs that aren't per-office budget data)."""
    wb = openpyxl.load_workbook(file_bytes, data_only=True)

    offices = []
    skipped_sheets = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        office_name, office_code, office_sector, lines, control_total = _parse_office_sheet(ws)

        if not office_name or not lines:
            skipped_sheets.append(sheet_name)
            continue

        total_proposed = round(sum(l["proposed_amount"] for l in lines), 2)
        control_match = (
            control_total is not None and abs(total_proposed - control_total) < 1.0
        )
        missing_classification = sum(1 for l in lines if l["classification"] is None)

        offices.append({
            "sheet": sheet_name,
            "office_name_in_file": office_name,
            "office_code": office_code,
            "office_sector": office_sector,
            "line_count": len(lines),
            "total_proposed": total_proposed,
            "control_total": control_total,
            "control_match": control_match,
            "missing_classification_count": missing_classification,
            "lines": lines,
        })

    return {"offices": offices, "skipped_sheets": skipped_sheets}


def normalize_office_name(name: str) -> str:
    """Loose normalization used to auto-suggest a matching existing office:
    uppercase, collapse whitespace, strip a leading 'OFFICE OF THE'/'OFFICE
    OF' so e.g. 'Office of the Provincial Administrator' and 'Provincial
    Administrator's Office' have a better chance of lining up."""
    u = re.sub(r"\s+", " ", name.strip().upper())
    u = re.sub(r"^OFFICE OF (THE )?", "", u)
    u = u.rstrip(".")
    return u


def suggest_office_match(office_name_in_file: str, existing_offices: list) -> Optional[int]:
    """existing_offices: list of (id, name) tuples. Returns the best-guess
    office id, or None if nothing looks close enough to auto-select --
    the caller (admin, in the preview UI) always gets the final say."""
    target = normalize_office_name(office_name_in_file)
    for oid, name in existing_offices:
        if normalize_office_name(name) == target:
            return oid
    # fall back to a loose containment match only when it's unambiguous
    candidates = [
        oid for oid, name in existing_offices
        if target in normalize_office_name(name) or normalize_office_name(name) in target
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None
