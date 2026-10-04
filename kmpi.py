"""Key model performance indicators (KMPIs) — rules as plain functions (no Streamlit).

Kept deliberately simple:

    KMPI         an ID (KMPI-001 ...), a short name and a description that states
                 what is measured and the pass/fail criterion, e.g.
                 "Gini of 12-month PDs against observed defaults. Pass: Gini >= 0.55."
    Frequency    set per model (monthly, quarterly, semi-annual, annual); a KMPI
                 can be reported less often than its model (e.g. an annual KMPI
                 on a quarterly model).
    Return       one per model per period. The owner or developer enters each
                 KMPI's value and result (Pass / Fail / Not available) — typed in
                 or uploaded from the Excel template — and submits. Fail or Not
                 available needs a comment. The validator reviews, sends back, or
                 raises a finding.

Status of a return:  Not started -> Draft -> Submitted -> Reviewed
                                        ^          |
                                        +- Returned+
"""

from __future__ import annotations

import io
from datetime import date, timedelta

# ---------------------------------------------------------------- frequencies and periods
FREQUENCY_MONTHS = {"Monthly": 1, "Quarterly": 3, "Semi-annual": 6, "Annual": 12}
FREQUENCIES = list(FREQUENCY_MONTHS)
AS_MODEL = "As model"                      # a KMPI that follows its model's frequency
DEFAULT_FREQUENCY = "Quarterly"
DUE_DAYS = 30                              # a return is due 30 days after period end

PASS, FAIL, NA = "Pass", "Fail", "Not available"
RESULTS = [PASS, FAIL, NA]
RESULT_ICON = {PASS: "✅", FAIL: "❌", NA: "⚪", None: ""}

NOT_STARTED, DRAFT, SUBMITTED, RETURNED, REVIEWED = (
    "Not started", "Draft", "Submitted", "Returned", "Reviewed")
EDITABLE = {NOT_STARTED, DRAFT, RETURNED}       # the first line can still change values
DONE = {SUBMITTED, REVIEWED}                     # counts as reported

ATTESTATION = ("I confirm these results follow the pass/fail criteria in each KMPI's description "
               "and every fail or missing value is explained.")


def period_label(year: int, end_month: int, frequency: str) -> str:
    if frequency == "Monthly":
        return f"{year}-{end_month:02d}"
    if frequency == "Quarterly":
        return f"{year}-Q{end_month // 3}"
    if frequency == "Semi-annual":
        return f"{year}-H{end_month // 6}"
    return str(year)


def _parse(period: str) -> tuple[int, int, str]:
    """'2026-Q3' -> (2026, 9, 'Quarterly'): year, end month, frequency."""
    if len(period) == 4:
        return int(period), 12, "Annual"
    year, part = int(period[:4]), period[5:]
    if part.startswith("Q"):
        return year, 3 * int(part[1]), "Quarterly"
    if part.startswith("H"):
        return year, 6 * int(part[1]), "Semi-annual"
    return year, int(part), "Monthly"


def frequency_of(period: str) -> str:
    return _parse(period)[2]


def period_end(period: str) -> date:
    year, month, _ = _parse(period)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def previous_period(period: str) -> str:
    year, month, freq = _parse(period)
    month -= FREQUENCY_MONTHS[freq]
    if month <= 0:
        year, month = year - 1, month + 12
    return period_label(year, month, freq)


def reporting_period(frequency: str = DEFAULT_FREQUENCY, today: date | None = None) -> str:
    """The period being reported now: the last one that has ended."""
    today = today or date.today()
    step = FREQUENCY_MONTHS[frequency]
    end_month = (today.month - 1) // step * step         # last completed period end month
    year = today.year
    if end_month == 0:
        year, end_month = year - 1, 12
    return period_label(year, end_month, frequency)


def recent_periods(frequency: str, n: int, today: date | None = None) -> list[str]:
    """The last n reporting periods, newest first."""
    out = [reporting_period(frequency, today)]
    for _ in range(n - 1):
        out.append(previous_period(out[-1]))
    return out


def due_date(period: str) -> date:
    return period_end(period) + timedelta(days=DUE_DAYS)


def kmpi_frequency(k: dict, model_frequency: str) -> str:
    """A KMPI's own frequency, never more often than its model's."""
    own = k.get("frequency") or AS_MODEL
    if own == AS_MODEL or FREQUENCY_MONTHS[own] < FREQUENCY_MONTHS[model_frequency]:
        return model_frequency
    return own


def due_kmpis(kmpis: list[dict], period: str) -> list[dict]:
    """Active KMPIs reported in this period (the period carries the model's frequency)."""
    _, month, model_freq = _parse(period)
    return [k for k in kmpis if k.get("active", True)
            and month % FREQUENCY_MONTHS[kmpi_frequency(k, model_freq)] == 0]


def return_status(ret: dict | None) -> str:
    return (ret or {}).get("status") or NOT_STARTED


def is_overdue(ret: dict | None, period: str, today: date | None = None) -> bool:
    return return_status(ret) not in DONE and (today or date.today()) > due_date(period)


def submission_problems(due: list[dict], values: dict) -> list[str]:
    """What stops a return from being submitted (empty list = ready)."""
    problems = []
    for k in due:
        e = values.get(k["kmpi_id"]) or {}
        if e.get("result") not in RESULTS:
            problems.append(f"{k['kmpi_id']}: choose Pass, Fail or Not available")
        elif e["result"] != PASS and not (e.get("comment") or "").strip():
            problems.append(f"{k['kmpi_id']}: say why it is '{e['result']}' and what is being done")
    return problems


def counts(values: dict) -> dict:
    results = [v.get("result") for v in values.values()]
    return {r: results.count(r) for r in RESULTS}


# ---------------------------------------------------------------- template upload
TEMPLATE_COLUMNS = ["KMPI ID", "KMPI", "Description (pass/fail criteria)", "Value", "Result", "Comment"]


def template_rows(due: list[dict], values: dict | None = None) -> list[dict]:
    values = values or {}
    return [{"KMPI ID": k["kmpi_id"], "KMPI": k["name"], "Description (pass/fail criteria)": k["description"],
             "Value": (values.get(k["kmpi_id"]) or {}).get("value") or "",
             "Result": (values.get(k["kmpi_id"]) or {}).get("result") or "",
             "Comment": (values.get(k["kmpi_id"]) or {}).get("comment") or ""} for k in due]


def template_xlsx(due: list[dict], values: dict | None = None) -> bytes:
    import pandas as pd

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(template_rows(due, values), columns=TEMPLATE_COLUMNS).to_excel(xw, index=False, sheet_name="KMPIs")
        ws = xw.sheets["KMPIs"]
        for col, width in zip("ABCDEF", (11, 34, 70, 12, 14, 50)):
            ws.column_dimensions[col].width = width
    return buf.getvalue()


def parse_upload(data: bytes, filename: str) -> dict:
    """Excel or CSV in the template layout -> {kmpi_id: {value, result, comment}}."""
    import pandas as pd

    if filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    elif filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data), dtype=str)
    else:
        raise ValueError("Upload the Excel template (.xlsx) or a CSV with the same columns.")
    df.columns = [str(c).strip() for c in df.columns]
    if "KMPI ID" not in df.columns or "Result" not in df.columns:
        raise ValueError("The file needs the template columns, at least 'KMPI ID' and 'Result'.")
    out = {}
    lookup = {r.lower(): r for r in RESULTS}
    for _, row in df.fillna("").iterrows():
        kid = str(row["KMPI ID"]).strip()
        if not kid:
            continue
        result = str(row.get("Result", "")).strip()
        if result and result.lower() not in lookup:
            raise ValueError(f"{kid}: result must be Pass, Fail or Not available (got '{result}').")
        out[kid] = {"value": str(row.get("Value", "")).strip(), "result": lookup.get(result.lower()),
                    "comment": str(row.get("Comment", "")).strip()}
    if not out:
        raise ValueError("No KMPI rows found in the file.")
    return out
