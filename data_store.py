"""Write side of the platform: every change goes through here.

Each public function runs in ONE database transaction that changes the record
and appends an audit event holding the record's before and after state, so the
change and its audit trail can never diverge. Governance rules that must hold
regardless of the page that calls them are enforced here as well:

  * permissions (via auth.require);
  * independence — the owner or developer of a model cannot be assigned its
    validation or model-change review;
  * closed requests are read-only;
  * evidence files are stored with a SHA-256 hash that is re-checked on read.
"""

from __future__ import annotations

import copy
import re
from datetime import date, datetime, timedelta

import streamlit as st

import auth
import config
import governance
import kmpi as kmpi_rules
import repository

REQUEST_STATUSES = ["Open", "In Progress", "Closed"]
VAL_SUBTYPES = ["Initial", "Periodic", "Targeted", "Ad-hoc"]
MATERIALITY_OPTIONS = ["Material", "Non-material"]
VALIDATION_OUTCOMES = governance.RATING_SCALE

EVIDENCE_CATEGORIES = ["Document", "Code", "Email", "Screenshot", "Data extract", "Other"]
EVIDENCE_LINK_TYPES = ("validation_request", "request_response", "change", "audit", "model")
ALLOWED_UPLOAD_TYPES = ["pdf", "docx", "xlsx", "pptx", "py", "r", "sql", "txt", "csv",
                        "msg", "eml", "png", "jpg", "zip"]
OTHER_DOC_TYPE = "Other supporting document"

COMMON_TESTS = [
    "Discriminatory power (Gini/KS)",
    "Calibration accuracy / backtest",
    "Population stability (PSI)",
    "Sensitivity analysis",
    "Benchmarking",
    "Data quality review",
    "Implementation testing",
    "Override analysis",
    "Scenario testing",
    "Bias and explainability testing",
    "Documentation review",
]


# ---------------------------------------------------------------- primitives
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _refresh() -> None:
    st.cache_data.clear()


def log_event(conn, action: str, entity_type: str, entity_id: str, model_id: str,
              details: str, before=None, after=None) -> None:
    """Append an audit event inside the caller's transaction."""
    user = auth.get_current_user()
    repository.append_audit(conn, {
        "timestamp": _now(),
        "user": user["name"],
        "role": user["role"],
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "model_id": model_id,
        "details": details,
        "before": before,
        "after": after,
    })


def _next_id(existing: list[str], prefix: str) -> str:
    nums = []
    for raw in existing:
        try:
            nums.append(int(str(raw).split("-")[-1]))
        except ValueError:
            continue
    return f"{prefix}-{max(nums or [0]) + 1:03d}"


def _model_or_fail(conn, model_id: str) -> dict:
    m = repository.get_model(model_id, conn)
    if m is None:
        raise ValueError(f"Unknown model {model_id}")
    return m


def _request_or_fail(conn, request_id: str) -> dict:
    r = repository.get_request(request_id, conn)
    if r is None:
        raise ValueError(f"Unknown request {request_id}")
    return r


def _check_independence(model: dict, assignee: str, rtype: str) -> None:
    reason = governance.independence_conflict(model, assignee, rtype)
    if reason:
        raise PermissionError(reason)


def is_request_open(req: dict) -> bool:
    return req.get("status") in ("Open", "In Progress")


def get_request(request_id: str) -> dict | None:
    return repository.get_request(request_id)


def peek_next_thread_id(request_id: str) -> str:
    """Stable id for the next thread entry (FND-001-R1, …)."""
    r = repository.get_request(request_id)
    n = len((r or {}).get("thread") or []) + 1
    return f"{request_id}-R{n}"


def _apply_validation_result(conn, model_id: str, outcome: str) -> None:
    """A rated validation updates the model's status (the dates are derived)."""
    m = _model_or_fail(conn, model_id)
    before = copy.deepcopy(m)
    if m["status"] in governance.APPROVAL_ROUTE_STATUSES:
        # Initial validation or revalidation of a change: approval (G4) comes next.
        if outcome == "Not Fit for Purpose":
            m["status"] = "Under Remediation" if m.get("approvals") else "In Development"
        else:
            m["status"] = governance.STATUS_AWAITING_APPROVAL
        m["pending_revalidation"] = False
        repository.put_model(conn, m)
        log_event(conn, "update_model_status", "model", model_id, model_id,
                  f"Validation signed off ({outcome}) — status {m['status']}",
                  before=before, after=m)
        return
    new_status = governance.OUTCOME_TO_STATUS.get(outcome)
    changed = False
    if new_status and m["status"] not in governance.PRE_IMPLEMENTATION_STATUSES | {"Retired"}:
        if m["status"] != new_status:
            m["status"] = new_status
            changed = True
    if m.get("pending_revalidation"):
        m["pending_revalidation"] = False
        changed = True
    if changed:
        repository.put_model(conn, m)
        log_event(conn, "update_model_status", "model", model_id, model_id,
                  f"Status set to {m['status']} after validation rated {outcome}",
                  before=before, after=m)


# ---------------------------------------------------------------- validation requests
def create_request(model_id: str, record: dict) -> str:
    """Create a typed request (MC / VAL / FND). Returns its id, e.g. VAL-016."""
    rtype = record["type"]
    if rtype not in auth.REQUEST_TYPES:
        raise ValueError(f"Unknown request type: {rtype}")
    auth.require(auth.INITIATE_ACTION[rtype])
    user = auth.get_current_user()

    with repository.tx() as conn:
        model = _model_or_fail(conn, model_id)
        if rtype == "VAL" and model["status"] == "In Development" and record.get("status") != "Closed":
            raise ValueError("A model in development goes to validation through gate G2 — "
                             "submit it from the Governance & Lifecycle tab.")
        assigned = record.get("assigned_to") or ""
        _check_independence(model, assigned, rtype)

        request_id = _next_id(repository.request_ids(conn, rtype), rtype)
        status = record.get("status") or "Open"
        outcome = governance.normalise_outcome(record.get("outcome"))
        if status == "Closed" and rtype in ("VAL", "MC") and outcome not in governance.RATING_SCALE:
            raise ValueError("A closed validation needs a rating from the rating scale.")
        closed_date = record.get("closed_date")
        if status == "Closed" and not closed_date:
            closed_date = date.today().isoformat()

        thread = []
        for i, entry in enumerate(record.get("thread") or [], start=1):
            thread.append({**entry, "response_id": f"{request_id}-R{i}"})

        req = {
            "request_id": request_id,
            "type": rtype,
            "model_id": model_id,
            "status": status,
            "initiated_by": user["name"],
            "initiated_by_role": user["role"],
            "assigned_to": assigned,
            "title": record["title"],
            "description": record.get("description") or "",
            "created_date": record.get("created_date") or date.today().isoformat(),
            "closed_date": closed_date,
            "due_date": record.get("due_date"),
            "outcome": outcome,
            "severity": record.get("severity"),
            "remediation": record.get("remediation"),
            "source": record.get("source"),
            "materiality": record.get("materiality"),
            "validation_subtype": record.get("validation_subtype"),
            "tests": record.get("tests") or [],
            "thread": thread,
        }
        if status != "Closed" and _needs_engagement(req):
            req["engagement"] = new_engagement()
        repository.put_request(conn, req)
        log_event(conn, f"initiate_{rtype.lower()}", "validation_request", request_id,
                  model_id, f"{rtype} opened: {record['title'][:80]}", after=req)

        if status == "Closed" and governance.counts_as_validation(req):
            _apply_validation_result(conn, model_id, outcome)
    _refresh()
    return request_id


def assign_request(request_id: str, assigned_to: str, set_in_progress: bool = True) -> None:
    """Assign a request (send to validator / owner). Open -> In Progress by default."""
    auth.require("assign_request")
    with repository.tx() as conn:
        r = _request_or_fail(conn, request_id)
        if r["status"] == "Closed":
            raise ValueError("Cannot assign a closed request")
        _check_independence(_model_or_fail(conn, r["model_id"]), assigned_to, r["type"])
        before = copy.deepcopy(r)
        r["assigned_to"] = assigned_to
        if set_in_progress and r["status"] == "Open":
            r["status"] = "In Progress"
        repository.put_request(conn, r)
        log_event(conn, "assign_request", "validation_request", request_id, r["model_id"],
                  f"Assigned to {assigned_to}", before=before, after=r)
    _refresh()


def add_request_response(request_id: str, text: str,
                         evidence_ids: list[str] | None = None) -> str:
    """Append a thread message (owners, validators and auditors). Returns its id."""
    auth.require("respond_request")
    user = auth.get_current_user()
    with repository.tx() as conn:
        r = _request_or_fail(conn, request_id)
        if r["status"] == "Closed":
            raise ValueError("Cannot comment on a closed request")
        before = copy.deepcopy(r)
        response_id = f"{request_id}-R{len(r.get('thread') or []) + 1}"
        r.setdefault("thread", []).append({
            "response_id": response_id,
            "date": date.today().isoformat(),
            "author": user["name"],
            "role": user["role"],
            "text": text,
            "evidence_ids": evidence_ids or [],
        })
        if r["status"] == "Open":
            r["status"] = "In Progress"
        repository.put_request(conn, r)
        log_event(conn, "respond_request", "validation_request", request_id, r["model_id"],
                  f"Response added: {text[:80]}", before=before, after=r)
    _refresh()
    return response_id


def close_request(request_id: str, comment: str, outcome: str | None = None,
                  evidence_ids: list[str] | None = None,
                  tests: list[str] | None = None, _signed_off: bool = False) -> str:
    """Close a request with a closure comment (stored on the thread).

    Validations and material model changes are closed only by signing off their
    engagement (gate G3) — see sign_off()."""
    user = auth.get_current_user()
    with repository.tx() as conn:
        r = _request_or_fail(conn, request_id)
        if _needs_engagement(r) and not _signed_off:
            raise ValueError("Validations are closed by signing off the engagement (gate G3).")
        if not auth.can_close_request(r):
            raise PermissionError(
                "You cannot close this request: findings are closed by the line that "
                "raised them; validations and model changes by a validator."
            )
        if r["status"] == "Closed":
            raise ValueError("Request already closed")
        outcome = governance.normalise_outcome(outcome)
        if _needs_engagement(r) and outcome not in governance.RATING_SCALE:
            raise ValueError("Choose a rating from the validation rating scale.")
        if r["type"] == "MC" and not _needs_engagement(r):
            outcome = outcome or "Noted"
        before = copy.deepcopy(r)
        response_id = f"{request_id}-R{len(r.get('thread') or []) + 1}"
        r["status"] = "Closed"
        r["closed_date"] = date.today().isoformat()
        r["outcome"] = outcome or "Closed"
        if tests:
            r["tests"] = tests
        r.setdefault("thread", []).append({
            "response_id": response_id,
            "date": date.today().isoformat(),
            "author": user["name"],
            "role": user["role"],
            "text": f"[Closure] {comment}",
            "evidence_ids": evidence_ids or [],
        })
        repository.put_request(conn, r)
        log_event(conn, "close_request", "validation_request", request_id, r["model_id"],
                  f"Closed ({r['outcome']}): {comment[:80]}", before=before, after=r)
        if governance.counts_as_validation(r):
            _apply_validation_result(conn, r["model_id"], r["outcome"])
    _refresh()
    return response_id


def _needs_engagement(req: dict) -> bool:
    return req.get("type") == "VAL" or (
        req.get("type") == "MC" and req.get("materiality") == "Material")


def new_engagement() -> dict:
    return {"stage": "Scoping", "scope": None, "planned_tests": [], "independence": None,
            "info_requests": [], "draft": None, "owner_review": None, "signed_off": None}


# ---------------------------------------------------------------- model changes
def _default_validator(model: dict) -> str:
    """The model's validator if they are a validator user, else the first validator."""
    validators = auth.users_for_roles("LOD2")
    name = governance.person_name(model.get("validator"))
    for u in validators:
        if u["name"] == name:
            return auth.user_option_label(u)
    for u in validators:
        if not governance.independence_conflict(model, u["name"], "MC"):
            return auth.user_option_label(u)
    return ""


def add_change_entry(model_id: str, entry: dict) -> str:
    """Record a model change and open the matching MC request.

    Material changes put the model In Validation pending revalidation.
    `entry`: date, version, description, author, classification, justification.
    Returns the new change id (e.g. CHG-031).
    """
    auth.require("record_change")
    material = entry.get("classification") == "Material"
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        before = copy.deepcopy(m)
        existing = [c.get("change_id", "") for mm in repository.list_models_conn(conn)
                    for c in mm.get("change_log", [])]
        change_id = _next_id(existing, "CHG")
        entry = {**entry, "change_id": change_id}
        m["change_log"].append(entry)
        m["version"] = entry["version"]
        if material and m["status"] not in governance.PRE_IMPLEMENTATION_STATUSES:
            m["status"] = "In Validation"
            m["pending_revalidation"] = True
        repository.put_model(conn, m)
        log_event(conn, "record_change", "change", change_id, model_id,
                  f"{entry.get('classification', 'Unclassified')} change to v{entry['version']}: "
                  f"{entry['description'][:80]}"
                  + (" — status set to In Validation pending revalidation"
                     if m.get("pending_revalidation") and material else ""),
                  before=before, after=m)

        assignee = _default_validator(m)
        request_id = _next_id(repository.request_ids(conn, "MC"), "MC")
        req = {
            "request_id": request_id, "type": "MC", "model_id": model_id,
            "status": "In Progress" if material else "Open",
            "initiated_by": user["name"], "initiated_by_role": user["role"],
            "assigned_to": assignee,
            "title": f"{'Material' if material else 'Non-material'} change v{entry['version']}",
            "description": f"{entry.get('description', '')}\n\nJustification: {entry.get('justification', '')}",
            "created_date": date.today().isoformat(), "closed_date": None, "due_date": None,
            "outcome": None, "severity": None, "remediation": None, "source": "Model Change",
            "materiality": "Material" if material else "Non-material",
            "validation_subtype": None, "tests": [], "change_id": change_id, "thread": [],
            "engagement": new_engagement() if material else None,
        }
        repository.put_request(conn, req)
        log_event(conn, "initiate_mc", "validation_request", request_id, model_id,
                  f"MC opened for {change_id}", after=req)
    _refresh()
    return change_id


# ---------------------------------------------------------------- audit reviews
def add_audit_review(model_id: str, review: dict) -> str:
    """`review`: date, auditor, rating, scope. Returns the new audit id."""
    auth.require("record_audit")
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        before = copy.deepcopy(m)
        existing = [a.get("audit_id", "") for mm in repository.list_models_conn(conn)
                    for a in mm.get("audit_reviews", [])]
        audit_id = _next_id(existing, "AUD")
        m["audit_reviews"].append({**review, "audit_id": audit_id})
        repository.put_model(conn, m)
        log_event(conn, "record_audit", "audit_review", audit_id, model_id,
                  f"Internal audit review recorded — rating: {review['rating']}",
                  before=before, after=m)
    _refresh()
    return audit_id


# ---------------------------------------------------------------- evidence
_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_filename(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1].strip() or "file"
    return _SAFE.sub("_", base)[:120]


def register_evidence(model_id: str, linked_type: str, linked_id: str, filename: str,
                      file_bytes: bytes, category: str, description: str,
                      doc_type: str | None = None) -> str:
    """Save a file in the evidence folder (<folder>/<model_id>/) and register it
    with its SHA-256 hash. Returns the new evidence id."""
    auth.require("upload_evidence")
    if linked_type not in EVIDENCE_LINK_TYPES:
        raise ValueError(f"Unknown evidence linked_type: {linked_type}")
    user = auth.get_current_user()
    safe = _safe_filename(filename)
    with repository.tx() as conn:
        _model_or_fail(conn, model_id)
        if linked_type == "validation_request":
            req = _request_or_fail(conn, linked_id)
            if req["status"] == "Closed":
                raise ValueError("Cannot attach evidence to a closed request")
        if linked_type == "request_response":
            parent = linked_id.rsplit("-R", 1)[0]
            req = repository.get_request(parent, conn)
            if req and req["status"] == "Closed":
                raise ValueError("Cannot attach evidence to a closed request")

        folder = config.evidence_dir() / model_id
        folder.mkdir(parents=True, exist_ok=True)
        stamped = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe}"
        (folder / stamped).write_bytes(file_bytes)

        evidence_id = _next_id(repository.evidence_ids(conn), "EV")
        ev = {
            "evidence_id": evidence_id,
            "model_id": model_id,
            "linked_type": linked_type,
            "linked_id": linked_id,
            "filename": safe,
            "stored_path": f"{model_id}/{stamped}",
            "sha256": repository.sha256_bytes(file_bytes),
            "size_bytes": len(file_bytes),
            "category": category,
            "description": description,
            "uploaded_by": user["name"],
            "role": user["role"],
            "uploaded_at": _now(),
        }
        if doc_type:
            ev["doc_type"] = doc_type
        repository.put_evidence(conn, ev)
        log_event(conn, "upload_evidence", "evidence", evidence_id, model_id,
                  f"Evidence uploaded ({category}): {safe} — {description[:60]}", after=ev)
    _refresh()
    return evidence_id


def attach_evidence(model_id: str, linked_type: str, linked_id: str, file, category: str,
                    description: str, doc_type: str | None = None) -> str:
    """Attach an uploaded file (Streamlit UploadedFile or anything with .name
    and .getvalue()) to a record. Returns the new evidence id."""
    return register_evidence(model_id, linked_type, linked_id, file.name, file.getvalue(),
                             category, description, doc_type)


def read_evidence(ev: dict) -> tuple[bytes | None, str]:
    """Return (bytes, state) where state is 'ok', 'missing' or 'altered'.

    'altered' means the file on disk no longer matches the hash recorded at
    upload — it was changed or replaced outside the platform."""
    path = config.evidence_dir() / ev["stored_path"]
    if not path.exists():
        return None, "missing"
    data = path.read_bytes()
    if ev.get("sha256") and repository.sha256_bytes(data) != ev["sha256"]:
        return data, "altered"
    return data, "ok"


def evidence_for(linked_type: str, linked_id: str, evidence: list[dict]) -> list[dict]:
    """Evidence rows linked to a specific record."""
    return [e for e in evidence
            if e.get("linked_type") == linked_type and e.get("linked_id") == linked_id]


# ================================================================ Phase 1 — inventory
FULL_DOCS = [
    "Model Development Document",
    "Methodology Document",
    "Data Quality Assessment",
    "User Guide / Operating Manual",
    "Validation Report",
    "Ongoing Monitoring Plan",
]
CORE_DOCS = [
    "Model Development Document",
    "Methodology Document",
    "Validation Report",
    "Ongoing Monitoring Plan",
]


def _checklist_for(tier: int, existing: dict | None = None) -> dict:
    """Documentation checklist for a tier, keeping items already recorded."""
    existing = dict(existing or {})
    for d in (FULL_DOCS if tier in (1, 2) else CORE_DOCS):
        existing.setdefault(d, False)
    return existing


def _sync_downstream(conn, model_id: str, old_up: list[str], new_up: list[str]) -> None:
    """Keep the mirrored downstream lists of other models consistent."""
    for mid in set(old_up) - set(new_up):
        other = repository.get_model(mid, conn)
        if other and model_id in other["dependencies"]["downstream"]:
            other["dependencies"]["downstream"].remove(model_id)
            repository.put_model(conn, other)
    for mid in set(new_up) - set(old_up):
        other = repository.get_model(mid, conn)
        if other is None:
            raise ValueError(f"Unknown upstream model {mid}")
        if model_id not in other["dependencies"]["downstream"]:
            other["dependencies"]["downstream"].append(model_id)
            repository.put_model(conn, other)


def _clean_list(values) -> list[str]:
    if isinstance(values, str):
        values = values.splitlines()
    return [str(v).strip() for v in (values or []) if str(v).strip()]


MODEL_ID_PATTERN = re.compile(r"^QDB-\d{3,}$")


def next_model_id(conn) -> str:
    """Next numeric model id: QDB-001, QDB-002, ..."""
    nums = [int(i.split("-")[1]) for i in repository.model_ids(conn) if MODEL_ID_PATTERN.match(i)]
    return f"QDB-{max(nums or [0]) + 1:03d}"


def register_model(record: dict, answers: dict) -> str:
    """Register a new model after the identification questionnaire.

    The proposed tier is recorded as *Proposed* until the MRM function confirms
    it (gate G1). Returns the new model id, e.g. QDB-018."""
    from tiering import compute_tier

    auth.require("register_model")
    result = governance.identify(answers)
    if result["classification"] != governance.CLASS_MODEL:
        raise ValueError(f"Not a model: {result['reason']} Register it as a tool instead.")
    for f in ("name", "risk_type", "description", "owner", "methodology"):
        if not str(record.get(f) or "").strip():
            raise ValueError(f"'{f}' is required.")
    if record["risk_type"] not in governance.MODEL_ID_PREFIX:
        raise ValueError(f"Unknown risk type {record['risk_type']}")
    scores = record["tier_scores"]
    tier = compute_tier(**scores)["tier"]
    user = auth.get_current_user()
    today = date.today().isoformat()
    upstream = _clean_list(record.get("upstream"))

    with repository.tx() as conn:
        model_id = next_model_id(conn)
        if upstream and model_id in upstream:
            raise ValueError("A model cannot depend on itself.")
        ai = bool(result["ai_system"] or record.get("ai_system"))
        m = {
            "model_id": model_id,
            "name": record["name"].strip(),
            "version": (record.get("version") or "1.0").strip(),
            "risk_type": record["risk_type"],
            "category": record.get("category") or "",
            "business_line": record.get("business_line") or "",
            "methodology": record["methodology"].strip(),
            "source": record.get("source") or "In-house",
            "vendor": record.get("vendor") or None,
            "description": record["description"].strip(),
            "owner": record["owner"],
            "developer": record.get("developer") or "",
            "validator": "Not yet assigned",
            "sponsor": record.get("sponsor") or "",
            "lod_mapping": {
                "first_line": f"{record.get('business_line') or 'Business'} (development, use, monitoring)",
                "second_line": "Model validator — QDB validator or external consultant (independent validation)",
                "third_line": "Internal Audit (periodic review of the model governance framework)",
            },
            "tier_scores": dict(scores),
            "tier_rationale": record.get("tier_rationale") or "",
            "tier_override": None,
            "tier_assessment": {
                "scores": dict(scores), "rationale": record.get("tier_rationale") or "",
                "proposed_by": user["name"], "proposed_on": today,
                "status": governance.TIER_PROPOSED, "confirmed_by": None, "confirmed_on": None,
                "override_tier": None, "override_reason": None,
            },
            "tier_history": [],
            "status": record.get("status") or "In Development",
            "approval_date": record.get("approval_date") or None,
            "regulatory_mapping": _clean_list(record.get("regulatory_mapping")),
            "dependencies": {"upstream": upstream, "downstream": []},
            "documentation": _checklist_for(tier),
            "change_log": [],
            "audit_reviews": [],
            "data_sources": _clean_list(record.get("data_sources")),
            "implementation_platform": record.get("implementation_platform") or "",
            "usage_frequency": record.get("usage_frequency") or "",
            "model_users": _clean_list(record.get("model_users")),
            "key_assumptions": _clean_list(record.get("key_assumptions")),
            "known_limitations": _clean_list(record.get("known_limitations")),
            "exposure_covered_qar_mn": int(record.get("exposure_covered_qar_mn") or 0),
            "uses": record.get("uses") or [],
            "ai_system": ai,
            "qcb_ai_high_risk": record.get("qcb_ai_high_risk") if ai else None,
            "ai_functional_category": record.get("ai_functional_category") if ai else None,
            "ai_provider_role": record.get("ai_provider_role") if ai else None,
            "ai_autonomy": record.get("ai_autonomy") if ai else None,
            "qcb_approval_status": record.get("qcb_approval_status") if ai else None,
            "identification_answers": {k: bool(answers.get(k)) for k, _ in governance.IDENTIFICATION_QUESTIONS},
            "registered_by": user["name"],
            "registered_on": today,
            "placeholder": False,
            "pending_revalidation": False,
        }
        repository.put_model(conn, m)
        _sync_downstream(conn, model_id, [], upstream)
        log_event(conn, "register_model", "model", model_id, model_id,
                  f"Model registered: {m['name']} (tier {tier} proposed)", after=m)
    _refresh()
    return model_id


TOOL_PREFIX = {
    governance.CLASS_EUC: "QDB-EUC",
    governance.CLASS_AI_TOOL: "QDB-AI",
    governance.CLASS_NOT_MODEL: "QDB-NM",
}


def register_tool(record: dict, answers: dict) -> str:
    """Record a candidate that is NOT a model in the EUC / AI / not-a-model register."""
    auth.require("register_tool")
    result = governance.identify(answers)
    cls = result["classification"]
    if cls == governance.CLASS_MODEL:
        raise ValueError("This is a model — register it in the model inventory.")
    for f in ("name", "description", "owner"):
        if not str(record.get(f) or "").strip():
            raise ValueError(f"'{f}' is required.")
    user = auth.get_current_user()
    today = date.today().isoformat()
    with repository.tx() as conn:
        prefix = TOOL_PREFIX[cls]
        tool_id = _next_id([i for i in repository.tool_ids(conn) if i.startswith(prefix + "-")], prefix)
        ai = result["ai_system"]
        t = {
            "tool_id": tool_id, "name": record["name"].strip(), "classification": cls,
            "description": record["description"].strip(), "owner": record["owner"],
            "business_area": record.get("business_area") or "",
            "platform": record.get("platform") or "",
            "materiality": record.get("materiality") or "Low",
            "controls": record.get("controls") or "",
            "ai_system": ai,
            "qcb_ai_high_risk": record.get("qcb_ai_high_risk") if ai else None,
            "ai_functional_category": record.get("ai_functional_category") if ai else None,
            "ai_provider_role": record.get("ai_provider_role") if ai else None,
            "ai_autonomy": record.get("ai_autonomy") if ai else None,
            "qcb_approval_status": record.get("qcb_approval_status") if ai else None,
            "related_models": _clean_list(record.get("related_models")),
            "identification_answers": {k: bool(answers.get(k)) for k, _ in governance.IDENTIFICATION_QUESTIONS},
            "registered_by": user["name"], "registered_on": today, "last_reviewed": today,
        }
        repository.put_tool(conn, t)
        log_event(conn, "register_tool", "tool", tool_id, "", f"{cls} registered: {t['name']}", after=t)
    _refresh()
    return tool_id


def update_model(model_id: str, changes: dict) -> list[str]:
    """Edit a model record. Returns the list of fields that changed.

    Owners and developers may edit descriptive fields of their own models;
    accountability fields (owner, developer, validator, sponsor, risk type)
    are for the MRM Administrator. Tier, status and validation dates are not
    edited here: they move through tier sign-off and the workflows."""
    auth.require("edit_model")
    user = auth.get_current_user()
    allowed = set(governance.DESCRIPTIVE_FIELDS) | set(governance.ASSIGNMENT_FIELDS)
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"These fields cannot be edited here: {', '.join(sorted(unknown))}")

    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if user["role"] == "LOD1" and not governance.is_owner_or_developer(m, user["name"]):
            raise PermissionError(f"Only the owner or developer of {model_id} can edit its record.")
        before = copy.deepcopy(m)
        changed = []
        for field, value in changes.items():
            if field in ("data_sources", "model_users", "key_assumptions",
                         "known_limitations", "regulatory_mapping"):
                value = _clean_list(value)
            if field == "exposure_covered_qar_mn":
                value = int(value or 0)
            current = m["dependencies"]["upstream"] if field == "upstream" else m.get(field)
            if field == "upstream":
                value = _clean_list(value)
            if value == current:
                continue
            if field in governance.ASSIGNMENT_FIELDS:
                auth.require("assign_accountability")
            changed.append(field)
            if field == "upstream":
                if model_id in value:
                    raise ValueError("A model cannot depend on itself.")
                _sync_downstream(conn, model_id, m["dependencies"]["upstream"], value)
                m["dependencies"]["upstream"] = value
            else:
                m[field] = value
        if not changed:
            return []
        if "validator" in changed and m["validator"] != "Not yet assigned":
            _check_independence(m, m["validator"], "VAL")
        sponsor = governance.person_name(m.get("sponsor"))
        if sponsor and sponsor in (governance.person_name(m.get("owner")),
                                   governance.person_name(m.get("developer"))):
            raise ValueError("The model sponsor must be a different person from the owner and the developer: "
                             "the two approvals are a four-eyes check.")
        if not m.get("ai_system"):
            for k in ("qcb_ai_high_risk", "ai_functional_category", "ai_provider_role",
                      "ai_autonomy", "qcb_approval_status"):
                m[k] = None
        repository.put_model(conn, m)
        log_event(conn, "edit_model", "model", model_id, model_id,
                  f"Record edited: {', '.join(changed)}", before=before, after=m)
    _refresh()
    return changed


# ---------------------------------------------------------------- tier sign-off (G1)
def _apply_tier(m: dict, scores: dict, rationale: str, override: int | None,
                confirmed_by: str) -> None:
    from tiering import compute_tier

    m["tier_scores"] = dict(scores)
    m["tier_rationale"] = rationale
    m["tier_override"] = override
    tier = override or compute_tier(**scores)["tier"]
    m["documentation"] = _checklist_for(tier, m.get("documentation"))
    ta = m["tier_assessment"]
    ta.update({"status": governance.TIER_CONFIRMED, "confirmed_by": confirmed_by,
               "confirmed_on": date.today().isoformat()})


def propose_tier(model_id: str, scores: dict, rationale: str) -> None:
    """Owner/developer (or MRM Administrator) proposes a tier reassessment."""
    from tiering import compute_tier

    auth.require("propose_tier")
    user = auth.get_current_user()
    compute_tier(**scores)  # validates the ratings
    if not rationale.strip():
        raise ValueError("A rationale is required.")
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if user["role"] == "LOD1" and not governance.is_owner_or_developer(m, user["name"]):
            raise PermissionError(f"Only the owner or developer of {model_id} can propose its tier.")
        if not governance.tier_confirmed(m):
            raise ValueError("A tier assessment is already awaiting sign-off.")
        before = copy.deepcopy(m)
        old = m.get("tier_assessment") or {}
        m.setdefault("tier_history", []).append({
            "scores": dict(m["tier_scores"]),
            "tier": governance.effective_tier(m),
            "override": m.get("tier_override"),
            "rationale": m.get("tier_rationale"),
            "confirmed_by": old.get("confirmed_by"),
            "confirmed_on": old.get("confirmed_on"),
        })
        m["tier_assessment"] = {
            "scores": dict(scores), "rationale": rationale.strip(),
            "proposed_by": user["name"], "proposed_on": date.today().isoformat(),
            "status": governance.TIER_PROPOSED, "confirmed_by": None, "confirmed_on": None,
            "override_tier": None, "override_reason": None,
        }
        repository.put_model(conn, m)
        log_event(conn, "propose_tier", "tier_assessment", model_id, model_id,
                  f"Tier {compute_tier(**scores)['tier']} proposed", before=before, after=m)
    _refresh()


def confirm_tier(model_id: str, override_tier: int | None = None,
                 override_reason: str | None = None) -> str:
    """Gate G1: the MRM function confirms the proposed tier. An override (a tier
    different from the rule-based one) needs a reason and the model sponsor's approval.
    Returns the resulting assessment status."""
    from tiering import compute_tier

    auth.require("confirm_tier")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        ta = m.get("tier_assessment") or {}
        if ta.get("status") != governance.TIER_PROPOSED:
            raise ValueError("There is no proposed tier awaiting confirmation.")
        if ta.get("proposed_by") == user["name"]:
            raise PermissionError("The person who proposed a tier cannot confirm it.")
        before = copy.deepcopy(m)
        computed = compute_tier(**ta["scores"])["tier"]
        if override_tier and int(override_tier) != computed:
            if not (override_reason or "").strip():
                raise ValueError("An override needs a written reason.")
            if not governance.person_name(m.get("sponsor")):
                raise ValueError("An override is approved by the model sponsor — assign a sponsor first.")
            ta.update({"status": governance.TIER_OVERRIDE_PENDING, "confirmed_by": user["name"],
                       "confirmed_on": date.today().isoformat(),
                       "override_tier": int(override_tier), "override_reason": override_reason.strip()})
            details = f"Tier override to {override_tier} (rule-based {computed}) sent to the sponsor"
        else:
            _apply_tier(m, ta["scores"], ta["rationale"], None, user["name"])
            details = f"Tier {computed} confirmed (G1)"
        repository.put_model(conn, m)
        log_event(conn, "confirm_tier", "tier_assessment", model_id, model_id, details,
                  before=before, after=m)
    _refresh()
    return m["tier_assessment"]["status"]


def decide_tier_override(model_id: str, approve: bool, comment: str = "") -> None:
    """The model's sponsor approves or rejects a tier override. Rejection confirms
    the rule-based tier."""
    auth.require("approve_tier_override")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if governance.person_name(m.get("sponsor")) != user["name"]:
            raise PermissionError(f"Only the sponsor of {model_id} decides on its tier override.")
        ta = m.get("tier_assessment") or {}
        if ta.get("status") != governance.TIER_OVERRIDE_PENDING:
            raise ValueError("There is no tier override awaiting approval.")
        before = copy.deepcopy(m)
        override = ta["override_tier"] if approve else None
        confirmer = ta.get("confirmed_by")
        ta["sponsor_decision"] = {"approved": bool(approve), "by": user["name"],
                              "on": date.today().isoformat(), "comment": comment.strip()}
        _apply_tier(m, ta["scores"], ta["rationale"], override, confirmer)
        repository.put_model(conn, m)
        log_event(conn, "decide_tier_override", "tier_assessment", model_id, model_id,
                  f"Tier override {'approved' if approve else 'rejected'} by the sponsor"
                  + (f": {comment.strip()[:60]}" if comment.strip() else ""),
                  before=before, after=m)
    _refresh()



# ================================================================ Phase 2 — validation workflow
def _required_docs_missing(conn, m: dict) -> list[str]:
    tier = governance.effective_tier(m)
    uploaded = {e.get("doc_type") for e in repository.list_evidence_conn(conn)
                if e["model_id"] == m["model_id"]}
    return [d for d in governance.G2_REQUIRED_DOCS[tier]
            if not m["documentation"].get(d) and d not in uploaded]


def submit_for_validation(model_id: str, note: str = "") -> str:
    """Gate G2: the owner submits a model in development for validation.

    Needs a confirmed tier (G1) and the tier's required documents. Opens an
    initial validation (VAL) assigned to the model's validator. Returns its id."""
    auth.require("submit_for_validation")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if user["role"] == "LOD1" and not governance.is_owner_or_developer(m, user["name"]):
            raise PermissionError(f"Only the owner or developer of {model_id} can submit it.")
        if m["status"] != "In Development":
            raise ValueError(f"{model_id} is {m['status']}; only models in development can be submitted.")
        if not governance.tier_confirmed(m):
            raise ValueError("The tier must be confirmed first (gate G1).")
        missing = _required_docs_missing(conn, m)
        if missing:
            raise ValueError("Upload the required documents first: " + ", ".join(missing) + ".")
        before = copy.deepcopy(m)
        m["status"] = "In Validation"
        repository.put_model(conn, m)
        log_event(conn, "submit_for_validation", "model", model_id, model_id,
                  "Submitted for validation (G2)", before=before, after=m)

        validator = m["validator"] if m.get("validator") not in (None, "", "Not yet assigned") else ""
        if validator and governance.independence_conflict(m, validator, "VAL"):
            validator = ""
        rid = _next_id(repository.request_ids(conn, "VAL"), "VAL")
        req = {
            "request_id": rid, "type": "VAL", "model_id": model_id,
            "status": "In Progress" if validator else "Open",
            "initiated_by": user["name"], "initiated_by_role": user["role"],
            "assigned_to": validator, "title": "Initial validation",
            "description": note or "Submitted for initial validation (gate G2).",
            "created_date": date.today().isoformat(), "closed_date": None, "due_date": None,
            "outcome": None, "severity": None, "remediation": None, "source": "LoD1 Request",
            "materiality": None, "validation_subtype": "Initial", "tests": [],
            "thread": [], "engagement": new_engagement(),
        }
        repository.put_request(conn, req)
        log_event(conn, "initiate_val", "validation_request", rid, model_id,
                  "VAL opened: Initial validation (from G2 submission)", after=req)
    _refresh()
    return rid


def _engagement_request(conn, request_id: str) -> tuple[dict, dict, dict]:
    r = _request_or_fail(conn, request_id)
    if not _needs_engagement(r):
        raise ValueError(f"{request_id} is not a validation.")
    if r["status"] == "Closed":
        raise ValueError(f"{request_id} is closed.")
    eng = r.get("engagement") or new_engagement()
    r["engagement"] = eng
    return r, eng, _model_or_fail(conn, r["model_id"])


def _require_assigned_validator(r: dict, m: dict) -> None:
    auth.require("run_engagement")
    me = auth.get_current_user()["name"]
    if governance.person_name(r.get("assigned_to")) != me:
        raise PermissionError(f"Only the assigned validator can do this ({r.get('assigned_to') or 'unassigned'}).")
    _check_independence(m, me, "VAL")


def _save_engagement(conn, r, before, action, details) -> None:
    repository.put_request(conn, r)
    log_event(conn, action, "validation_request", r["request_id"], r["model_id"], details,
              before=before, after=r)


def start_engagement(request_id: str, scope: str, planned_tests: list[str]) -> None:
    """Validator records the scope and declares independence; fieldwork starts.
    An unassigned validation is taken by the validator starting it."""
    auth.require("run_engagement")
    user = auth.get_current_user()
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        before = copy.deepcopy(r)
        if not r.get("assigned_to"):
            _check_independence(m, user["name"], r["type"])
            r["assigned_to"] = auth.user_option_label(user)
        _require_assigned_validator(r, m)
        if eng["stage"] not in ("Scoping", "Fieldwork"):
            raise ValueError("The scope can only be set before the draft report.")
        if not scope.strip():
            raise ValueError("Describe the scope of the validation.")
        eng.update({"stage": "Fieldwork", "scope": scope.strip(), "planned_tests": planned_tests,
                    "independence": {"declared_by": user["name"], "on": date.today().isoformat()}})
        r["status"] = "In Progress"
        _save_engagement(conn, r, before, "start_engagement",
                         "Scope set and independence declared — fieldwork started")
    _refresh()


def add_info_request(request_id: str, item: str, owner: str, due: str) -> str:
    """Validator asks the first line for an item (document, data, explanation)."""
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        _require_assigned_validator(r, m)
        if eng["stage"] != "Fieldwork":
            raise ValueError("Information requests are raised during fieldwork.")
        if not item.strip():
            raise ValueError("Describe the item requested.")
        before = copy.deepcopy(r)
        ir_id = f"IR-{len(eng['info_requests']) + 1}"
        eng["info_requests"].append({
            "ir_id": ir_id, "item": item.strip(), "owner": owner, "due": due, "status": "Open",
            "response": None, "answered_by": None, "answered_on": None, "review_comment": None,
            "evidence_ids": [],
        })
        _save_engagement(conn, r, before, "add_info_request", f"{ir_id} requested: {item.strip()[:70]}")
    _refresh()
    return ir_id


def answer_info_request(request_id: str, ir_id: str, response: str,
                        evidence_ids: list[str] | None = None) -> None:
    """First line answers an information request (the IR owner, or the model's owner/developer)."""
    auth.require("answer_info_request")
    user = auth.get_current_user()
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        ir = next((i for i in eng["info_requests"] if i["ir_id"] == ir_id), None)
        if ir is None:
            raise ValueError(f"Unknown information request {ir_id}")
        if user["name"] not in (governance.person_name(ir["owner"]),) and \
                not governance.is_owner_or_developer(m, user["name"]):
            raise PermissionError("Only the person asked, or the model's owner or developer, can answer.")
        if not response.strip():
            raise ValueError("Write a response.")
        before = copy.deepcopy(r)
        ir.update({"status": "Answered", "response": response.strip(), "answered_by": user["name"],
                   "answered_on": date.today().isoformat()})
        ir["evidence_ids"] = list(ir.get("evidence_ids") or []) + list(evidence_ids or [])
        _save_engagement(conn, r, before, "answer_info_request", f"{ir_id} answered")
    _refresh()


def send_back_info_request(request_id: str, ir_id: str, comment: str) -> None:
    """Validator sends an inadequate answer back to the first line (open again).
    Answers that are not sent back count as accepted when the draft is issued."""
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        _require_assigned_validator(r, m)
        ir = next((i for i in eng["info_requests"] if i["ir_id"] == ir_id), None)
        if ir is None:
            raise ValueError(f"Unknown information request {ir_id}")
        if ir["status"] != "Answered":
            raise ValueError(f"{ir_id} has no answer to send back.")
        if not comment.strip():
            raise ValueError("Say what is still missing.")
        before = copy.deepcopy(r)
        ir["status"] = "Open"
        ir["review_comment"] = comment.strip()
        _save_engagement(conn, r, before, "send_back_info_request", f"{ir_id} sent back")
    _refresh()


def issue_draft(request_id: str, rating: str, summary: str) -> None:
    """Validator issues the draft report and proposed rating for the owner's review."""
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        _require_assigned_validator(r, m)
        if eng["stage"] != "Fieldwork":
            raise ValueError("The draft is issued at the end of fieldwork.")
        reason = governance.engagement_can_issue_draft(eng)
        if reason:
            raise ValueError(reason)
        if rating not in governance.RATING_SCALE:
            raise ValueError("Choose a rating from the rating scale.")
        if not summary.strip():
            raise ValueError("Summarise the conclusions.")
        before = copy.deepcopy(r)
        eng["draft"] = {"rating": rating, "summary": summary.strip(),
                        "issued_by": auth.get_current_user()["name"],
                        "issued_on": date.today().isoformat()}
        eng["stage"] = "Owner review"
        _save_engagement(conn, r, before, "issue_draft", f"Draft report issued — proposed rating {rating}")
    _refresh()


def submit_owner_review(request_id: str, comments: str) -> None:
    """Model owner/developer gives the factual-accuracy review of the draft."""
    auth.require("owner_review")
    user = auth.get_current_user()
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        if not governance.is_owner_or_developer(m, user["name"]):
            raise PermissionError("Only the model's owner or developer gives the factual-accuracy review.")
        if eng["stage"] != "Owner review" or eng.get("owner_review"):
            raise ValueError("There is no draft awaiting review.")
        before = copy.deepcopy(r)
        eng["owner_review"] = {"comments": comments.strip() or "No factual-accuracy comments.",
                               "by": user["name"], "on": date.today().isoformat()}
        _save_engagement(conn, r, before, "owner_review", "Owner's factual-accuracy review submitted")
    _refresh()


def sign_off(request_id: str, rating: str, comment: str, tests: list[str] | None = None) -> None:
    """Gate G3: the validator signs off the validation with the final rating.

    Allowed after the owner's review, or once the review window has lapsed."""
    with repository.tx() as conn:
        r, eng, m = _engagement_request(conn, request_id)
        _require_assigned_validator(r, m)
        reason = governance.engagement_can_sign_off(eng)
        if reason:
            raise ValueError(reason)
        if rating not in governance.RATING_SCALE:
            raise ValueError("Choose a rating from the rating scale.")
        before = copy.deepcopy(r)
        eng["signed_off"] = {"rating": rating, "by": auth.get_current_user()["name"],
                             "on": date.today().isoformat()}
        eng["stage"] = "Signed off"
        repository.put_request(conn, r)
        log_event(conn, "sign_off", "validation_request", request_id, r["model_id"],
                  f"Validation signed off — rating {rating} (G3)", before=before, after=r)
    close_request(request_id, comment or f"Signed off — rating {rating}.", outcome=rating,
                  tests=tests or eng.get("planned_tests") or None, _signed_off=True)


def record_approval(model_id: str, decision: str, conditions: list[dict] | None = None,
                    comment: str = "") -> str | None:
    """Gate G4: the model owner signs first, then the model sponsor.

    Each signs Approved, Approved with conditions or Rejected. A rejection by either
    ends the approval. Conditions from both signatures are combined. When the
    sponsor signs, the approval is complete and the model waits for implementation
    verification (G5). Returns the approval ID once complete, else None."""
    auth.require("record_approval")
    user = auth.get_current_user()
    if decision not in governance.APPROVAL_DECISIONS:
        raise ValueError(f"Decision must be one of {governance.APPROVAL_DECISIONS}")
    conditions = [c for c in (conditions or []) if str(c.get("condition") or "").strip()]
    if decision == "Approved with conditions" and not conditions:
        raise ValueError("List at least one condition.")
    if decision == "Rejected" and not comment.strip():
        raise ValueError("Give the reason for the rejection.")
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if m["status"] != governance.STATUS_AWAITING_APPROVAL:
            raise ValueError(f"{model_id} is not awaiting approval.")
        signer = governance.next_approver(m)
        expected = governance.approver_name(m, signer)
        if user["name"] != expected:
            raise PermissionError(
                f"{model_id} is waiting for the {signer.lower()} ({expected or 'not assigned'}) to sign.")
        if user["name"] == governance.person_name(m.get("developer")):
            raise PermissionError("The model developer cannot approve the model.")
        before = copy.deepcopy(m)
        today = date.today().isoformat()
        pending = m.setdefault("pending_approval", {"signatures": [], "conditions": []})
        pending["signatures"].append({"as": signer, "by": auth.user_option_label(user), "on": today,
                                      "decision": decision, "comment": comment.strip() or None})
        if decision != "Rejected":
            pending["conditions"] += [{"condition": str(c["condition"]).strip(),
                                       "owner": c.get("owner") or m["owner"], "due": c.get("due") or None,
                                       "set_by": signer} for c in conditions]
        complete = decision == "Rejected" or signer == governance.APPROVERS[-1]
        approval_id = None
        if complete:
            existing = [a["approval_id"] for mm in repository.list_models_conn(conn)
                        for a in mm.get("approvals") or []]
            approval_id = _next_id(existing, "APR")
            conds = [{
                "cond_id": f"C-{i}", "condition": c["condition"], "owner": c["owner"], "due": c["due"],
                "set_by": c["set_by"], "status": governance.CONDITION_OPEN, "note": None, "met_on": None,
                "verified_by": None, "verified_on": None,
            } for i, c in enumerate(pending["conditions"], start=1)] if decision != "Rejected" else []
            final = "Rejected" if decision == "Rejected" else \
                "Approved with conditions" if conds else "Approved"
            m.setdefault("approvals", []).append({
                "approval_id": approval_id, "date": today, "body": governance.approval_body(),
                "decision": final, "conditions": conds, "version": m["version"],
                "signatures": pending["signatures"], "recorded_by": auth.user_option_label(user),
                "comment": comment.strip() or None,
            })
            m.pop("pending_approval", None)
            if final == "Rejected":
                prior = [a for a in m["approvals"][:-1] if a["decision"] != "Rejected"]
                m["status"] = "Under Remediation" if prior else "In Development"
            else:
                m["status"] = governance.STATUS_AWAITING_IMPLEMENTATION
                m["approval_date"] = today
            details = f"{final} — signed by the {signer.lower()} (G4 complete)"
        else:
            details = f"{decision} by the {signer.lower()} — waiting for the model sponsor (G4)"
        repository.put_model(conn, m)
        log_event(conn, "record_approval", "approval", approval_id or f"{model_id}/pending", model_id,
                  details, before=before, after=m)
    _refresh()
    return approval_id


def update_condition(model_id: str, approval_id: str, cond_id: str, action: str, note: str = "") -> None:
    """Conditions of approval: the owner marks one met; a validator verifies it,
    or reopens it with a reason."""
    auth.require("update_condition")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        ap = next((a for a in m.get("approvals") or [] if a["approval_id"] == approval_id), None)
        cond = next((c for c in (ap or {}).get("conditions", []) if c["cond_id"] == cond_id), None)
        if cond is None:
            raise ValueError("Unknown condition.")
        before = copy.deepcopy(m)
        today = date.today().isoformat()
        if action == "met":
            if user["role"] != "LOD1" or not (
                governance.is_owner_or_developer(m, user["name"])
                or governance.person_name(cond.get("owner")) == user["name"]
            ):
                raise PermissionError("The model owner or developer marks a condition as met.")
            if cond["status"] != governance.CONDITION_OPEN:
                raise ValueError("Only an open condition can be marked as met.")
            if not note.strip():
                raise ValueError("Say how the condition was met.")
            cond.update({"status": governance.CONDITION_MET, "note": note.strip(), "met_on": today})
        elif action in ("verify", "reopen"):
            if user["role"] != "LOD2":
                raise PermissionError("A validator verifies conditions.")
            if governance.is_owner_or_developer(m, user["name"]):
                raise PermissionError("Owners and developers cannot verify their own conditions.")
            if cond["status"] != governance.CONDITION_MET:
                raise ValueError("Only a condition marked as met can be verified or reopened.")
            if action == "verify":
                cond.update({"status": governance.CONDITION_VERIFIED, "verified_by": user["name"],
                             "verified_on": today})
            else:
                if not note.strip():
                    raise ValueError("Say why the condition is reopened.")
                cond.update({"status": governance.CONDITION_OPEN, "note": f"Reopened: {note.strip()}"})
        else:
            raise ValueError(f"Unknown action {action}")
        repository.put_model(conn, m)
        log_event(conn, f"condition_{action}", "approval", f"{approval_id}/{cond_id}", model_id,
                  f"Condition {cond_id} of {approval_id}: {cond['status']}", before=before, after=m)
    _refresh()


def verify_implementation(model_id: str, note: str) -> str:
    """Gate G5: a validator confirms the deployed version is the validated and
    approved one; the model goes into use. Returns the new status."""
    auth.require("verify_implementation")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        if m["status"] != governance.STATUS_AWAITING_IMPLEMENTATION:
            raise ValueError(f"{model_id} is not awaiting implementation.")
        _check_independence(m, user["name"], "VAL")
        if not note.strip():
            raise ValueError("Describe what was checked (version, configuration, reconciliation).")
        if not [k for k in _kmpis_of(conn, model_id) if k.get("active", True)]:
            raise ValueError("Define at least one KMPI before the model goes into use, "
                             "so its performance is monitored from the first period.")
        before = copy.deepcopy(m)
        m.setdefault("implementation", []).append({
            "version": m["version"], "verified_by": auth.user_option_label(user),
            "verified_on": date.today().isoformat(), "note": note.strip(),
        })
        latest = (m.get("approvals") or [{}])[-1]
        open_conditions = [c for c in latest.get("conditions", [])
                           if c["status"] != governance.CONDITION_VERIFIED]
        m["status"] = "Approved with Conditions" if open_conditions else "In Production"
        repository.put_model(conn, m)
        log_event(conn, "verify_implementation", "implementation", model_id, model_id,
                  f"Implementation of v{m['version']} verified (G5) — status {m['status']}",
                  before=before, after=m)
    _refresh()
    return m["status"]



# ================================================================ Phase 3 — KMPIs
KMPI_FIELDS = ["name", "category", "description", "definition", "data_source", "unit",
               "direction", "amber", "red", "frequency", "active"]
_KMPI_CONTROL_FIELDS = {"direction", "amber", "red", "frequency", "active"}


def _require_first_line(m: dict, user: dict, what: str) -> None:
    if user["role"] == "LOD1" and not governance.is_owner_or_developer(m, user["name"]):
        raise PermissionError(f"Only the owner or developer of {m['model_id']} can {what}.")


def save_kmpi(model_id: str, fields: dict, kmpi_id: str | None = None, reason: str = "") -> str:
    """Add a KMPI to a model's library, or change one. Changing a threshold,
    the direction, the frequency, or retiring a KMPI needs a reason; every
    change is kept on the KMPI so the validator sees it at the next review."""
    auth.require("define_kmpi")
    user = auth.get_current_user()
    fields = {k: v for k, v in fields.items() if k in KMPI_FIELDS}
    for f in ("name", "description", "definition"):
        if f in fields:
            fields[f] = str(fields[f] or "").strip()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        _require_first_line(m, user, "define its KMPIs")
        today = date.today().isoformat()
        if kmpi_id is None:
            missing = [f for f in ("name", "description", "definition", "direction", "amber", "red")
                       if fields.get(f) in (None, "")]
            if missing:
                raise ValueError(f"Complete: {', '.join(missing)}.")
            kmpi_id = _next_id(repository.kmpi_ids(conn), "KMPI")
            k = {"kmpi_id": kmpi_id, "model_id": model_id, "category": "Calibration / back-testing",
                 "data_source": "", "unit": "ratio", "frequency": "Quarterly", "active": True,
                 **fields, "defined_by": auth.user_option_label(user), "defined_on": today, "changes": []}
            before = None
            details = f"KMPI {kmpi_id} added: {k['name']}"
        else:
            k = next((x for x in repository.list_kmpis(conn) if x["kmpi_id"] == kmpi_id), None)
            if k is None or k["model_id"] != model_id:
                raise ValueError(f"Unknown KMPI {kmpi_id} for {model_id}.")
            before = copy.deepcopy(k)
            changed = {f: v for f, v in fields.items() if v != k.get(f)}
            if not changed:
                return kmpi_id
            if set(changed) & _KMPI_CONTROL_FIELDS and not reason.strip():
                raise ValueError("Give a reason for changing a threshold, the direction, "
                                 "the frequency, or retiring a KMPI.")
            k.update(changed)
            k.setdefault("changes", []).append({
                "on": today, "by": auth.user_option_label(user), "reason": reason.strip() or None,
                "fields": sorted(changed),
                "before": {f: before.get(f) for f in changed}, "after": changed,
            })
            details = f"KMPI {kmpi_id} changed: {', '.join(sorted(changed))}" + \
                (f" — {reason.strip()[:60]}" if reason.strip() else "")
        if not k["name"]:
            raise ValueError("A KMPI needs a name.")
        if k["direction"] not in kmpi_rules.DIRECTIONS or k["frequency"] not in kmpi_rules.FREQUENCIES:
            raise ValueError("Choose a direction and a frequency from the lists.")
        kmpi_rules.check_thresholds(k["direction"], k["amber"], k["red"])
        repository.put_kmpi(conn, k)
        log_event(conn, "save_kmpi", "kmpi", kmpi_id, model_id, details, before=before, after=k)
    _refresh()
    return kmpi_id


def _kmpis_of(conn, model_id: str) -> list[dict]:
    return [k for k in repository.list_kmpis(conn) if k["model_id"] == model_id]


def save_kmpi_return(model_id: str, period: str, entries: dict, submit: bool = False,
                     attest: bool = False, note: str = "") -> str:
    """The owner or developer enters the period's KMPI values ({kmpi_id: {value,
    comment}}) and saves a draft, or submits. Submitting needs a value (or a
    reason it is missing) for every KMPI due, an explanation for every amber or
    red value, and the attestation. Thresholds are copied into the return, so
    a later threshold change does not rewrite history. Returns the new status."""
    auth.require("enter_kmpi")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        _require_first_line(m, user, "report its KMPIs")
        ret = repository.get_kmpi_return(conn, model_id, period)
        status = kmpi_rules.return_status(ret)
        if status not in kmpi_rules.EDITABLE:
            raise ValueError(f"The {period} return is {status.lower()} and can no longer be changed.")
        due = kmpi_rules.due_kmpis(_kmpis_of(conn, model_id), period)
        if not due:
            raise ValueError(f"{model_id} has no KMPIs due for {period}.")
        before = copy.deepcopy(ret)
        ret = ret or {"model_id": model_id, "period": period, "status": kmpi_rules.DRAFT,
                      "values": {}, "history": []}
        for k in due:
            e = entries.get(k["kmpi_id"])
            if e is None:
                continue
            value = e.get("value")
            value = None if value is None or (isinstance(value, float) and value != value) else float(value)
            ret["values"][k["kmpi_id"]] = {
                "name": k["name"], "value": value, "comment": (e.get("comment") or "").strip(),
                "direction": k["direction"], "amber": k["amber"], "red": k["red"], "unit": k.get("unit"),
                "rag": kmpi_rules.rag(value, k["direction"], k["amber"], k["red"]),
            }
        today = date.today().isoformat()
        ret.update({"entered_by": auth.user_option_label(user), "updated_on": today})
        if submit:
            problems = kmpi_rules.submission_problems(due, ret["values"])
            if problems:
                raise ValueError("Cannot submit yet — " + "; ".join(problems) + ".")
            if not attest:
                raise ValueError("Tick the attestation to submit.")
            ret.update({"status": kmpi_rules.SUBMITTED, "submitted_by": auth.user_option_label(user),
                        "submitted_on": today, "attestation": kmpi_rules.ATTESTATION,
                        "note": note.strip() or None})
            action, details = "submit_kmpi_return", f"KMPI return {period} submitted"
        else:
            ret["status"] = kmpi_rules.DRAFT if status != kmpi_rules.RETURNED else kmpi_rules.RETURNED
            action, details = "save_kmpi_return", f"KMPI return {period} saved as draft"
        ret["history"].append({"action": "Submitted" if submit else "Saved", "by": auth.user_option_label(user),
                               "on": today, "comment": note.strip() or None})
        worst = kmpi_rules.worst(v["rag"] for v in ret["values"].values())
        repository.put_kmpi_return(conn, ret)
        log_event(conn, action, "kmpi_return", f"{model_id}/{period}", model_id,
                  details + (f" — worst {worst}" if worst else ""), before=before, after=ret)
    _refresh()
    return ret["status"]


def review_kmpi_return(model_id: str, period: str, accept: bool, comment: str = "",
                       raise_finding: bool = False, severity: str = "Medium") -> str | None:
    """The validator reviews a submitted return: marks it reviewed, or sends it
    back with a reason. On review the validator may raise one finding for the
    amber and red KMPIs; it is opened through the normal finding workflow.
    Returns the finding ID if one was raised."""
    auth.require("review_kmpi")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        _check_independence(m, user["name"], "VAL")
        ret = repository.get_kmpi_return(conn, model_id, period)
        if kmpi_rules.return_status(ret) != kmpi_rules.SUBMITTED:
            raise ValueError(f"The {period} return has not been submitted.")
        if not accept and not comment.strip():
            raise ValueError("Say what must be corrected before sending the return back.")
        breaches = {kid: v for kid, v in ret["values"].items() if v["rag"] in (kmpi_rules.AMBER, kmpi_rules.RED)}
        if raise_finding and (not accept or not breaches):
            raise ValueError("A finding can be raised when reviewing a return with amber or red KMPIs.")
        before = copy.deepcopy(ret)
        today = date.today().isoformat()
        if accept:
            ret.update({"status": kmpi_rules.REVIEWED, "reviewed_by": auth.user_option_label(user),
                        "reviewed_on": today, "review_comment": comment.strip() or None})
        else:
            ret["status"] = kmpi_rules.RETURNED
        ret["history"].append({"action": "Reviewed" if accept else "Returned",
                               "by": auth.user_option_label(user), "on": today,
                               "comment": comment.strip() or None})
        repository.put_kmpi_return(conn, ret)
        log_event(conn, "review_kmpi_return" if accept else "return_kmpi_return", "kmpi_return",
                  f"{model_id}/{period}", model_id,
                  f"KMPI return {period} " + ("reviewed" if accept else f"sent back: {comment.strip()[:60]}"),
                  before=before, after=ret)
    _refresh()
    if not raise_finding:
        return None
    lines = [f"{kid} {v['name']}: {v['value'] if v['value'] is not None else 'not reported'} ({v['rag']})"
             + (f" — owner's explanation: {v['comment']}" if v.get("comment") else "")
             for kid, v in breaches.items()]
    fid = create_request(model_id, {
        "type": "FND", "title": f"KMPI breach {period}: " + ", ".join(v["name"] for v in breaches.values())[:80],
        "description": "Raised from the KMPI review.\n" + "\n".join(lines),
        "assigned_to": m["owner"], "severity": severity, "source": "Monitoring",
        "remediation": comment.strip() or "Investigate the breach and agree corrective action.",
        "due_date": (date.today() + timedelta(days=90)).isoformat(),
    })
    with repository.tx() as conn:
        ret = repository.get_kmpi_return(conn, model_id, period)
        before = copy.deepcopy(ret)
        ret["finding_id"] = fid
        repository.put_kmpi_return(conn, ret)
        log_event(conn, "link_finding", "kmpi_return", f"{model_id}/{period}", model_id,
                  f"Finding {fid} raised from the {period} KMPI review", before=before, after=ret)
    _refresh()
    return fid



# ================================================================ Administration
PERSON_FIELDS = {
    "owner", "developer", "validator", "assigned_to", "initiated_by", "author", "uploaded_by",
    "proposed_by", "confirmed_by", "by", "declared_by", "issued_by", "answered_by",
    "recorded_by", "verified_by", "registered_by", "raised_by", "auditor", "sponsor",
    "entered_by", "submitted_by", "reviewed_by", "defined_by",
}


def _rename_in(obj, old: str, new_label_for):
    """Replace a person's name in name/label fields of a document, recursively.
    'Old' -> 'New' and 'Old (Title)' -> 'New (Title)'. Free text is left alone."""
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str) and k in PERSON_FIELDS:
                if v == old:
                    obj[k] = new_label_for(None)
                    changed = True
                elif v.startswith(old + " ("):
                    obj[k] = new_label_for(v[len(old):])
                    changed = True
            elif isinstance(v, (dict, list)):
                changed |= _rename_in(v, old, new_label_for)
    elif isinstance(obj, list):
        for v in obj:
            changed |= _rename_in(v, old, new_label_for)
    return changed


def save_user(old_name: str | None, name: str, title: str, role: str) -> int:
    """Add a user (old_name None) or rename / re-title / re-role one.

    A rename is carried into every record that names the person (owner,
    validator, thread authors, evidence uploads ...). The audit log keeps the
    names as they were at the time — it is never rewritten. Returns the number
    of records updated."""
    auth.require("administer")
    name, title = name.strip(), title.strip()
    if not name or not title:
        raise ValueError("Name and title are required.")
    if role not in auth.ROLE_LABELS:
        raise ValueError(f"Unknown role {role}")
    if "(" in name or ")" in name:
        raise ValueError("Names cannot contain brackets.")
    touched = 0
    with repository.tx() as conn:
        users = {u["name"]: u for u in repository.list_users_conn(conn)}
        if old_name is None:
            if name in users:
                raise ValueError(f"{name} already exists.")
            new = {"name": name, "title": title, "role": role}
            repository.put_user(conn, new)
            log_event(conn, "add_user", "user", name, "", f"User added: {name} ({title}, {role})", after=new)
        else:
            if old_name not in users:
                raise ValueError(f"Unknown user {old_name}")
            if name != old_name and name in users:
                raise ValueError(f"{name} already exists.")
            before = users[old_name]
            new = {**before, "name": name, "title": title, "role": role}
            if name != old_name:
                repository.delete_user(conn, old_name)
            repository.put_user(conn, new)
            if name != old_name or title != before.get("title"):
                old_suffix = f" ({before.get('title')})"

                def label_for(rest):
                    if rest is None:
                        return name
                    return f"{name} ({title})" if rest == old_suffix else f"{name}{rest}"

                for m in repository.list_models_conn(conn):
                    if _rename_in(m, old_name, label_for):
                        repository.put_model(conn, m)
                        touched += 1
                for r in repository.list_requests_conn(conn):
                    if _rename_in(r, old_name, label_for):
                        repository.put_request(conn, r)
                        touched += 1
                for e in repository.list_evidence_conn(conn):
                    if _rename_in(e, old_name, label_for):
                        repository.update_evidence(conn, e)
                        touched += 1
                for t in repository.list_tools_conn(conn):
                    if _rename_in(t, old_name, label_for):
                        repository.put_tool(conn, t)
                        touched += 1
            log_event(conn, "update_user", "user", name, "",
                      f"User {old_name} -> {name} ({title}, {role}); {touched} record(s) updated",
                      before=before, after=new)
    if old_name and st.session_state.get(auth._SESSION_KEY) == old_name:
        st.session_state[auth._SESSION_KEY] = name
    _refresh()
    return touched


def rename_model_id(old_id: str, new_id: str) -> None:
    """Renumber a model (e.g. QDB-007 -> QDB-101) everywhere it is referenced.
    Evidence files stay where they are; the audit log keeps the old id."""
    auth.require("administer")
    new_id = new_id.strip().upper()
    if not MODEL_ID_PATTERN.match(new_id):
        raise ValueError("Model IDs look like QDB-001.")
    with repository.tx() as conn:
        m = _model_or_fail(conn, old_id)
        if repository.get_model(new_id, conn):
            raise ValueError(f"{new_id} is already used.")
        before = copy.deepcopy(m)
        m["model_id"] = new_id
        repository.delete_model(conn, old_id)
        repository.put_model(conn, m)
        for other in repository.list_models_conn(conn):
            deps = other["dependencies"]
            if old_id in deps["upstream"] or old_id in deps["downstream"]:
                deps["upstream"] = [new_id if d == old_id else d for d in deps["upstream"]]
                deps["downstream"] = [new_id if d == old_id else d for d in deps["downstream"]]
                repository.put_model(conn, other)
        for r in repository.list_requests_conn(conn):
            if r["model_id"] == old_id:
                r["model_id"] = new_id
                repository.put_request(conn, r)
        for e in repository.list_evidence_conn(conn):
            changed = False
            if e["model_id"] == old_id:
                e["model_id"] = new_id
                changed = True
            if e.get("linked_type") == "model" and e.get("linked_id") == old_id:
                e["linked_id"] = new_id
                changed = True
            if changed:
                repository.update_evidence(conn, e)
        repository.rename_model_in_kmpis(conn, old_id, new_id)
        for t in repository.list_tools_conn(conn):
            if old_id in (t.get("related_models") or []):
                t["related_models"] = [new_id if x == old_id else x for x in t["related_models"]]
                repository.put_tool(conn, t)
        log_event(conn, "rename_model_id", "model", new_id, new_id,
                  f"Model ID changed from {old_id} to {new_id}", before=before, after=m)
    _refresh()
