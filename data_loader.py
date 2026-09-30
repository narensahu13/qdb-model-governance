"""Read side of the platform. Pages load data only through these helpers.

Everything comes from the SQLite repository. Fields that could drift if typed
by hand are DERIVED here, never stored on the model record:
  * tier                 — from the tier scores (tiering engine)
  * validation_frequency — from the tier
  * approval_body        — from the tier (Management Risk Committee / CRO)
  * last_validation, last_rating, next_validation_due — from closed
    validation requests
"""

from datetime import date

import pandas as pd
import streamlit as st

import governance
import repository
from tiering import compute_tier

DUE_SOON_DAYS = governance.DUE_SOON_DAYS


def _enrich(model: dict, requests: list[dict]) -> dict:
    m = dict(model)
    tier = compute_tier(**m["tier_scores"])["tier"]
    m["tier"] = tier
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
def load_monitoring() -> pd.DataFrame:
    rows = repository.list_monitoring()
    cols = ["model_id", "metric", "period", "value", "amber_threshold",
            "red_threshold", "higher_is_better", "rag"]
    return pd.DataFrame(rows, columns=cols)


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
