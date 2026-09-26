"""Persistence layer: every write to the mock JSON data files goes through
here. Each write also appends an event to data/audit_log.json and clears the
Streamlit data cache so all pages refresh. Swapping the JSON files for a real
database later only requires changing this module and data_loader.py.

Source of truth for validation workflow: data/validation_requests.json
(types MC / VAL / FND). Historical validations.json and
issues.json remain as read-only archives from the migration.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

import auth

DATA_DIR = Path(__file__).resolve().parent / "data"
EVIDENCE_DIR = DATA_DIR / "evidence"
REQUESTS_FILE = "validation_requests.json"

FREQUENCY_DAYS = {"Annual": 365, "Biennial": 730, "Triennial": 1095}

EVIDENCE_CATEGORIES = ["Document", "Code", "Email", "Screenshot", "Data extract", "Other"]

# linked_type values used when attaching evidence in-context
EVIDENCE_LINK_TYPES = (
    "validation_request", "request_response",
    "validation", "issue", "issue_response",  # legacy aliases still readable
    "change", "audit", "model",
)

ALLOWED_UPLOAD_TYPES = ["pdf", "docx", "xlsx", "py", "txt", "msg", "eml", "png", "jpg", "zip"]

REQUEST_STATUSES = ["Open", "In Progress", "Closed"]

VAL_SUBTYPES = [
    "Initial",
    "Periodic",
    "Targeted",
    "Ad-hoc",
]

MATERIALITY_OPTIONS = ["Material", "Non-material"]

# Legacy labels still accepted by add_validation() compatibility wrapper
VALIDATION_TYPES = VAL_SUBTYPES + [
    "Material Model Change",
    "Non-material Model Change Review",
    "Initial (pre-implementation)",
    "Periodic (annual/biennial)",
    "Targeted / Trigger-based",
    "Vendor Model Review",
]

CHANGE_RELATED_VALIDATION_TYPES = {
    "Material Model Change",
    "Non-material Model Change Review",
}

VALIDATION_OUTCOMES = ["Fit for Purpose", "Approved with Conditions", "Not Fit for Purpose"]

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
    "Documentation review",
]


# ---------------------------------------------------------------- primitives
def _read(filename: str):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _write(filename: str, data) -> None:
    with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    st.cache_data.clear()


def log_event(action: str, entity_type: str, entity_id: str, model_id: str, details: str) -> None:
    """Append an event to the platform audit trail (data/audit_log.json)."""
    user = auth.get_current_user()
    log = _read("audit_log.json")
    log.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": user["name"],
        "role": user["role"],
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "model_id": model_id,
        "details": details,
    })
    _write("audit_log.json", log)


def _update_model(model_id: str, mutate) -> dict:
    """Apply `mutate(model_dict)` to one model and persist models.json."""
    models = _read("models.json")
    target = None
    for m in models:
        if m["model_id"] == model_id:
            mutate(m)
            target = m
            break
    _write("models.json", models)
    return target


def _next_id(items: list[dict], key: str, prefix: str) -> str:
    nums = []
    for i in items:
        raw = i.get(key) or ""
        try:
            nums.append(int(str(raw).split("-")[-1]))
        except ValueError:
            continue
    return f"{prefix}-{max(nums or [0]) + 1:03d}"


def _all_change_ids() -> list[str]:
    ids = []
    for m in _read("models.json"):
        for c in m.get("change_log", []):
            if c.get("change_id"):
                ids.append(c["change_id"])
    return ids


def _all_audit_ids() -> list[str]:
    ids = []
    for m in _read("models.json"):
        for a in m.get("audit_reviews", []):
            if a.get("audit_id"):
                ids.append(a["audit_id"])
    return ids


def _next_prefixed_id(existing: list[str], prefix: str) -> str:
    nums = []
    for raw in existing:
        try:
            nums.append(int(str(raw).split("-")[-1]))
        except ValueError:
            continue
    return f"{prefix}-{max(nums or [0]) + 1:03d}"


def _read_requests() -> list[dict]:
    return _read(REQUESTS_FILE)


def _write_requests(requests: list[dict]) -> None:
    _write(REQUESTS_FILE, requests)


def get_request(request_id: str) -> dict | None:
    for r in _read_requests():
        if r["request_id"] == request_id:
            return r
    return None


def is_request_open(req: dict) -> bool:
    return req.get("status") in ("Open", "In Progress")


def peek_next_thread_id(request_id: str) -> str:
    """Stable id for the next thread entry (FND-001-R1, …)."""
    for r in _read_requests():
        if r["request_id"] == request_id:
            n = len(r.get("thread") or []) + 1
            return f"{request_id}-R{n}"
    return f"{request_id}-R1"


def _map_legacy_finding_id(issue_id: str) -> str:
    """Map legacy ISS-xxx / VFI-xxx ids to FND-xxx when present."""
    if issue_id.startswith("ISS-"):
        candidate = "FND-" + issue_id.split("-", 1)[1]
        if get_request(candidate):
            return candidate
        old = "VFI-" + issue_id.split("-", 1)[1]
        if get_request(old):
            return old
        return candidate
    if issue_id.startswith("VFI-"):
        candidate = "FND-" + issue_id.split("-", 1)[1]
        if get_request(candidate):
            return candidate
    return issue_id


# Legacy alias used by older callers / smoke tests
def peek_next_response_id(issue_id: str) -> str:
    mapped = _map_legacy_finding_id(issue_id)
    req = get_request(mapped) or get_request(issue_id)
    if req:
        return peek_next_thread_id(req["request_id"])
    return f"{mapped}-R1"


def _apply_validation_schedule(model_id: str, val_date_iso: str, outcome: str) -> None:
    val_date = date.fromisoformat(val_date_iso)

    def mutate(m):
        m["last_validation"] = val_date_iso
        freq_days = next(
            (d for f, d in FREQUENCY_DAYS.items() if m["validation_frequency"].startswith(f)), 365
        )
        m["next_validation_due"] = (val_date + timedelta(days=freq_days)).isoformat()
        m["last_review_date"] = val_date_iso
        if m.get("pending_revalidation") and outcome in (
            "Fit for Purpose", "Approved with Conditions",
        ):
            m["pending_revalidation"] = False
            m["status"] = (
                "In Production" if outcome == "Fit for Purpose"
                else "Approved with Conditions"
            )

    _update_model(model_id, mutate)


# ---------------------------------------------------------------- validation requests
def create_request(model_id: str, record: dict) -> str:
    """Create a typed validation request. Returns request_id (e.g. MC-002).

    `record` keys: type (MC|VAL|FND), title, description, assigned_to,
    optional materiality (MC), validation_subtype/nature (VAL),
    severity/remediation/due_date (FND), tests, status, outcome/closed_date.
    """
    user = auth.get_current_user()
    rtype = record["type"]
    if rtype not in auth.REQUEST_TYPES:
        raise ValueError(f"Unknown request type: {rtype}")

    requests = _read_requests()
    request_id = _next_id(requests, "request_id", rtype)
    status = record.get("status") or "Open"
    closed_date = record.get("closed_date")
    outcome = record.get("outcome")
    if status == "Closed" and not closed_date:
        closed_date = date.today().isoformat()

    req = {
        "request_id": request_id,
        "type": rtype,
        "model_id": model_id,
        "status": status,
        "initiated_by": user["name"],
        "initiated_by_role": user["role"],
        "assigned_to": record.get("assigned_to") or "",
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
        "legacy_id": record.get("legacy_id"),
        "thread": record.get("thread") or [],
    }
    requests.append(req)
    # Normalize thread response ids
    for i, entry in enumerate(req.get("thread") or [], start=1):
        if not entry.get("response_id") or str(entry["response_id"]).startswith("TEMP"):
            entry["response_id"] = f"{request_id}-R{i}"
    _write_requests(requests)

    material = (req.get("materiality") or "") == "Material"
    if status == "Closed" and outcome and (rtype == "VAL" or (rtype == "MC" and material)):
        _apply_validation_schedule(model_id, req["created_date"], outcome)

    log_event(
        f"initiate_{rtype.lower()}", "validation_request", request_id, model_id,
        f"{rtype} opened: {record['title'][:80]}",
    )
    return request_id


def assign_request(request_id: str, assigned_to: str, set_in_progress: bool = True) -> None:
    """Assign a request (send to validator / owner). Open → In Progress by default."""
    requests = _read_requests()
    model_id = ""
    for r in requests:
        if r["request_id"] == request_id:
            if r["status"] == "Closed":
                raise ValueError("Cannot assign a closed request")
            r["assigned_to"] = assigned_to
            if set_in_progress and r["status"] == "Open":
                r["status"] = "In Progress"
            model_id = r["model_id"]
            break
    _write_requests(requests)
    log_event(
        "assign_request", "validation_request", request_id, model_id,
        f"Assigned to {assigned_to}",
    )


def add_request_response(
    request_id: str,
    text: str,
    evidence_ids: list[str] | None = None,
) -> str:
    """Append a thread comment. Returns response_id. Closed requests reject writes."""
    user = auth.get_current_user()
    requests = _read_requests()
    model_id = ""
    response_id = peek_next_thread_id(request_id)
    for r in requests:
        if r["request_id"] == request_id:
            if r["status"] == "Closed":
                raise ValueError("Cannot comment on a closed request")
            n = len(r.get("thread") or []) + 1
            response_id = f"{request_id}-R{n}"
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
            model_id = r["model_id"]
            break
    _write_requests(requests)
    log_event(
        "respond_request", "validation_request", request_id, model_id,
        f"Response added: {text[:80]}",
    )
    return response_id


def close_request(
    request_id: str,
    comment: str,
    outcome: str | None = None,
    evidence_ids: list[str] | None = None,
    tests: list[str] | None = None,
) -> str:
    """Close a request with a closure comment (stored on the thread)."""
    user = auth.get_current_user()
    requests = _read_requests()
    model_id = ""
    response_id = peek_next_thread_id(request_id)
    rtype = ""
    material = False
    closed_outcome = ""
    for r in requests:
        if r["request_id"] == request_id:
            if r["status"] == "Closed":
                raise ValueError("Request already closed")
            n = len(r.get("thread") or []) + 1
            response_id = f"{request_id}-R{n}"
            r["status"] = "Closed"
            r["closed_date"] = date.today().isoformat()
            if outcome:
                r["outcome"] = outcome
            elif not r.get("outcome"):
                r["outcome"] = "Closed"
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
            model_id = r["model_id"]
            rtype = r["type"]
            material = (r.get("materiality") or "") == "Material"
            closed_outcome = r.get("outcome") or outcome or ""
            break
    _write_requests(requests)

    if closed_outcome and (rtype == "VAL" or (rtype == "MC" and material)):
        _apply_validation_schedule(model_id, date.today().isoformat(), closed_outcome)

    log_event(
        "close_request", "validation_request", request_id, model_id,
        f"Closed ({outcome or 'n/a'}): {comment[:80]}",
    )
    return response_id


# ---------------------------------------------------------------- legacy validation / issue wrappers
def add_validation(model_id: str, record: dict) -> str:
    """Compatibility: record a completed VAL (or MC) as a Closed request.

    `record`: date, type, outcome, validator, tests, summary.
    Returns the new request_id (VAL-xxx / MC-xxx).
    """
    raw_type = record.get("type", "Periodic")
    if raw_type in ("Material Model Change",) or raw_type == "Material":
        rtype, subtype, materiality = "MC", None, "Material"
        title = "Material Model Change"
    elif raw_type in ("Non-material Model Change Review", "Non-material"):
        rtype, subtype, materiality = "MC", None, "Non-material"
        title = "Non-material Model Change"
    else:
        rtype, subtype, materiality = "VAL", raw_type, None
        title = raw_type

    rid = create_request(model_id, {
        "type": rtype,
        "title": title,
        "description": record.get("summary") or "",
        "assigned_to": record.get("validator") or "",
        "status": "Closed",
        "created_date": record.get("date") or date.today().isoformat(),
        "closed_date": record.get("date") or date.today().isoformat(),
        "outcome": record.get("outcome"),
        "materiality": materiality,
        "validation_subtype": subtype,
        "tests": record.get("tests") or [],
        "source": "Validation",
        "thread": [{
            "response_id": "TEMP-R1",
            "date": record.get("date") or date.today().isoformat(),
            "author": (record.get("validator") or auth.get_current_user()["name"]).split(" (")[0],
            "role": "LOD2",
            "text": record.get("summary") or "",
            "evidence_ids": [],
        }],
    })
    # Fix temp response id
    requests = _read_requests()
    for r in requests:
        if r["request_id"] == rid and r.get("thread"):
            r["thread"][0]["response_id"] = f"{rid}-R1"
    _write_requests(requests)
    log_event(
        "add_validation", "validation_request", rid, model_id,
        f"{raw_type} validation recorded — outcome: {record.get('outcome')}",
    )
    return rid


def add_issue(issue: dict) -> str:
    """Compatibility: raise a Finding. Returns request_id (FND-xxx)."""
    user = auth.get_current_user()
    source = issue.get(
        "source",
        "Validation" if user["role"] == "LOD2" else "Internal Audit",
    )
    rid = create_request(issue["model_id"], {
        "type": "FND",
        "title": issue["title"],
        "description": issue["description"],
        "assigned_to": issue.get("owner") or "",
        "severity": issue.get("severity"),
        "remediation": issue.get("remediation"),
        "due_date": issue.get("due_date"),
        "source": source,
        "status": "Open",
    })
    log_event(
        "raise_issue", "validation_request", rid, issue["model_id"],
        f"Finding raised ({issue.get('severity')}): {issue['title']}",
    )
    return rid


def add_issue_response(issue_id: str, text: str, evidence_ids: list[str] | None = None) -> str:
    """Compatibility wrapper → add_request_response."""
    rid = _map_legacy_finding_id(issue_id)
    if not get_request(rid):
        rid = issue_id
    response_id = add_request_response(rid, text, evidence_ids)
    log_event(
        "respond_issue", "validation_request", rid,
        get_request(rid)["model_id"] if get_request(rid) else "",
        f"Response added: {text[:80]}",
    )
    return response_id


def close_issue(
    issue_id: str,
    comment: str,
    evidence_ids: list[str] | None = None,
) -> str:
    """Compatibility wrapper → close_request."""
    rid = _map_legacy_finding_id(issue_id)
    if not get_request(rid):
        rid = issue_id
    response_id = close_request(rid, comment, outcome="Closed", evidence_ids=evidence_ids)
    log_event(
        "close_issue", "validation_request", rid,
        get_request(rid)["model_id"] if get_request(rid) else "",
        f"Finding closed: {comment[:80]}",
    )
    return response_id


# ---------------------------------------------------------------- model changes
def add_change_entry(model_id: str, entry: dict) -> str:
    """Append a change-log entry. Material changes push the model into
    'In Validation' pending independent revalidation and open an MC request.
    Non-material changes open an MC notification (materiality=Non-material).

    `entry`: date, version, description, author, classification, justification.
    Returns the new change_id (e.g. CHG-026).
    """
    material = entry.get("classification") == "Material"
    change_id = _next_prefixed_id(_all_change_ids(), "CHG")
    entry = {**entry, "change_id": change_id}

    def mutate(m):
        m["change_log"].append(entry)
        m["version"] = entry["version"]
        if material:
            m["status"] = "In Validation"
            m["pending_revalidation"] = True

    _update_model(model_id, mutate)

    default_assignee = "Hassan Al-Mohannadi (Model Validation Unit)"
    models = _read("models.json")
    for m in models:
        if m["model_id"] == model_id and m.get("validator"):
            default_assignee = m["validator"]
            break
    create_request(model_id, {
        "type": "MC",
        "title": f"{'Material' if material else 'Non-material'} change v{entry['version']}",
        "description": (
            f"{entry.get('description', '')}\n\n"
            f"Justification: {entry.get('justification', '')}"
        ),
        "assigned_to": default_assignee,
        "status": "In Progress" if material else "Open",
        "materiality": "Material" if material else "Non-material",
        "source": "Model Change",
    })

    log_event(
        "record_change", "change", change_id, model_id,
        f"{entry.get('classification', 'Unclassified')} change to v{entry['version']}: "
        f"{entry['description'][:80]}"
        + (" — status set to In Validation pending revalidation" if material else ""),
    )
    return change_id


# ---------------------------------------------------------------- audit reviews
def add_audit_review(model_id: str, review: dict) -> str:
    """`review`: date, auditor, rating, scope. Returns the new audit_id."""
    audit_id = _next_prefixed_id(_all_audit_ids(), "AUD")
    review = {**review, "audit_id": audit_id}
    _update_model(model_id, lambda m: m["audit_reviews"].append(review))
    log_event("record_audit", "audit_review", audit_id, model_id,
              f"Internal audit review recorded — rating: {review['rating']}")
    return audit_id


# ---------------------------------------------------------------- evidence
def register_evidence(
    model_id: str,
    linked_type: str,
    linked_id: str,
    filename: str,
    file_bytes: bytes,
    category: str,
    description: str,
) -> str:
    """Save an uploaded file under data/evidence/<model_id>/ and register it.
    Returns the new evidence_id."""
    # Normalize legacy link types
    if linked_type == "validation":
        linked_type = "validation_request"
    elif linked_type == "issue":
        linked_type = "validation_request"
    elif linked_type == "issue_response":
        linked_type = "request_response"

    if linked_type not in EVIDENCE_LINK_TYPES:
        raise ValueError(f"Unknown evidence linked_type: {linked_type}")

    # Block uploads against closed validation requests
    if linked_type == "validation_request":
        req = get_request(linked_id)
        if req and req.get("status") == "Closed":
            raise ValueError("Cannot attach evidence to a closed request")

    user = auth.get_current_user()
    folder = EVIDENCE_DIR / model_id
    folder.mkdir(parents=True, exist_ok=True)
    stamped = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    stored = folder / stamped
    stored.write_bytes(file_bytes)

    registry = _read("evidence.json")
    evidence_id = _next_id(registry, "evidence_id", "EV")
    registry.append({
        "evidence_id": evidence_id,
        "model_id": model_id,
        "linked_type": linked_type,
        "linked_id": linked_id,
        "filename": filename,
        "stored_path": f"data/evidence/{model_id}/{stamped}",
        "category": category,
        "description": description,
        "uploaded_by": user["name"],
        "role": user["role"],
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    })
    _write("evidence.json", registry)
    log_event("upload_evidence", "evidence", evidence_id, model_id,
              f"Evidence uploaded ({category}): {filename} — {description[:60]}")
    return evidence_id


def attach_evidence(
    model_id: str,
    linked_type: str,
    linked_id: str,
    file,
    category: str,
    description: str,
    user=None,  # noqa: ARG001 — reserved; identity always from auth.get_current_user()
) -> str:
    """Attach an uploaded file to a workflow entity in context.

    `file` is a Streamlit UploadedFile (or any object with `.name` and
    `.getvalue()`). Returns the new evidence_id.
    """
    del user  # identity comes from the auth session
    return register_evidence(
        model_id,
        linked_type,
        linked_id,
        file.name,
        file.getvalue(),
        category,
        description,
    )


def evidence_for(linked_type: str, linked_id: str, evidence: list[dict] | None = None) -> list[dict]:
    """Evidence rows linked to a specific entity."""
    rows = evidence if evidence is not None else _read("evidence.json")
    return [
        e for e in rows
        if e.get("linked_type") == linked_type and e.get("linked_id") == linked_id
    ]
