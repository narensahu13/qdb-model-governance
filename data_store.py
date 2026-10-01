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
from datetime import date, datetime

import streamlit as st

import auth
import config
import governance
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
    new_status = governance.OUTCOME_TO_STATUS.get(outcome)
    changed = False
    if new_status and m["status"] not in ("In Development", "Retired"):
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
                  tests: list[str] | None = None) -> str:
    """Close a request with a closure comment (stored on the thread)."""
    user = auth.get_current_user()
    with repository.tx() as conn:
        r = _request_or_fail(conn, request_id)
        if not auth.can_close_request(r):
            raise PermissionError(
                "You cannot close this request: findings are closed by the line that "
                "raised them; validations and model changes by a validator."
            )
        if r["status"] == "Closed":
            raise ValueError("Request already closed")
        outcome = governance.normalise_outcome(outcome)
        if r["type"] in ("VAL", "MC") and outcome not in governance.RATING_SCALE:
            raise ValueError("Choose a rating from the validation rating scale.")
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


def register_model(record: dict, answers: dict) -> str:
    """Register a new model after the identification questionnaire.

    The proposed tier is recorded as *Proposed* until the MRM function confirms
    it (gate G1). Returns the new model id, e.g. QDB-CR-014."""
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
        prefix = f"QDB-{governance.MODEL_ID_PREFIX[record['risk_type']]}"
        existing = [i for i in repository.model_ids(conn) if i.startswith(prefix + "-")]
        model_id = _next_id(existing, prefix)
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
            "monitoring_metrics": [],
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
    different from the rule-based one) needs a reason and CRO approval.
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
            ta.update({"status": governance.TIER_OVERRIDE_PENDING, "confirmed_by": user["name"],
                       "confirmed_on": date.today().isoformat(),
                       "override_tier": int(override_tier), "override_reason": override_reason.strip()})
            details = f"Tier override to {override_tier} (rule-based {computed}) sent to the CRO"
        else:
            _apply_tier(m, ta["scores"], ta["rationale"], None, user["name"])
            details = f"Tier {computed} confirmed (G1)"
        repository.put_model(conn, m)
        log_event(conn, "confirm_tier", "tier_assessment", model_id, model_id, details,
                  before=before, after=m)
    _refresh()
    return m["tier_assessment"]["status"]


def decide_tier_override(model_id: str, approve: bool, comment: str = "") -> None:
    """CRO approves or rejects a tier override. Rejection confirms the rule-based tier."""
    auth.require("approve_tier_override")
    user = auth.get_current_user()
    with repository.tx() as conn:
        m = _model_or_fail(conn, model_id)
        ta = m.get("tier_assessment") or {}
        if ta.get("status") != governance.TIER_OVERRIDE_PENDING:
            raise ValueError("There is no tier override awaiting approval.")
        before = copy.deepcopy(m)
        override = ta["override_tier"] if approve else None
        confirmer = ta.get("confirmed_by")
        ta["cro_decision"] = {"approved": bool(approve), "by": user["name"],
                              "on": date.today().isoformat(), "comment": comment.strip()}
        _apply_tier(m, ta["scores"], ta["rationale"], override, confirmer)
        repository.put_model(conn, m)
        log_event(conn, "decide_tier_override", "tier_assessment", model_id, model_id,
                  f"Tier override {'approved' if approve else 'rejected'} by CRO"
                  + (f": {comment.strip()[:60]}" if comment.strip() else ""),
                  before=before, after=m)
    _refresh()
