"""Central data access layer. All pages load data through these helpers so the
mock JSON/CSV files in data/ can later be swapped for a database or a real
inventory extract without touching page code."""

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from tiering import compute_tier

DATA_DIR = Path(__file__).resolve().parent / "data"

DUE_SOON_DAYS = 90


@st.cache_data
def load_models() -> list[dict]:
    with open(DATA_DIR / "models.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_validation_requests() -> list[dict]:
    """Unified validation workflow: MMC / NMMC / VAL / VRQ / VFI."""
    path = DATA_DIR / "validation_requests.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_validations() -> pd.DataFrame:
    """Completed VAL / MMC / NMMC requests as a validation-history view."""
    rows = []
    for r in load_validation_requests():
        if r["type"] not in ("VAL", "MMC", "NMMC"):
            continue
        if r.get("status") != "Closed" and not r.get("outcome"):
            # Include in-progress MMC that already has an interim outcome label
            if r["type"] != "MMC":
                continue
        vtype = r.get("validation_subtype")
        if not vtype:
            vtype = {
                "MMC": "Material Model Change",
                "NMMC": "Non-material Model Change Review",
                "VAL": "Periodic (annual/biennial)",
            }.get(r["type"], r["type"])
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
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=[
            "validation_id", "model_id", "date", "type", "outcome",
            "validator", "tests", "summary", "status",
        ])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date", ascending=False)


@st.cache_data
def load_issues() -> pd.DataFrame:
    """VFI findings as the bank-wide issues/findings view (for dashboard & tracker)."""
    rows = []
    today = pd.Timestamp(date.today())
    for r in load_validation_requests():
        if r["type"] != "VFI":
            continue
        status = r["status"]
        due = r.get("due_date")
        due_ts = pd.to_datetime(due) if due else pd.NaT
        if status != "Closed" and pd.notna(due_ts) and due_ts < today:
            display_status = "Overdue"
        elif status == "Closed":
            display_status = "Closed"
        elif status == "In Progress":
            display_status = "Open"
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
            "request_type": "VFI",
            "workflow_status": r["status"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=[
            "issue_id", "model_id", "severity", "title", "description", "remediation",
            "owner", "source", "raised_date", "due_date", "status", "closed_date",
            "raised_by", "raised_by_role", "responses", "request_type", "workflow_status",
        ])
    for col in ("raised_date", "due_date", "closed_date"):
        df[col] = pd.to_datetime(df[col])
    return df


@st.cache_data
def load_monitoring() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "monitoring.csv")


@st.cache_data
def load_evidence() -> list[dict]:
    with open(DATA_DIR / "evidence.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_audit_log() -> list[dict]:
    with open(DATA_DIR / "audit_log.json", encoding="utf-8") as f:
        return json.load(f)


def validation_status(model: dict) -> str:
    """On Track / Due Soon / Overdue / Never Validated for a model record."""
    if model["last_validation"] is None:
        return "Never Validated"
    due = model.get("next_validation_due")
    if due is None:
        return "On Track"
    due_date = date.fromisoformat(due)
    today = date.today()
    if due_date < today:
        return "Overdue"
    if due_date <= today + timedelta(days=DUE_SOON_DAYS):
        return "Due Soon"
    return "On Track"


def models_dataframe() -> pd.DataFrame:
    """Flat inventory view with derived governance fields."""
    models = load_models()
    issues = load_issues()

    rows = []
    for m in models:
        model_issues = issues[issues["model_id"] == m["model_id"]]
        open_issues = model_issues[model_issues["status"] != "Closed"]
        docs = m["documentation"]
        rows.append({
            "Model ID": m["model_id"],
            "Model Name": m["name"],
            "Risk Type": m["risk_type"],
            # Tier is computed from tier_scores by the tiering engine, not read
            # from the manually entered field (reconciled: computed == stored).
            "Tier": compute_tier(**m["tier_scores"])["tier"],
            "Status": m["status"],
            "Owner": m["owner"],
            "Validator": m["validator"],
            "Source": m["source"],
            "Category": m["category"],
            "Methodology": m["methodology"],
            "Last Validation": m["last_validation"] or "-",
            "Next Validation Due": m["next_validation_due"] or "-",
            "Validation Status": validation_status(m),
            "Open Issues": len(open_issues),
            "High Open Issues": int((open_issues["severity"] == "High").sum()),
            "Overdue Issues": int((open_issues["status"] == "Overdue").sum()),
            "Doc Completeness (%)": round(100 * sum(docs.values()) / len(docs)),
        })
    return pd.DataFrame(rows)


def get_model(model_id: str) -> dict | None:
    for m in load_models():
        if m["model_id"] == model_id:
            return m
    return None


def requests_for_model(model_id: str) -> list[dict]:
    return [r for r in load_validation_requests() if r["model_id"] == model_id]
