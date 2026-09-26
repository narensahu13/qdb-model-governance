"""One-shot migration: validations.json + issues.json → validation_requests.json.

Also remaps evidence linked_type/linked_id for validation / issue / issue_response.
Keeps validations.json and issues.json as read-only archives (not written by the app).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TYPE_LABELS = {
    "MMC": "Material Model Change",
    "NMMC": "Non-material Model Change",
    "VAL": "Independent Validation",
    "VRQ": "Validation Request",
    "VFI": "Validation Finding",
}


def _map_val_type(raw: str) -> tuple[str, str | None]:
    """Return (request type code, optional VAL subtype label)."""
    t = (raw or "").strip()
    if t == "Material Model Change":
        return "MMC", None
    if t == "Non-material Model Change Review":
        return "NMMC", None
    return "VAL", t


def _status_from_issue(status: str) -> str:
    if status == "Closed":
        return "Closed"
    # Overdue / Open → Open (overdue derived from due_date in the UI)
    return "Open"


def main() -> None:
    validations = json.loads((DATA / "validations.json").read_text(encoding="utf-8"))
    issues = json.loads((DATA / "issues.json").read_text(encoding="utf-8"))
    evidence = json.loads((DATA / "evidence.json").read_text(encoding="utf-8"))

    requests: list[dict] = []
    id_remap: dict[str, str] = {}  # legacy id → new request_id
    counters = {"MMC": 0, "NMMC": 0, "VAL": 0, "VRQ": 0, "VFI": 0}

    def next_id(code: str) -> str:
        counters[code] += 1
        return f"{code}-{counters[code]:03d}"

    # ---- validations → MMC / NMMC / VAL
    for v in validations:
        legacy = v.get("validation_id") or f"VAL-legacy-{v['model_id']}-{v['date']}"
        code, subtype = _map_val_type(v.get("type", ""))
        rid = next_id(code)
        id_remap[legacy] = rid

        # VAL-027 style open revalidation: treat incomplete MMC as In Progress
        summary = v.get("summary") or ""
        awaiting = "awaiting" in summary.lower() or "opened for" in summary.lower()
        if code == "MMC" and awaiting:
            status = "In Progress"
            closed_date = None
            outcome = None
        else:
            status = "Closed"
            closed_date = v["date"]
            outcome = v.get("outcome")

        title = TYPE_LABELS[code]
        if subtype:
            title = f"{subtype}"

        thread = []
        if summary:
            thread.append({
                "response_id": f"{rid}-R1",
                "date": v["date"],
                "author": (v.get("validator") or "MVU").split(" (")[0],
                "role": "LOD2",
                "text": summary,
                "evidence_ids": [],
            })

        requests.append({
            "request_id": rid,
            "type": code,
            "model_id": v["model_id"],
            "status": status,
            "initiated_by": (v.get("validator") or "Hassan Al-Mohannadi").split(" (")[0],
            "initiated_by_role": "LOD2",
            "assigned_to": v.get("validator") or "Hassan Al-Mohannadi (Model Validation Unit)",
            "title": title,
            "description": summary,
            "created_date": v["date"],
            "closed_date": closed_date,
            "due_date": None,
            "outcome": outcome,
            "severity": None,
            "remediation": None,
            "source": "Validation",
            "validation_subtype": subtype,
            "tests": v.get("tests") or [],
            "legacy_id": legacy,
            "thread": thread,
        })

    # ---- issues → VFI (preserve numbering where possible)
    for iss in issues:
        legacy = iss["issue_id"]
        # Prefer VFI-NNN matching ISS-NNN
        try:
            num = int(legacy.split("-")[-1])
            rid = f"VFI-{num:03d}"
            counters["VFI"] = max(counters["VFI"], num)
        except ValueError:
            rid = next_id("VFI")
        id_remap[legacy] = rid

        thread = []
        for resp in iss.get("responses") or []:
            old_rid = resp.get("response_id") or ""
            new_resp_id = old_rid.replace(legacy, rid) if old_rid.startswith(legacy) else None
            if not new_resp_id:
                n = len(thread) + 1
                new_resp_id = f"{rid}-R{n}"
            if old_rid:
                id_remap[old_rid] = new_resp_id
            thread.append({
                "response_id": new_resp_id,
                "date": resp["date"],
                "author": resp["author"],
                "role": resp.get("role", "LOD1"),
                "text": resp["text"],
                "evidence_ids": list(resp.get("evidence_ids") or []),
            })

        status = _status_from_issue(iss.get("status", "Open"))
        requests.append({
            "request_id": rid,
            "type": "VFI",
            "model_id": iss["model_id"],
            "status": status,
            "initiated_by": iss.get("raised_by") or "Hassan Al-Mohannadi",
            "initiated_by_role": iss.get("raised_by_role") or "LOD2",
            "assigned_to": iss.get("owner") or "",
            "title": iss["title"],
            "description": iss["description"],
            "created_date": iss["raised_date"],
            "closed_date": iss.get("closed_date"),
            "due_date": iss.get("due_date"),
            "outcome": "Closed" if status == "Closed" else None,
            "severity": iss.get("severity"),
            "remediation": iss.get("remediation"),
            "source": iss.get("source"),
            "validation_subtype": None,
            "tests": [],
            "legacy_id": legacy,
            "thread": thread,
        })

    # ---- demo VRQ (LoD1 → LoD2) so the type shows in demos
    requests.append({
        "request_id": next_id("VRQ"),
        "type": "VRQ",
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
        "validation_subtype": None,
        "tests": [],
        "legacy_id": None,
        "thread": [
            {
                "response_id": "VRQ-001-R1",
                "date": "2026-03-12",
                "author": "Hassan Al-Mohannadi",
                "role": "LOD2",
                "text": "Accepted. External firm shortlist under review; kick-off targeted for Q3.",
                "evidence_ids": [],
            }
        ],
    })

    # Sort: type then id
    type_order = {"MMC": 0, "NMMC": 1, "VAL": 2, "VRQ": 3, "VFI": 4}
    requests.sort(key=lambda r: (type_order.get(r["type"], 9), r["request_id"]))

    (DATA / "validation_requests.json").write_text(
        json.dumps(requests, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # ---- remap evidence
    for ev in evidence:
        lt = ev.get("linked_type")
        lid = ev.get("linked_id") or ""
        if lt == "validation":
            ev["linked_type"] = "validation_request"
            ev["linked_id"] = id_remap.get(lid, lid)
        elif lt == "issue":
            ev["linked_type"] = "validation_request"
            ev["linked_id"] = id_remap.get(lid, lid)
        elif lt == "issue_response":
            ev["linked_type"] = "request_response"
            ev["linked_id"] = id_remap.get(lid, lid)

    (DATA / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(requests)} validation requests")
    for code in ("MMC", "NMMC", "VAL", "VRQ", "VFI"):
        n = sum(1 for r in requests if r["type"] == code)
        print(f"  {code}: {n}")
    print(f"Evidence remaps applied: {len(id_remap)} id mappings")


if __name__ == "__main__":
    main()
