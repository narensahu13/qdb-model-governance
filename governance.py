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
    "Awaiting Approval",
    "Approved — Awaiting Implementation",
    "In Production",
    "Approved with Conditions",
    "Restricted Use",
    "Under Remediation",
    "In Production - Approval Pending",
    "Retired",
]

PRE_IMPLEMENTATION_STATUSES = {
    "In Development", "In Validation", "Awaiting Approval", "Approved — Awaiting Implementation",
}

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
    """'Validator 1 (Validator)' -> 'Validator 1'."""
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


# ================================================================ Phase 1
# ---------------------------------------------------------------- identification
IDENTIFICATION_QUESTIONS = [
    ("quantitative",
     "Does it produce quantitative outputs — scores, grades, probabilities, values, "
     "forecasts or weights?"),
    ("theory",
     "Does it apply statistical, economic, financial or mathematical methods or "
     "assumptions (including calibrated parameters or expert-set weights)?"),
    ("deterministic_only",
     "Is it only arithmetic or fixed deterministic rules, with no estimation or calibration?"),
    ("learns_from_data",
     "Does it learn from data (machine learning / AI) or generate content (generative AI)?"),
    ("decision_use",
     "Are its outputs used for credit, pricing, provisioning, capital, liquidity, "
     "compliance or other business decisions or reporting?"),
]

CLASS_MODEL = "Model"
CLASS_EUC = "EUC tool"
CLASS_AI_TOOL = "AI tool (non-model)"
CLASS_NOT_MODEL = "Not a model"
TOOL_CLASSES = [CLASS_EUC, CLASS_AI_TOOL, CLASS_NOT_MODEL]


def identify(answers: dict) -> dict:
    """Classify a candidate from the identification questionnaire.

    Follows the SR 26-2 definition (a complex quantitative method applying
    statistical, economic or financial theory; simple arithmetic and
    deterministic rules excluded) and the QCB AI Guideline (every AI system is
    registered, model or not)."""
    q = {k: bool(answers.get(k)) for k, _ in IDENTIFICATION_QUESTIONS}
    ai = q["learns_from_data"]
    if q["quantitative"] and (ai or (q["theory"] and not q["deterministic_only"])):
        cls = CLASS_MODEL
        why = ("Produces quantitative estimates using "
               + ("a method that learns from data" if ai else "statistical, economic or financial methods")
               + " — in scope of the model inventory.")
    elif ai:
        cls = CLASS_AI_TOOL
        why = ("Uses AI but does not produce quantitative estimates — recorded in the AI "
               "register (QCB AI Guideline), not in the model inventory.")
    elif q["decision_use"] and (q["quantitative"] or q["deterministic_only"]):
        cls = CLASS_EUC
        why = ("Calculation or rules without estimation, used for decisions or reporting — "
               "recorded in the end-user computing (EUC) register with basic controls.")
    else:
        cls = CLASS_NOT_MODEL
        why = "Neither a model nor a decision-relevant calculation tool — recorded for traceability only."
    return {"classification": cls, "ai_system": ai, "reason": why}


# ---------------------------------------------------------------- tier sign-off (gate G1)
TIER_CONFIRMED = "Confirmed"
TIER_PROPOSED = "Proposed"
TIER_OVERRIDE_PENDING = "Override pending CRO"


def effective_tier(model: dict) -> int:
    """The tier in force: an approved override, else the rule-based tier."""
    from tiering import compute_tier
    if model.get("tier_override"):
        return int(model["tier_override"])
    return compute_tier(**model["tier_scores"])["tier"]


def tier_confirmed(model: dict) -> bool:
    return (model.get("tier_assessment") or {}).get("status", TIER_CONFIRMED) == TIER_CONFIRMED


# ---------------------------------------------------------------- QCB AI register
AI_FUNCTIONAL_CATEGORIES = [
    "Credit assessment and decisioning",
    "Document processing",
    "Customer interaction",
    "Financial crime / AML",
    "Forecasting and analytics",
    "Other",
]
AI_PROVIDER_ROLES = ["Provider (built by QDB)", "User / deployer (third-party system)"]
AI_AUTONOMY = ["Human-in-the-loop", "Human-on-the-loop", "Fully autonomous"]
QCB_APPROVAL_STATUSES = ["Not required", "Required — not yet sought", "Submitted to QCB", "Approved by QCB"]


def qcb_approval_required(rec: dict) -> bool:
    """QCB prior approval: high-risk AI, or any fully autonomous AI system."""
    if not rec.get("ai_system"):
        return False
    return bool(rec.get("qcb_ai_high_risk")) or rec.get("ai_autonomy") == "Fully autonomous"


# ---------------------------------------------------------------- record editing
MODEL_ID_PREFIX = {
    "IFRS 9 / Provisioning": "IF",
    "Credit Rating & Scoring": "CR",
    "Pricing": "PR",
    "Market & Liquidity Risk": "ML",
    "Operational & Non-Financial Risk": "OR",
}
RISK_TYPES = list(MODEL_ID_PREFIX)
SOURCES = ["In-house", "Vendor", "Hybrid (vendor, QDB-calibrated)"]
USE_STATUSES = ["Active", "Planned", "Retired"]

# Fields an owner/developer may edit (MRM Administrator may edit these too).
DESCRIPTIVE_FIELDS = [
    "name", "description", "category", "business_line", "methodology", "source", "vendor",
    "data_sources", "implementation_platform", "usage_frequency", "model_users",
    "key_assumptions", "known_limitations", "exposure_covered_qar_mn", "regulatory_mapping",
    "uses", "upstream", "ai_system", "qcb_ai_high_risk", "ai_functional_category",
    "ai_provider_role", "ai_autonomy", "qcb_approval_status",
]
# Accountability fields: MRM Administrator only.
ASSIGNMENT_FIELDS = ["owner", "developer", "validator", "sponsor", "risk_type"]


def is_owner_or_developer(model: dict, user_name: str) -> bool:
    return user_name in (person_name(model.get("owner")), person_name(model.get("developer")))



# ================================================================ Phase 2 — validation workflow
STATUS_AWAITING_APPROVAL = "Awaiting Approval"
STATUS_AWAITING_IMPLEMENTATION = "Approved — Awaiting Implementation"
# A validation closed while the model is in one of these statuses must go to
# approval (G4) and implementation verification (G5) before the version is used.
APPROVAL_ROUTE_STATUSES = {"In Validation", "In Production - Approval Pending"}
IN_USE_STATUSES = {
    "In Production", "Approved with Conditions", "Restricted Use", "Under Remediation",
    "In Production - Approval Pending",
}

GATES = [
    ("G1", "Tier confirmed"),
    ("G2", "Ready for validation"),
    ("G3", "Validation signed off"),
    ("G4", "Approved"),
    ("G5", "Implementation verified"),
]

# Documents that must be uploaded or on record before a model can be submitted (G2).
G2_REQUIRED_DOCS = {
    1: ["Model Development Document", "Methodology Document", "Data Quality Assessment"],
    2: ["Model Development Document", "Methodology Document", "Data Quality Assessment"],
    3: ["Model Development Document", "Methodology Document"],
}

ENGAGEMENT_STAGES = ["Scoping", "Fieldwork", "Draft report", "Owner review", "Final sign-off", "Signed off"]
OWNER_REVIEW_DAYS = 7          # owner's factual-accuracy review window (calendar days)
IR_STATUSES = ["Open", "Answered", "Accepted"]
APPROVAL_DECISIONS = ["Approved", "Approved with conditions", "Rejected"]
CONDITION_OPEN = "Open"
CONDITION_MET = "Met — awaiting verification"
CONDITION_VERIFIED = "Verified"


def current_gate(model: dict) -> str | None:
    """The gate the model is waiting at, or None when it is in use (all passed)."""
    status = model.get("status")
    if status == "In Development":
        return "G1" if not tier_confirmed(model) else "G2"
    if status in APPROVAL_ROUTE_STATUSES:
        return "G3"
    if status == STATUS_AWAITING_APPROVAL:
        return "G4"
    if status == STATUS_AWAITING_IMPLEMENTATION:
        return "G5"
    return None


def gate_states(model: dict) -> list[dict]:
    """[{gate, name, state}] with state 'done', 'current' or 'pending'."""
    cur = current_gate(model)
    order = [g for g, _ in GATES]
    out = []
    for g, name in GATES:
        if model.get("status") == "Retired":
            state = "done"
        elif cur is None:
            state = "done"
        elif order.index(g) < order.index(cur):
            state = "done"
        elif g == cur:
            state = "current"
        else:
            state = "pending"
        if g == "G1" and not tier_confirmed(model):
            state = "current"  # first sign-off, or a reassessment awaiting confirmation
        out.append({"gate": g, "name": name, "state": state})
    return out


def engagement_can_issue_draft(eng: dict) -> str | None:
    """Reason the draft cannot be issued yet, or None."""
    if not eng.get("independence"):
        return "The validator must declare independence first."
    open_irs = [ir["ir_id"] for ir in eng.get("info_requests", []) if ir["status"] != "Accepted"]
    if open_irs:
        return f"Information requests not yet accepted: {', '.join(open_irs)}."
    return None


def engagement_can_sign_off(eng: dict, today: date | None = None) -> str | None:
    """Reason the validation cannot be signed off yet, or None."""
    today = today or date.today()
    if eng.get("stage") == "Final sign-off":
        return None
    if eng.get("stage") == "Owner review" and eng.get("draft"):
        issued = date.fromisoformat(eng["draft"]["issued_on"])
        if today >= issued + timedelta(days=OWNER_REVIEW_DAYS):
            return None
        return (f"Waiting for the owner's factual-accuracy review (until "
                f"{(issued + timedelta(days=OWNER_REVIEW_DAYS)).isoformat()}).")
    return "Issue the draft report first."
