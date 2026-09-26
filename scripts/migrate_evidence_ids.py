"""One-off migration: add validation_id / change_id / audit_id / response_id
and re-seed evidence linked in-context. Run from repo root."""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
EVIDENCE_DIR = DATA / "evidence"


def main() -> None:
    vals = json.loads((DATA / "validations.json").read_text(encoding="utf-8"))
    for i, v in enumerate(vals, 1):
        v["validation_id"] = f"VAL-{i:03d}"
    (DATA / "validations.json").write_text(
        json.dumps(vals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    models = json.loads((DATA / "models.json").read_text(encoding="utf-8"))
    chg_n = aud_n = 0
    for m in models:
        for c in m.get("change_log", []):
            chg_n += 1
            c["change_id"] = f"CHG-{chg_n:03d}"
            desc = c.get("description", "").lower()
            if "classification" not in c:
                material_hints = (
                    "redevelop", "recalibrat", "migration", "moved from",
                    "new claims", "added combined", "added guarantee", "added shap",
                    "formalised", "initial build", "scenario threshold",
                )
                c["classification"] = (
                    "Material" if any(h in desc for h in material_hints) else "Non-material"
                )
            if "justification" not in c:
                c["justification"] = "Seeded historical entry."
        for a in m.get("audit_reviews", []):
            aud_n += 1
            a["audit_id"] = f"AUD-{aud_n:03d}"
    (DATA / "models.json").write_text(
        json.dumps(models, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    issues = json.loads((DATA / "issues.json").read_text(encoding="utf-8"))
    for iss in issues:
        for i, r in enumerate(iss.get("responses") or [], 1):
            r["response_id"] = f"{iss['issue_id']}-R{i}"
    (DATA / "issues.json").write_text(
        json.dumps(issues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    val_cr001_2025 = next(
        v["validation_id"]
        for v in vals
        if v["model_id"] == "QDB-CR-001" and v["date"] == "2025-11-20"
    )
    val_cr002_2025 = next(
        v["validation_id"]
        for v in vals
        if v["model_id"] == "QDB-CR-002" and v["date"] == "2025-02-28"
    )
    chg_cr001_v31 = next(
        c["change_id"]
        for m in models if m["model_id"] == "QDB-CR-001"
        for c in m["change_log"] if c["version"] == "3.1"
    )
    aud_cr001 = next(
        a["audit_id"]
        for m in models if m["model_id"] == "QDB-CR-001"
        for a in m["audit_reviews"]
    )
    aud_aml = next(
        a["audit_id"]
        for m in models if m["model_id"] == "QDB-OF-001"
        for a in m["audit_reviews"]
    )

    # Seed one Material Model Change validation (pending-style pack target for LoD1)
    # on QDB-CR-002 which has an overdue recalibration narrative.
    has_mmc = any(
        v["model_id"] == "QDB-CR-002" and v["type"] == "Material Model Change"
        for v in vals
    )
    if not has_mmc:
        new_val = {
            "validation_id": f"VAL-{len(vals) + 1:03d}",
            "model_id": "QDB-CR-002",
            "date": "2026-08-01",
            "type": "Material Model Change",
            "outcome": "Approved with Conditions",
            "validator": "Hassan Al-Mohannadi (Model Validation Unit)",
            "tests": [
                "Discriminatory power (Gini/KS)",
                "Calibration accuracy / backtest",
                "Documentation review",
            ],
            "summary": (
                "Revalidation opened for the overdue behavioural-scorecard recalibration. "
                "Awaiting first-line development pack (code, change memo, OOT results)."
            ),
        }
        vals.append(new_val)
        (DATA / "validations.json").write_text(
            json.dumps(vals, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        mmc_id = new_val["validation_id"]
    else:
        mmc_id = next(
            v["validation_id"]
            for v in vals
            if v["model_id"] == "QDB-CR-002" and v["type"] == "Material Model Change"
        )

    # Evidence files for new seed rows
    def write_stub(model_id: str, stamp: str, filename: str, body: str) -> str:
        folder = EVIDENCE_DIR / model_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stamp}_{filename}"
        path.write_text(body, encoding="utf-8")
        return f"data/evidence/{model_id}/{stamp}_{filename}"

    path_chg = write_stub(
        "QDB-CR-001", "20250402100000", "score_to_pd_recal_memo.txt",
        "Change memo: score-to-PD mapping recalibration following masterscale review (v3.1).",
    )
    path_aud = write_stub(
        "QDB-CR-001", "20250315143000", "ia_sme_override_workpapers.txt",
        "Internal Audit workpapers — SME origination override sample testing.",
    )
    path_mmc = write_stub(
        "QDB-CR-002", "20260801110000", "recal_dev_pack_outline.txt",
        "Outline of development pack for Material Model Change revalidation (code + OOT results pending).",
    )
    path_aud_aml = write_stub(
        "QDB-OF-001", "20250722120000", "aml_backlog_audit_memo.txt",
        "IA memo on AML alert backlog disposition testing.",
    )

    evidence = [
        {
            "evidence_id": "EV-001",
            "model_id": "QDB-CR-002",
            "linked_type": "issue_response",
            "linked_id": "ISS-001-R1",
            "filename": "recalibration_project_plan.txt",
            "stored_path": "data/evidence/QDB-CR-002/20260510090000_recalibration_project_plan.txt",
            "category": "Document",
            "description": "Recalibration project plan and timeline (target Q4 2026)",
            "uploaded_by": "Lina Haddad",
            "role": "LOD1",
            "uploaded_at": "2026-05-10T09:00:00",
        },
        {
            "evidence_id": "EV-002",
            "model_id": "QDB-CR-003",
            "linked_type": "issue_response",
            "linked_id": "ISS-004-R1",
            "filename": "override_rate_extract_q1_2026.txt",
            "stored_path": "data/evidence/QDB-CR-003/20260318120000_override_rate_extract_q1_2026.txt",
            "category": "Data extract",
            "description": "Q1 2026 override rate extract showing reduction from 31% to 26%",
            "uploaded_by": "Ahmed Al-Kuwari",
            "role": "LOD1",
            "uploaded_at": "2026-03-18T12:00:00",
        },
        {
            "evidence_id": "EV-003",
            "model_id": "QDB-CR-001",
            "linked_type": "validation",
            "linked_id": val_cr001_2025,
            "filename": "annual_validation_report_2025.txt",
            "stored_path": "data/evidence/QDB-CR-001/20251120162500_annual_validation_report_2025.txt",
            "category": "Document",
            "description": "2025 annual validation report — SME Application Scorecard",
            "uploaded_by": "Hassan Al-Mohannadi",
            "role": "LOD2",
            "uploaded_at": "2025-11-20T16:25:00",
        },
        {
            "evidence_id": "EV-004",
            "model_id": "QDB-IF-005",
            "linked_type": "issue_response",
            "linked_id": "ISS-010-R1",
            "filename": "scenario_weight_freeze_memo.txt",
            "stored_path": "data/evidence/QDB-IF-005/20260305100000_scenario_weight_freeze_memo.txt",
            "category": "Email",
            "description": "CFO memo freezing scenario weights pending independent validation",
            "uploaded_by": "Fatima Al-Sulaiti",
            "role": "LOD1",
            "uploaded_at": "2026-03-05T10:00:00",
        },
        {
            "evidence_id": "EV-005",
            "model_id": "QDB-ML-003",
            "linked_type": "issue",
            "linked_id": "ISS-012",
            "filename": "external_validation_rfp.txt",
            "stored_path": "data/evidence/QDB-ML-003/20260710083000_external_validation_rfp.txt",
            "category": "Email",
            "description": "RFP issued for external validation of the liquidity stress testing model",
            "uploaded_by": "Mohammed Al-Marri",
            "role": "LOD1",
            "uploaded_at": "2026-07-10T08:30:00",
        },
        {
            "evidence_id": "EV-006",
            "model_id": "QDB-CR-001",
            "linked_type": "change",
            "linked_id": chg_cr001_v31,
            "filename": "score_to_pd_recal_memo.txt",
            "stored_path": path_chg,
            "category": "Document",
            "description": "Change memo for v3.1 score-to-PD recalibration",
            "uploaded_by": "Rajesh Nair",
            "role": "LOD1",
            "uploaded_at": "2025-04-02T10:00:00",
        },
        {
            "evidence_id": "EV-007",
            "model_id": "QDB-CR-001",
            "linked_type": "audit",
            "linked_id": aud_cr001,
            "filename": "ia_sme_override_workpapers.txt",
            "stored_path": path_aud,
            "category": "Document",
            "description": "IA workpapers — SME override governance sample",
            "uploaded_by": "Abdulla Al-Sayed",
            "role": "LOD3",
            "uploaded_at": "2025-03-15T14:30:00",
        },
        {
            "evidence_id": "EV-008",
            "model_id": "QDB-CR-002",
            "linked_type": "validation",
            "linked_id": mmc_id,
            "filename": "recal_dev_pack_outline.txt",
            "stored_path": path_mmc,
            "category": "Document",
            "description": "LoD1 supporting outline for Material Model Change revalidation",
            "uploaded_by": "Lina Haddad",
            "role": "LOD1",
            "uploaded_at": "2026-08-01T11:00:00",
        },
        {
            "evidence_id": "EV-009",
            "model_id": "QDB-CR-002",
            "linked_type": "validation",
            "linked_id": val_cr002_2025,
            "filename": "conditional_approval_letter_2025.txt",
            "stored_path": write_stub(
                "QDB-CR-002", "20250228160000", "conditional_approval_letter_2025.txt",
                "MVU conditional approval — recalibration required by Q4 2025.",
            ),
            "category": "Document",
            "description": "2025 conditional approval letter for behavioural scorecard",
            "uploaded_by": "Hassan Al-Mohannadi",
            "role": "LOD2",
            "uploaded_at": "2025-02-28T16:00:00",
        },
        {
            "evidence_id": "EV-010",
            "model_id": "QDB-OF-001",
            "linked_type": "audit",
            "linked_id": aud_aml,
            "filename": "aml_backlog_audit_memo.txt",
            "stored_path": path_aud_aml,
            "category": "Document",
            "description": "Internal Audit memo on AML alert backlog",
            "uploaded_by": "Abdulla Al-Sayed",
            "role": "LOD3",
            "uploaded_at": "2025-07-22T12:00:00",
        },
    ]
    (DATA / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Migrated: {len(vals)} validations, {chg_n} changes, {aud_n} audits; "
        f"{len(evidence)} evidence rows; MMC={mmc_id}"
    )


if __name__ == "__main__":
    main()
