"""QDB model governance rules as data and pure functions (no Streamlit).

Decisions recorded 30 September 2026:
  * No Model Validation Unit: one QDB validator or an external consultant
    performs validations; both act in the validator (LOD2) role.
  * No Model Risk Committee: Tier 1 models are approved by the Management
    Risk Committee; the CRO approves Tier 2 and Tier 3 (may delegate Tier 3).
  * Four-level validation rating scale.
  * Benchmarks: Federal Reserve SR 26-2 (April 2026, replaced SR 11-7),
    PRA SS1/23, and the QCB Artificial Intelligence Guideline (September 2024),
    which applies directly because QDB is licensed by QCB.
"""

from __future__ import annotations

from datetime import date, timedelta

# ---------------------------------------------------------------- rating scale
RATING_SCALE = [
    "Fit for Purpose",
    "Fit with Conditions",
    "Restricted Use",
    "Not Fit for Purpose",
]

RATING_DESCRIPTIONS = {
    "Fit for Purpose": "No material weaknesses; the model may be used as intended.",
    "Fit with Conditions": "Usable, provided the listed findings are remediated by their due dates.",
    "Restricted Use": "Usable only within stated limits (segments, overlays or reduced reliance) until weaknesses are fixed.",
    "Not Fit for Purpose": "Must not be relied on; remediation or replacement required.",
}

# Older labels found in historic records.
LEGACY_OUTCOMES = {
    "Approved with Conditions": "Fit with Conditions",
}

OUTCOME_TO_STATUS = {
    "Fit for Purpose": "In Production",
    "Fit with Conditions": "Approved with Conditions",
    "Restricted Use": "Restricted Use",
    "Not Fit for Purpose": "Under Remediation",
}

MODEL_STATUSES = [
    "In Development",
    "In Validation",
    "In Production",
    "Approved with Conditions",
    "Restricted Use",
    "Under Remediation",
    "In Production - Approval Pending",
    "Retired",
]

PRE_IMPLEMENTATION_STATUSES = {"In Development", "In Validation"}

# ---------------------------------------------------------------- tier-driven rules
FREQUENCY_BY_TIER = {
    1: ("Annual", 365),
    2: ("Biennial", 730),
    3: ("Triennial", 1095),
}

APPROVAL_BODY_BY_TIER = {
    1: "Management Risk Committee",
    2: "CRO",
    3: "CRO (may delegate)",
}

DUE_SOON_DAYS = 90


def normalise_outcome(outcome: str | None) -> str | None:
    if not outcome:
        return outcome
    return LEGACY_OUTCOMES.get(outcome, outcome)


def validation_frequency(tier: int) -> str:
    return FREQUENCY_BY_TIER[tier][0]


def approval_body(tier: int) -> str:
    return APPROVAL_BODY_BY_TIER[tier]


def counts_as_validation(req: dict) -> bool:
    """A closed Validation, or a closed Material Model Change, with a rating."""
    if req.get("status") != "Closed":
        return False
    if normalise_outcome(req.get("outcome")) not in RATING_SCALE:
        return False
    if req.get("type") == "VAL":
        return True
    return req.get("type") == "MC" and req.get("materiality") == "Material"


def derive_validation_dates(tier: int, requests: list[dict]) -> dict:
    """Last validation, its rating and the next due date — derived from the
    request history, never typed onto the model record."""
    done = [r for r in requests if counts_as_validation(r)]
    if not done:
        return {"last_validation": None, "last_rating": None, "next_validation_due": None}
    latest = max(done, key=lambda r: (r.get("closed_date") or r.get("created_date") or ""))
    last = latest.get("closed_date") or latest.get("created_date")
    days = FREQUENCY_BY_TIER[tier][1]
    return {
        "last_validation": last,
        "last_rating": normalise_outcome(latest.get("outcome")),
        "next_validation_due": (date.fromisoformat(last) + timedelta(days=days)).isoformat(),
    }


def validation_status(model: dict, today: date | None = None) -> str:
    """On Track / Due Soon / Overdue / Never Validated / Pre-implementation."""
    today = today or date.today()
    if model.get("last_validation") is None:
        if model.get("status") in PRE_IMPLEMENTATION_STATUSES:
            return "Pre-implementation"
        return "Never Validated"
    due = model.get("next_validation_due")
    if due is None:
        return "On Track"
    due_date = date.fromisoformat(due)
    if due_date < today:
        return "Overdue"
    if due_date <= today + timedelta(days=DUE_SOON_DAYS):
        return "Due Soon"
    return "On Track"


# ---------------------------------------------------------------- independence
def person_name(label: str | None) -> str:
    """'Hassan Al-Mohannadi (Validator)' -> 'Hassan Al-Mohannadi'."""
    return (label or "").split(" (")[0].strip()


def independence_conflict(model: dict, assignee: str, request_type: str) -> str | None:
    """A validator must not have developed or own the model they validate.

    Returns a human-readable reason when the assignment breaks independence,
    otherwise None. Findings (FND) are assigned to owners by design.
    """
    if request_type not in ("VAL", "MC"):
        return None
    who = person_name(assignee)
    if not who:
        return None
    for role_field, role_label in (("owner", "owner"), ("developer", "developer")):
        if who and who == person_name(model.get(role_field)):
            return (
                f"{who} is the {role_label} of {model['model_id']} and cannot "
                "validate it (independence rule)."
            )
    return None
