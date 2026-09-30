import json

import pytest

import config
import data_loader
import data_store
import repository
from conftest import Upload

VALIDATOR = "Hassan Al-Mohannadi"
CONSULTANT = "Priya Menon"
OWNER = "Ahmed Al-Kuwari"
DEVELOPER = "Lina Haddad"
AUDITOR = "Abdulla Al-Sayed"
ADMIN = "Maryam Al-Kaabi"


def last_event():
    return repository.list_audit()[-1]


def test_validator_can_reply_in_thread(act_as):
    """Defect 1: validators could not post in request threads."""
    act_as(VALIDATOR)
    rid = data_store.add_request_response("MC-001", "Please attach the v1/v2 comparison.")
    req = repository.get_request("MC-001")
    assert req["thread"][-1]["response_id"] == rid
    assert req["thread"][-1]["role"] == "LOD2"


def test_owner_cannot_reassign_validation(act_as):
    """Defect 2: owners could route their own model's validation."""
    act_as(OWNER)
    with pytest.raises(PermissionError):
        data_store.assign_request("VAL-015", "Hassan Al-Mohannadi (Model Validator (QDB))")


def test_developer_cannot_be_assigned_as_validator(act_as):
    act_as(ADMIN)
    with pytest.raises(PermissionError, match="independence"):
        data_store.assign_request("MC-001", "Lina Haddad (Risk Analytics)")  # developer of QDB-IF-005


def test_admin_cannot_close_or_raise_findings(act_as):
    """Defect 3: segregation of duties for the MRM Administrator."""
    act_as(ADMIN)
    with pytest.raises(PermissionError):
        data_store.close_request("FND-001", "closing")
    with pytest.raises(PermissionError):
        data_store.create_request("QDB-IF-001", {"type": "FND", "title": "x", "severity": "Low"})


def test_only_raiser_line_closes_finding(act_as):
    act_as(AUDITOR)  # FND-001 was raised by a validator
    with pytest.raises(PermissionError):
        data_store.close_request("FND-001", "closing")
    act_as(CONSULTANT)
    data_store.close_request("FND-001", "Segment back-test verified.")
    assert repository.get_request("FND-001")["status"] == "Closed"


def test_closing_validation_derives_dates_rating_and_status(act_as):
    act_as(CONSULTANT)
    data_store.close_request("VAL-015", "Recalculation reconciles within 1%.", outcome="Fit for Purpose")
    m = data_loader.get_model("QDB-IF-006")
    assert m["last_rating"] == "Fit for Purpose"
    assert m["last_validation"] == repository.get_request("VAL-015")["closed_date"]
    assert m["next_validation_due"] > m["last_validation"]
    assert m["status"] == "In Production"
    assert data_loader.validation_status(m) == "On Track"


def test_closed_validation_needs_rating_from_scale(act_as):
    act_as(CONSULTANT)
    with pytest.raises(ValueError):
        data_store.close_request("VAL-015", "done", outcome="Approved")


def test_material_change_puts_model_in_validation(act_as):
    act_as(DEVELOPER)
    cid = data_store.add_change_entry("QDB-IF-003", {
        "date": "2026-09-30", "version": "2.0", "description": "New CCF segmentation",
        "author": DEVELOPER, "classification": "Material", "justification": "Methodology change",
    })
    m = repository.get_model("QDB-IF-003")
    assert m["status"] == "In Validation" and m["pending_revalidation"]
    mc = [r for r in repository.list_requests("QDB-IF-003") if r.get("change_id") == cid][0]
    assert mc["materiality"] == "Material"
    assert mc["assigned_to"].startswith(CONSULTANT)  # the model's validator


def test_writes_record_before_and_after(act_as):
    act_as(VALIDATOR)
    data_store.add_request_response("MC-001", "Noted.")
    ev = last_event()
    before, after = json.loads(ev["before"]), json.loads(ev["after"])
    assert len(after["thread"]) == len(before["thread"]) + 1
    assert repository.verify_audit_chain() == (True, None)


def test_model_document_upload_ticks_checklist(act_as):
    act_as(DEVELOPER)
    m = data_loader.get_model("QDB-IF-005")
    assert data_loader.documentation_status(m)["Model Development Document"] is False
    data_store.attach_evidence("QDB-IF-005", "model", "QDB-IF-005",
                               Upload("mdd_v2.docx", b"development document"),
                               "Document", "MDD v2", doc_type="Model Development Document")
    assert data_loader.documentation_status(m)["Model Development Document"] is True


def test_evidence_hash_detects_altered_file(act_as):
    act_as(OWNER)
    eid = data_store.attach_evidence("QDB-CR-001", "model", "QDB-CR-001",
                                     Upload("../../etc/passwd", b"original"),
                                     "Document", "path traversal attempt")
    ev = next(e for e in repository.list_evidence() if e["evidence_id"] == eid)
    assert ev["stored_path"].startswith("QDB-CR-001/") and "/.." not in ev["stored_path"]
    assert data_store.read_evidence(ev) == (b"original", "ok")
    (config.evidence_dir() / ev["stored_path"]).write_bytes(b"swapped")
    assert data_store.read_evidence(ev)[1] == "altered"


def test_closed_request_rejects_evidence(act_as):
    act_as(CONSULTANT)
    with pytest.raises(ValueError, match="closed"):
        data_store.attach_evidence("QDB-IF-001", "validation_request", "VAL-002",
                                   Upload("late.pdf", b"x"), "Document", "late upload")
