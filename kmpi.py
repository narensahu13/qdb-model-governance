"""Key model performance indicators (KMPIs) — rules as data and pure functions.

A KMPI is a measure, defined for one model, that the first line reports every
period to show the model still performs as validated: discrimination,
calibration, stability, data quality, overrides, business outcomes.

    KMPI library     one record per KMPI (ID KMPI-001 ...): what it measures, how
                     it is calculated, the data source, the direction, amber and
                     red thresholds, and how often it is reported.
    KMPI return      one per model per period (2026-Q3 ...). The owner or
                     developer enters the values, explains every amber or red
                     one, and submits with an attestation; the validator reviews
                     it, sends it back, or raises a finding.

Status of a return:  Not started -> Draft -> Submitted -> Reviewed
                                        ^          |
                                        +- Returned+

No Streamlit here, so the rules are unit-tested directly.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# ---------------------------------------------------------------- library
CATEGORIES = [
    "Discrimination",
    "Calibration / back-testing",
    "Stability",
    "Data quality",
    "Overrides and use",
    "Business outcome",
    "Fairness (AI)",
]
HIGHER, LOWER, RANGE = "Higher is better", "Lower is better", "Within range"
DIRECTIONS = [HIGHER, LOWER, RANGE]
FREQUENCIES = ["Quarterly", "Semi-annual", "Annual"]
UNITS = ["ratio", "%", "pp", "count", "days"]

# ---------------------------------------------------------------- returns
NOT_STARTED, DRAFT, SUBMITTED, RETURNED, REVIEWED = (
    "Not started", "Draft", "Submitted", "Returned", "Reviewed")
RETURN_STATUSES = [NOT_STARTED, DRAFT, SUBMITTED, RETURNED, REVIEWED]
EDITABLE = {NOT_STARTED, DRAFT, RETURNED}       # the first line can still change values
DONE = {SUBMITTED, REVIEWED}                     # counts as reported on time
DUE_DAYS = 30                                    # a return is due 30 days after period end

GREEN, AMBER, RED, NOT_REPORTED = "Green", "Amber", "Red", "Not reported"
RAG_ORDER = {RED: 0, AMBER: 1, NOT_REPORTED: 2, GREEN: 3}

ATTESTATION = ("I confirm these values were calculated as defined in the KMPI library, from the "
               "stated data sources, and that every amber or red value is explained.")


# ---------------------------------------------------------------- thresholds and RAG
def rag(value, direction: str, amber, red) -> str:
    """Green / Amber / Red for a value; 'Not reported' when there is no value.

    Higher is better: amber below `amber`, red below `red`.
    Lower is better:  amber above `amber`, red above `red`.
    Within range:     `amber` and `red` are [low, high]; green inside amber,
                      red outside red, amber in between."""
    if value is None:
        return NOT_REPORTED
    v = float(value)
    if direction == HIGHER:
        return RED if v < red else AMBER if v < amber else GREEN
    if direction == LOWER:
        return RED if v > red else AMBER if v > amber else GREEN
    if direction == RANGE:
        if v < red[0] or v > red[1]:
            return RED
        if v < amber[0] or v > amber[1]:
            return AMBER
        return GREEN
    raise ValueError(f"Unknown direction {direction}")


def worst(rags) -> str | None:
    rags = [r for r in rags if r]
    return min(rags, key=lambda r: RAG_ORDER[r]) if rags else None


def _num(x) -> str:
    return f"{x:g}"


def threshold_text(k: dict) -> str:
    unit = k.get("unit") or ""
    u = "" if unit in ("ratio", "count", "") else f" {unit}" if unit != "%" else "%"
    if k["direction"] == HIGHER:
        return f"Amber < {_num(k['amber'])}{u} · Red < {_num(k['red'])}{u}"
    if k["direction"] == LOWER:
        return f"Amber > {_num(k['amber'])}{u} · Red > {_num(k['red'])}{u}"
    a, r = k["amber"], k["red"]
    return f"Green {_num(a[0])}–{_num(a[1])}{u} · Red outside {_num(r[0])}–{_num(r[1])}{u}"


def parse_threshold(text, direction: str):
    """'0.5' -> 0.5; for a range '0.8-1.2' or '0.8 – 1.2' -> [0.8, 1.2]."""
    text = str(text).strip()
    num = r"(-?\d+(?:\.\d+)?)"
    if direction == RANGE:
        match = re.fullmatch(num + r"\s*(?:-|–|to)\s*" + num, text)
        if not match or float(match[1]) >= float(match[2]):
            raise ValueError("For a range, enter low and high, e.g. 0.8-1.2.")
        return [float(match[1]), float(match[2])]
    if not re.fullmatch(num, text):
        raise ValueError(f"Enter one number for the threshold (got '{text}').")
    return float(text)


def check_thresholds(direction: str, amber, red) -> None:
    """Red must be beyond amber, or the RAG never turns amber."""
    if direction == HIGHER and not red < amber:
        raise ValueError("Higher is better: the red threshold must be below the amber threshold.")
    if direction == LOWER and not red > amber:
        raise ValueError("Lower is better: the red threshold must be above the amber threshold.")
    if direction == RANGE and not (red[0] <= amber[0] and amber[1] <= red[1]):
        raise ValueError("Within range: the green range must sit inside the red limits.")


# ---------------------------------------------------------------- periods
def period_of(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def period_end(period: str) -> date:
    year, q = int(period[:4]), int(period[-1])
    month = 3 * q
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def previous_period(period: str) -> str:
    year, q = int(period[:4]), int(period[-1])
    return f"{year - 1}-Q4" if q == 1 else f"{year}-Q{q - 1}"


def reporting_period(today: date | None = None) -> str:
    """The period being reported now: the last quarter that has ended."""
    today = today or date.today()
    return previous_period(period_of(today))


def recent_periods(n: int, today: date | None = None) -> list[str]:
    """The last n reporting periods, oldest first."""
    p = reporting_period(today)
    out = [p]
    for _ in range(n - 1):
        out.append(previous_period(out[-1]))
    return list(reversed(out))


def due_date(period: str) -> date:
    return period_end(period) + timedelta(days=DUE_DAYS)


def is_due(k: dict, period: str) -> bool:
    """Is this KMPI reported in this period (by frequency)?"""
    q = int(period[-1])
    freq = k.get("frequency", "Quarterly")
    return (freq == "Quarterly" or (freq == "Semi-annual" and q in (2, 4))
            or (freq == "Annual" and q == 4))


def due_kmpis(kmpis: list[dict], period: str) -> list[dict]:
    return [k for k in kmpis if k.get("active", True) and is_due(k, period)]


def return_status(ret: dict | None) -> str:
    return (ret or {}).get("status") or NOT_STARTED


def is_overdue(ret: dict | None, period: str, today: date | None = None) -> bool:
    today = today or date.today()
    return return_status(ret) not in DONE and today > due_date(period)


def submission_problems(due: list[dict], values: dict) -> list[str]:
    """What stops a return from being submitted (empty list = ready)."""
    problems = []
    for k in due:
        e = values.get(k["kmpi_id"]) or {}
        comment = (e.get("comment") or "").strip()
        if e.get("value") is None:
            if not comment:
                problems.append(f"{k['kmpi_id']}: enter a value, or say why it is not available")
            continue
        if rag(e["value"], k["direction"], k["amber"], k["red"]) in (AMBER, RED) and not comment:
            problems.append(f"{k['kmpi_id']}: explain the {rag(e['value'], k['direction'], k['amber'], k['red']).lower()} value and the action taken")
    return problems
