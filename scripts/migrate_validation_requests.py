"""Rebuild data/validation_requests.json from historical validations.json +
issues.json using the simplified 3-type taxonomy (MC / VAL / FND).

Normally not needed — seed data is already migrated. Re-run only if regenerating
from archives.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TYPE_LABELS = {
    "MC": "Model Change",
    "VAL": "Validation",
    "FND": "Finding",
}


def classify_validation(vtype: str) -> tuple[str, str | None, str | None]:
    """Return (type, materiality, validation_subtype)."""
    if vtype == "Material Model Change":
        return "MC", "Material", None
    if vtype == "Non-material Model Change Review":
        return "MC", "Non-material", None
    # Light nature labels
    if vtype.startswith("Initial"):
        return "VAL", None, "Initial"
    if vtype.startswith("Periodic"):
        return "VAL", None, "Periodic"
    if "Targeted" in vtype or "Trigger" in vtype:
        return "VAL", None, "Targeted"
    if "Vendor" in vtype:
        return "VAL", None, "Targeted"
    return "VAL", None, vtype or "Periodic"


def main() -> None:
    vals = json.loads((DATA / "validations.json").read_text(encoding="utf-8"))
    issues = json.loads((DATA / "issues.json").read_text(encoding="utf-8"))

    counters = {"MC": 0, "VAL": 0, "FND": 0}

    def next_id(code: str) -> str:
        counters[code] += 1
        return f"{code}-{counters[code]:03d}"

    out: list[dict] = []

    for v in vals:
        legacy = v.get("validation_id") or f"VAL-legacy-{v['model_id']}-{v['date']}"
        code, materiality, subtype = classify_validation(v.get("type") or "")
        awaiting = "awaiting" in (v.get("summary") or "").lower() or v.get("outcome") in (
            None, "", "In Progress",
        )
        status = "In Progress" if code == "MC" and materiality == "Material" and awaiting else "Closed"
        if status == "Closed" and not v.get("outcome"):
            status = "In Progress"

        rid = next_id(code)
        title = (
            "Material Model Change" if code == "MC" and materiality == "Material"
            else "Non-material Model Change" if code == "MC"
            else (subtype or "Validation")
        )
        thread = []
        if v.get("summary"):
            thread.append({
                "response_id": f"{rid}-R1",
                "date": v["date"],
                "author": (v.get("validator") or "MVU").split(" (")[0],
                "role": "LOD2",
                "text": v["summary"],
                "evidence_ids": [],
            })
        out.append({
            "request_id": rid,
            "type": code,
            "model_id": v["model_id"],
            "status": status,
            "initiated_by": (v.get("validator") or "Hassan Al-Mohannadi").split(" (")[0],
            "initiated_by_role": "LOD2",
            "assigned_to": v.get("validator") or "",
            "title": title,
            "description": v.get("summary") or "",
            "created_date": v["date"],
            "closed_date": v["date"] if status == "Closed" else None,
            "due_date": None,
            "outcome": v.get("outcome") if status == "Closed" else None,
            "severity": None,
            "remediation": None,
            "source": "Validation",
            "materiality": materiality,
            "validation_subtype": subtype,
            "tests": v.get("tests") or [],
            "legacy_id": legacy,
            "thread": thread,
        })

    for iss in issues:
        raw = iss.get("issue_id") or ""
        try:
            num = int(raw.split("-")[-1])
            rid = f"FND-{num:03d}"
            counters["FND"] = max(counters["FND"], num)
        except ValueError:
            rid = next_id("FND")

        thread = []
        for i, resp in enumerate(iss.get("responses") or [], start=1):
            thread.append({
                "response_id": f"{rid}-R{i}",
                "date": resp.get("date"),
                "author": resp.get("author"),
                "role": resp.get("role") or "LOD1",
                "text": resp.get("text") or "",
                "evidence_ids": resp.get("evidence_ids") or [],
            })

        status = "Closed" if iss.get("status") == "Closed" else (
            "In Progress" if thread else "Open"
        )
        out.append({
            "request_id": rid,
            "type": "FND",
            "model_id": iss["model_id"],
            "status": status if status != "Overdue" else "Open",
            "initiated_by": iss.get("raised_by") or "Hassan Al-Mohannadi",
            "initiated_by_role": iss.get("raised_by_role") or "LOD2",
            "assigned_to": iss.get("owner") or "",
            "title": iss["title"],
            "description": iss.get("description") or "",
            "created_date": iss.get("raised_date"),
            "closed_date": iss.get("closed_date"),
            "due_date": iss.get("due_date"),
            "outcome": "Closed" if status == "Closed" else None,
            "severity": iss.get("severity"),
            "remediation": iss.get("remediation"),
            "source": iss.get("source") or "Validation",
            "materiality": None,
            "validation_subtype": None,
            "tests": [],
            "legacy_id": raw,
            "thread": thread,
        })

    # Demo LoD1-initiated validation request
    rid = next_id("VAL")
    out.append({
        "request_id": rid,
        "type": "VAL",
        "model_id": "QDB-IF-005",
        "status": "In Progress",
        "initiated_by": "Fatima Al-Sulaiti",
        "initiated_by_role": "LOD1",
        "assigned_to": "Hassan Al-Mohannadi (Model Validation Unit)",
        "title": "Request independent validation of macro scenario model",
        "description": (
            "LoD1 requests MVU to commission independent validation of QDB-IF-005 "
            "before MRC conditional approval. Methodology documented and weights frozen."
        ),
        "created_date": "2026-03-10",
        "closed_date": None,
        "due_date": "2026-09-30",
        "outcome": None,
        "severity": None,
        "remediation": None,
        "source": "LoD1 Request",
        "materiality": None,
        "validation_subtype": "Ad-hoc",
        "tests": [],
        "legacy_id": None,
        "thread": [{
            "response_id": f"{rid}-R1",
            "date": "2026-03-12",
            "author": "Hassan Al-Mohannadi",
            "role": "LOD2",
            "text": "Accepted. External firm shortlist under review; kick-off targeted for Q3.",
            "evidence_ids": [],
        }],
    })

    type_order = {"MC": 0, "VAL": 1, "FND": 2}
    out.sort(key=lambda r: (type_order.get(r["type"], 9), r["request_id"]))

    path = DATA / "validation_requests.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from collections import Counter
    print(f"Wrote {len(out)} requests to {path.name}: {dict(Counter(r['type'] for r in out))}")
    for code in ("MC", "VAL", "FND"):
        print(f"  {code} ({TYPE_LABELS[code]}): {counters[code]}")


if __name__ == "__main__":
    main()
