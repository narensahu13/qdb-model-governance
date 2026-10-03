"""Read side of the platform. Pages load data only through these helpers.

Everything comes from the SQLite repository. Fields that could drift if typed
by hand are DERIVED here, never stored on the model record:
  * tier                 — from the confirmed tier scores (tiering engine),
                           or an override approved by the model sponsor
  * validation_frequency — from the tier
  * approval_body        — model owner and model sponsor (every tier)
  * last_validation, last_rating, next_validation_due — from closed
    validation requests
"""

from datetime import date

import pandas as pd
import streamlit as st

import governance
import kmpi as kmpi_rules
import repository
from tiering import compute_tier

DUE_SOON_DAYS = governance.DUE_SOON_DAYS


def _enrich(model: dict, requests: list[dict]) -> dict:
    m = dict(model)
    m["computed_tier"] = compute_tier(**m["tier_scores"])["tier"]
    tier = governance.effective_tier(m)
    m["tier"] = tier
    m["tier_confirmed"] = governance.tier_confirmed(m)
    m["validation_frequency"] = governance.validation_frequency(tier)
    m["approval_body"] = governance.approval_body(tier)
    m.update(governance.derive_validation_dates(tier, requests))
    m["last_review_date"] = m["last_validation"]
    return m


@st.cache_data
def load_validation_requests() -> list[dict]:
    """Unified validation workflow: MC / VAL / FND."""
    reqs = repository.list_requests()
    for r in reqs:
        r["outcome"] = governance.normalise_outcome(r.get("outcome"))
    return reqs


@st.cache_data
def load_models() -> list[dict]:
    reqs = load_validation_requests()
    by_model: dict[str, list[dict]] = {}
    for r in reqs:
        by_model.setdefault(r["model_id"], []).append(r)
    return [_enrich(m, by_model.get(m["model_id"], [])) for m in repository.list_models()]


@st.cache_data
def load_validations() -> pd.DataFrame:
    """Completed VAL / MC requests as a validation-history view."""
    rows = []
    for r in load_validation_requests():
        if r["type"] not in ("VAL", "MC"):
            continue
        if r.get("status") != "Closed" and not r.get("outcome"):
            if not (r["type"] == "MC" and r.get("materiality") == "Material"):
                continue
        vtype = r.get("validation_subtype")
        if not vtype:
            if r["type"] == "MC":
                mat = r.get("materiality") or "Material"
                vtype = (
                    "Material Model Change" if mat == "Material"
                    else "Non-material Model Change Review"
                )
            else:
                vtype = "Periodic"
        rows.append({
            "validation_id": r["request_id"],
            "model_id": r["model_id"],
            "date": r.get("closed_date") or r["created_date"],
            "type": vtype,
            "outcome": r.get("outcome") or ("In Progress" if r["status"] != "Closed" else "—"),
            "validator": r.get("assigned_to") or r.get("initiated_by"),
            "tests": r.get("tests") or [],
            "summary": r.get("description") or "",
            "status": r["status"],
            "materiality": r.get("materiality"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=[
            "validation_id", "model_id", "date", "type", "outcome",
            "validator", "tests", "summary", "status", "materiality",
        ])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date", ascending=False)


@st.cache_data
def load_issues() -> pd.DataFrame:
    """Findings (FND) as the bank-wide findings view (dashboard & tracker)."""
    rows = []
    today = pd.Timestamp(date.today())
    for r in load_validation_requests():
        if r["type"] != "FND":
            continue
        status = r["status"]
        due = r.get("due_date")
        due_ts = pd.to_datetime(due) if due else pd.NaT
        if status != "Closed" and pd.notna(due_ts) and due_ts < today:
            display_status = "Overdue"
        elif status == "Closed":
            display_status = "Closed"
        else:
            display_status = "Open"
        rows.append({
            "issue_id": r["request_id"],
            "model_id": r["model_id"],
            "severity": r.get("severity") or "Medium",
            "title": r["title"],
            "description": r.get("description") or "",
            "remediation": r.get("remediation") or "",
            "owner": r.get("assigned_to") or "",
            "source": r.get("source") or "Validation",
            "raised_date": r["created_date"],
            "due_date": due,
            "status": display_status,
            "closed_date": r.get("closed_date"),
            "raised_by": r.get("initiated_by"),
            "raised_by_role": r.get("initiated_by_role"),
            "responses": r.get("thread") or [],
            "request_type": "FND",
            "workflow_status": r["status"],
        })
    cols = [
        "issue_id", "model_id", "severity", "title", "description", "remediation",
        "owner", "source", "raised_date", "due_date", "status", "closed_date",
        "raised_by", "raised_by_role", "responses", "request_type", "workflow_status",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for col in ("raised_date", "due_date", "closed_date"):
        df[col] = pd.to_datetime(df[col])
    return df


@st.cache_data
def load_tools() -> list[dict]:
    """EUC tools, AI tools and 'not a model' decisions (identification register)."""
    return repository.list_tools()


def ai_register() -> list[dict]:
    """Every AI system — models and tools — for the QCB AI Guideline register."""
    rows = []
    for m in load_models():
        if m.get("ai_system"):
            rows.append({"kind": "Model", "id": m["model_id"], "name": m["name"],
                         "owner": m["owner"], "source": m["source"], "vendor": m.get("vendor"),
                         "status": m["status"], **{k: m.get(k) for k in AI_FIELDS}})
    for t in load_tools():
        if t.get("ai_system"):
            rows.append({"kind": t["classification"], "id": t["tool_id"], "name": t["name"],
                         "owner": t["owner"], "source": t.get("platform"), "vendor": None,
                         "status": "In use", **{k: t.get(k) for k in AI_FIELDS}})
    for r in rows:
        r["qcb_approval_required"] = governance.qcb_approval_required(r)
    return rows


AI_FIELDS = ["qcb_ai_high_risk", "ai_functional_category", "ai_provider_role",
             "ai_autonomy", "qcb_approval_status", "ai_system"]


@st.cache_data
def load_kmpis() -> list[dict]:
    return repository.list_kmpis()


@st.cache_data
def load_kmpi_returns() -> list[dict]:
    return repository.list_kmpi_returns()


def kmpis_for(model_id: str, active_only: bool = False) -> list[dict]:
    return [k for k in load_kmpis() if k["model_id"] == model_id
            and (k.get("active", True) or not active_only)]


def kmpi_return(model_id: str, period: str) -> dict | None:
    return next((r for r in load_kmpi_returns()
                 if r["model_id"] == model_id and r["period"] == period), None)


MONITORING_COLUMNS = ["model_id", "kmpi_id", "metric", "period", "value", "rag", "status",
                      "direction", "amber", "red", "unit"]


@st.cache_data
def load_monitoring() -> pd.DataFrame:
    """Reported KMPI values (submitted or reviewed returns), one row per KMPI per period."""
    rows = []
    for r in load_kmpi_returns():
        if r["status"] not in kmpi_rules.DONE:
            continue
        for kid, v in r["values"].items():
            rows.append({"model_id": r["model_id"], "kmpi_id": kid, "metric": v["name"],
                         "period": r["period"], "value": v["value"], "rag": v["rag"],
                         "status": r["status"], "direction": v["direction"], "amber": v["amber"],
                         "red": v["red"], "unit": v.get("unit")})
    return pd.DataFrame(rows, columns=MONITORING_COLUMNS)


def needs_kmpi_return(model: dict, period: str) -> bool:
    """A model in use reports every KMPI due in the period."""
    return model["status"] in governance.IN_USE_STATUSES and bool(
        kmpi_rules.due_kmpis(kmpis_for(model["model_id"]), period))


def kmpi_overview(period: str, today: date | None = None) -> list[dict]:
    """One row per model that reports for the period: status, due date, RAG counts."""
    rows = []
    for m in load_models():
        if not needs_kmpi_return(m, period):
            continue
        ret = kmpi_return(m["model_id"], period)
        status = kmpi_rules.return_status(ret)
        rags = [v["rag"] for v in (ret or {}).get("values", {}).values()] if status in kmpi_rules.DONE else []
        rows.append({
            "model_id": m["model_id"], "name": m["name"], "tier": m["tier"], "owner": m["owner"],
            "validator": m["validator"], "status": status,
            "due": kmpi_rules.due_date(period).isoformat(),
            "overdue": kmpi_rules.is_overdue(ret, period, today),
            "kmpis_due": len(kmpi_rules.due_kmpis(kmpis_for(m["model_id"]), period)),
            "green": rags.count(kmpi_rules.GREEN), "amber": rags.count(kmpi_rules.AMBER),
            "red": rags.count(kmpi_rules.RED), "worst": kmpi_rules.worst(rags),
            "submitted_by": (ret or {}).get("submitted_by"), "reviewed_by": (ret or {}).get("reviewed_by"),
            "finding_id": (ret or {}).get("finding_id"),
        })
    return rows


def latest_kmpi_position(model_id: str) -> dict | None:
    """The most recent submitted or reviewed return of a model, with its worst RAG."""
    done = [r for r in load_kmpi_returns() if r["model_id"] == model_id and r["status"] in kmpi_rules.DONE]
    if not done:
        return None
    r = max(done, key=lambda x: x["period"])
    return {"period": r["period"], "status": r["status"],
            "worst": kmpi_rules.worst(v["rag"] for v in r["values"].values()),
            "red": [f"{k} {v['name']}" for k, v in r["values"].items() if v["rag"] == kmpi_rules.RED],
            "amber": [f"{k} {v['name']}" for k, v in r["values"].items() if v["rag"] == kmpi_rules.AMBER]}


@st.cache_data
def load_evidence() -> list[dict]:
    return repository.list_evidence()


@st.cache_data
def load_audit_log() -> list[dict]:
    return repository.list_audit()


def validation_status(model: dict) -> str:
    """On Track / Due Soon / Overdue / Never Validated / Pre-implementation."""
    return governance.validation_status(model)


def models_dataframe() -> pd.DataFrame:
    """Flat inventory view with derived governance fields."""
    models = load_models()
    issues = load_issues()
    evidence = load_evidence()

    rows = []
    for m in models:
        model_issues = issues[issues["model_id"] == m["model_id"]]
        open_issues = model_issues[model_issues["status"] != "Closed"]
        docs = documentation_status(m, evidence)
        rows.append({
            "Model ID": m["model_id"],
            "Model Name": m["name"],
            "Risk Type": m["risk_type"],
            "Tier": m["tier"],
            "Tier Confirmed": m["tier_confirmed"],
            "Status": m["status"],
            "Owner": m["owner"],
            "Validator": m["validator"],
            "Source": m["source"],
            "Category": m["category"],
            "Methodology": m["methodology"],
            "Last Validation": m["last_validation"] or "-",
            "Last Rating": m["last_rating"] or "-",
            "Next Validation Due": m["next_validation_due"] or "-",
            "Validation Status": validation_status(m),
            "Open Issues": len(open_issues),
            "High Open Issues": int((open_issues["severity"] == "High").sum()),
            "Overdue Issues": int((open_issues["status"] == "Overdue").sum()),
            "Doc Completeness (%)": round(100 * sum(docs.values()) / len(docs)) if docs else 0,
            "AI System": bool(m.get("ai_system")),
            "Latest KMPI": (latest_kmpi_position(m["model_id"]) or {}).get("worst") or "-",
        })
    return pd.DataFrame(rows)


def documentation_status(model: dict, evidence: list[dict] | None = None) -> dict:
    """Checklist item -> in place? An item counts as in place when it was
    recorded as existing on the model record, or a document of that type has
    been uploaded to the model."""
    evidence = load_evidence() if evidence is None else evidence
    uploaded = {
        e.get("doc_type") for e in evidence
        if e["model_id"] == model["model_id"] and e.get("doc_type")
    }
    return {d: bool(ok) or d in uploaded for d, ok in model["documentation"].items()}


def get_model(model_id: str) -> dict | None:
    for m in load_models():
        if m["model_id"] == model_id:
            return m
    return None


def requests_for_model(model_id: str) -> list[dict]:
    return [r for r in load_validation_requests() if r["model_id"] == model_id]


def factsheet_pdf(model_id: str) -> bytes:
    """One-page PDF factsheet for a model, built from live data."""
    import factsheet

    m = get_model(model_id)
    mon = load_monitoring()
    mon = mon[mon["model_id"] == model_id].to_dict("records")
    return factsheet.build_factsheet(
        m, requests_for_model(model_id), mon, documentation_status(m), validation_status(m),
    )


# ================================================================ Phase 2 — task inbox
def _task(kind, model, title, detail="", due=None, request_id=None):
    return {"kind": kind, "model_id": model["model_id"], "model_name": model["name"],
            "title": title, "detail": detail, "due": due, "request_id": request_id}


def g2_missing_docs(model: dict) -> list[str]:
    docs = documentation_status(model)
    return [d for d in governance.G2_REQUIRED_DOCS[model["tier"]] if not docs.get(d)]


def tasks_for(user: dict) -> list[dict]:
    """Everything waiting on this person, across all models."""
    from datetime import timedelta

    name, role = user["name"], user["role"]
    models = {m["model_id"]: m for m in load_models()}
    reqs = load_validation_requests()
    tasks: list[dict] = []
    mine = lambda m: governance.is_owner_or_developer(m, name)  # noqa: E731

    for r in reqs:
        m = models.get(r["model_id"])
        if m is None or r["status"] == "Closed":
            continue
        eng = r.get("engagement")
        assignee = governance.person_name(r.get("assigned_to"))
        if eng:
            stage = eng["stage"]
            if role == "LOD1":
                for ir in eng.get("info_requests", []):
                    if ir["status"] == "Open" and (governance.person_name(ir["owner"]) == name or mine(m)):
                        tasks.append(_task("Information request", m, f"{ir['ir_id']}: {ir['item']}",
                                           ir.get("review_comment") or "", ir.get("due"), r["request_id"]))
                if stage == "Owner review" and mine(m) and not eng.get("owner_review"):
                    due = (date.fromisoformat(eng["draft"]["issued_on"])
                           + timedelta(days=governance.OWNER_REVIEW_DAYS)).isoformat()
                    tasks.append(_task("Factual-accuracy review", m, f"Review the draft report ({r['request_id']})",
                                       f"Proposed rating: {eng['draft']['rating']}", due, r["request_id"]))
            if role == "LOD2":
                if not assignee and not governance.independence_conflict(m, name, r["type"]):
                    tasks.append(_task("Unassigned validation", m, f"{r['request_id']} {r['title']}",
                                       "Start it to take it on", None, r["request_id"]))
                elif assignee == name:
                    answered = [ir["ir_id"] for ir in eng.get("info_requests", []) if ir["status"] == "Answered"]
                    if stage == "Scoping":
                        tasks.append(_task("Validation", m, f"Scope {r['request_id']} and declare independence",
                                           r["title"], None, r["request_id"]))
                    elif stage == "Fieldwork" and not governance.engagement_can_issue_draft(eng):
                        tasks.append(_task("Validation", m, f"Issue the draft report for {r['request_id']}",
                                           f"Answers received: {', '.join(answered) or 'none needed'}",
                                           None, r["request_id"]))
                    elif stage == "Owner review" and not governance.engagement_can_sign_off(eng):
                        tasks.append(_task("Validation", m, f"Sign off {r['request_id']} (G3)",
                                           "Owner review done or lapsed", None, r["request_id"]))
        elif r["type"] == "FND":
            if role == "LOD1" and assignee == name:
                tasks.append(_task("Finding", m, f"{r['request_id']} {r['title']}",
                                   f"Severity {r.get('severity')}", r.get("due_date"), r["request_id"]))
            if role in ("LOD2", "LOD3") and r.get("initiated_by") == name:
                last = (r.get("thread") or [{}])[-1]
                if last.get("author") and last["author"] != name:
                    tasks.append(_task("Finding response", m, f"Review the response on {r['request_id']}",
                                       r["title"], r.get("due_date"), r["request_id"]))
        elif r["type"] == "MC" and role == "LOD2" and assignee == name:
            tasks.append(_task("Model change", m, f"Review {r['request_id']} (non-material)",
                               r["title"], None, r["request_id"]))

    for m in models.values():
        ta = m.get("tier_assessment") or {}
        if ta.get("status") == governance.TIER_PROPOSED and role in ("LOD2", "ADMIN") \
                and ta.get("proposed_by") != name:
            tasks.append(_task("Tier sign-off", m, "Confirm the proposed tier (G1)",
                               f"Proposed by {ta.get('proposed_by')}"))
        if ta.get("status") == governance.TIER_OVERRIDE_PENDING and role == "SPONSOR" \
                and governance.person_name(m.get("sponsor")) == name:
            tasks.append(_task("Tier override", m, f"Decide on the override to Tier {ta['override_tier']}",
                               ta.get("override_reason") or ""))
        if m["status"] == "In Development" and role == "LOD1" and mine(m) and m["tier_confirmed"]:
            missing = g2_missing_docs(m)
            tasks.append(_task("Submit for validation", m,
                               "Upload documents for G2" if missing else "Submit for validation (G2)",
                               ("Missing: " + ", ".join(missing)) if missing else "Required documents in place"))
        signer = governance.next_approver(m)
        if signer and governance.approver_name(m, signer) == name and role in ("LOD1", "SPONSOR"):
            owner_sig = next((s for s in (m.get("pending_approval") or {}).get("signatures", [])), None)
            tasks.append(_task("Approval", m, f"Approve as {signer.lower()} (G4)",
                               f"Validation rating {m.get('last_rating')}"
                               + (f"; owner: {owner_sig['decision']}" if owner_sig else "")))
        if m["status"] == governance.STATUS_AWAITING_IMPLEMENTATION and role == "LOD2" \
                and not governance.independence_conflict(m, name, "VAL") \
                and governance.person_name(m.get("validator")) in (name, "Not yet assigned", ""):
            tasks.append(_task("Implementation", m, "Verify implementation (G5)", f"Version {m['version']}"))
        for ap in m.get("approvals") or []:
            for c in ap.get("conditions", []):
                if c["status"] == governance.CONDITION_OPEN and role == "LOD1" and (
                        mine(m) or governance.person_name(c.get("owner")) == name):
                    tasks.append(_task("Condition of approval", m, c["condition"], ap["approval_id"], c.get("due")))
                if c["status"] == governance.CONDITION_MET and role == "LOD2" and not mine(m) \
                        and governance.person_name(m.get("validator")) == name:
                    tasks.append(_task("Condition to verify", m, c["condition"], c.get("note") or "", c.get("due")))
        if role == "ADMIN" and m["status"] not in ("Retired",) and m.get("validator") in (None, "", "Not yet assigned") \
                and m["status"] != "In Development":
            tasks.append(_task("Assignment", m, "Assign a validator", m["status"]))

    # ---- KMPI returns for the reporting period (and any earlier one still open)
    period = kmpi_rules.reporting_period()
    open_returns = {(r["model_id"], r["period"]) for r in load_kmpi_returns()
                    if r["status"] != kmpi_rules.REVIEWED}
    for m in models.values():
        periods = {period} | {p for mid, p in open_returns if mid == m["model_id"]}
        for p in sorted(periods):
            if not needs_kmpi_return(m, p):
                continue
            ret = kmpi_return(m["model_id"], p)
            status = kmpi_rules.return_status(ret)
            due = kmpi_rules.due_date(p).isoformat()
            if role == "LOD1" and mine(m) and status in kmpi_rules.EDITABLE:
                last = (ret or {}).get("history", [{}])[-1] if ret else {}
                tasks.append(_task("KMPI return", m,
                                   f"{'Correct and resubmit' if status == kmpi_rules.RETURNED else 'Enter and submit'} "
                                   f"the {p} KMPIs",
                                   (f"Sent back: {last.get('comment')}" if status == kmpi_rules.RETURNED
                                    else f"{status} — {len(kmpi_rules.due_kmpis(kmpis_for(m['model_id']), p))} KMPIs"),
                                   due))
            if role == "LOD2" and status == kmpi_rules.SUBMITTED and not mine(m) and (
                    governance.person_name(m.get("validator")) == name
                    or governance.person_name(m.get("validator")) in ("Not yet assigned", "")):
                rags = [v["rag"] for v in ret["values"].values()]
                tasks.append(_task("KMPI review", m, f"Review the {p} KMPI return",
                                   f"{rags.count('Red')} red, {rags.count('Amber')} amber — "
                                   f"submitted by {governance.person_name(ret.get('submitted_by'))}", due))

    today = date.today().isoformat()
    for t in tasks:
        t["overdue"] = bool(t["due"] and t["due"] < today)
    tasks.sort(key=lambda t: (not t["overdue"], t["due"] or "9999", t["model_id"]))
    return tasks
