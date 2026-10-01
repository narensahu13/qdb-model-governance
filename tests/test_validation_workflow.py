"""Phase 2 — gates G2–G5, validation engagement, approvals, conditions, tasks, admin."""

import pytest

import data_loader
import data_store
import governance
import repository
from conftest import Upload

V1 = "Model Validator 1"
V2 = "Model Validator 2"
CRO = "CRO"
ADMIN = "MRM Administrator 1"


def run_engagement(act_as, rid, validator, owner, rating, with_ir=True):
    """Drive a validation from scoping to sign-off."""
    act_as(validator)
    if repository.get_request(rid)["engagement"]["stage"] == "Scoping":
        data_store.start_engagement(rid, "Full scope", ["Documentation review"])
    if with_ir:
        data_store.add_info_request(rid, "Latest code", owner, "2026-12-01")
    for ir in repository.get_request(rid)["engagement"]["info_requests"]:
        if ir["status"] == "Open":
            act_as(owner)
            data_store.answer_info_request(rid, ir["ir_id"], "Provided")
    act_as(validator)
    data_store.issue_draft(rid, rating, "Conclusions")
    act_as(owner)
    data_store.submit_owner_review(rid, "")
    act_as(validator)
    data_store.sign_off(rid, rating, "Signed")


# ---------------------------------------------------------------- engagement rules
def test_only_assigned_validator_runs_engagement(act_as):
    act_as(V1)  # VAL-015 is assigned to Model Validator 2
    with pytest.raises(PermissionError, match="assigned validator"):
        data_store.start_engagement("VAL-015", "scope", [])


def test_draft_blocked_while_information_requests_open(act_as):
    act_as(V2)
    with pytest.raises(ValueError, match="still open"):
        data_store.issue_draft("VAL-014", "Fit for Purpose", "x")  # QDB-010 has open IRs


def test_sign_off_waits_for_owner_review_or_lapse(act_as):
    act_as(V2)
    data_store.start_engagement("VAL-015", "scope", [])
    data_store.issue_draft("VAL-015", "Fit for Purpose", "Draft")
    with pytest.raises(ValueError, match="factual-accuracy"):
        data_store.sign_off("VAL-015", "Fit for Purpose", "")
    # simulate the review window lapsing
    with repository.tx() as conn:
        r = repository.get_request("VAL-015", conn)
        r["engagement"]["draft"]["issued_on"] = "2026-01-01"
        repository.put_request(conn, r)
    data_store.sign_off("VAL-015", "Fit for Purpose", "Owner did not respond")
    assert repository.get_request("VAL-015")["status"] == "Closed"


def test_validator_can_send_an_answer_back(act_as):
    act_as(V2)  # IR-2 on VAL-014 is answered
    data_store.send_back_info_request("VAL-014", "IR-2", "Add data lineage for each feature")
    ir = repository.get_request("VAL-014")["engagement"]["info_requests"][1]
    assert ir["status"] == "Open" and ir["review_comment"]


def test_only_owner_answers_and_reviews(act_as):
    act_as("Model Owner 5")  # not involved with QDB-010
    with pytest.raises(PermissionError):
        data_store.answer_info_request("VAL-014", "IR-3", "x")


# ---------------------------------------------------------------- G2
def test_g2_needs_documents_then_opens_validation(act_as):
    act_as("Model Developer 4")  # developer of QDB-013, in development, tier confirmed
    with pytest.raises(ValueError, match="required documents"):
        data_store.submit_for_validation("QDB-013")
    for d in governance.G2_REQUIRED_DOCS[1]:
        data_store.attach_evidence("QDB-013", "model", "QDB-013", Upload(f"{d}.docx", b"x"),
                                   "Document", d, doc_type=d)
    rid = data_store.submit_for_validation("QDB-013", "Ready")
    req = repository.get_request(rid)
    assert req["engagement"]["stage"] == "Scoping" and req["validation_subtype"] == "Initial"
    assert repository.get_model("QDB-013")["status"] == "In Validation"


def test_g2_cannot_be_bypassed(act_as):
    act_as("Model Developer 4")
    with pytest.raises(ValueError, match="gate G2"):
        data_store.create_request("QDB-013", {"type": "VAL", "title": "x"})


# ---------------------------------------------------------------- G3 -> G4 -> G5
def test_full_route_to_production(act_as):
    run_engagement(act_as, "VAL-014", V2, "Model Developer 4", "Fit with Conditions", with_ir=False)
    m = data_loader.get_model("QDB-010")
    assert m["status"] == governance.STATUS_AWAITING_APPROVAL
    assert governance.current_gate(m) == "G4"
    # Tier 1: committee decision needs the minute reference
    act_as(CRO)
    with pytest.raises(ValueError, match="minute"):
        data_store.record_approval("QDB-010", "Approved", [])
    act_as(ADMIN)  # secretary records the committee decision
    data_store.record_approval("QDB-010", "Approved with conditions",
                               [{"condition": "Bias tests repeated after 6 months", "due": "2027-04-30"}],
                               minute_ref="MgmtRC 2026-10 item 3")
    m = data_loader.get_model("QDB-010")
    assert m["status"] == governance.STATUS_AWAITING_IMPLEMENTATION
    act_as("Model Developer 4")
    with pytest.raises(PermissionError):
        data_store.verify_implementation("QDB-010", "x")
    act_as(V2)
    assert data_store.verify_implementation("QDB-010", "Version 0.5 deployed") == "Approved with Conditions"
    assert data_loader.validation_status(data_loader.get_model("QDB-010")) == "On Track"


def test_tier2_approval_is_the_cros(act_as):
    act_as(ADMIN)
    with pytest.raises(PermissionError, match="CRO"):
        data_store.record_approval("QDB-011", "Approved")
    act_as(CRO)
    data_store.record_approval("QDB-011", "Approved")
    assert repository.get_model("QDB-011")["status"] == governance.STATUS_AWAITING_IMPLEMENTATION


def test_rejection_returns_to_development(act_as):
    act_as(CRO)
    data_store.record_approval("QDB-011", "Rejected", comment="Rework the expatriate segment")
    assert repository.get_model("QDB-011")["status"] == "In Development"


def test_not_fit_on_route_returns_to_development(act_as):
    run_engagement(act_as, "VAL-014", V2, "Model Developer 4", "Not Fit for Purpose", with_ir=False)
    assert repository.get_model("QDB-010")["status"] == "In Development"


def test_material_change_goes_back_through_approval(act_as):
    run_engagement(act_as, "MC-001", V1, "Model Developer 1", "Fit for Purpose", with_ir=False)
    assert repository.get_model("QDB-005")["status"] == governance.STATUS_AWAITING_APPROVAL


def test_conditions_met_verified_then_production(act_as):
    act_as("Model Developer 3")
    data_store.update_condition("QDB-012", "APR-013", "C-1", "met", "Plan approved 30 Sep")
    act_as("Model Developer 3")
    with pytest.raises(PermissionError):
        data_store.update_condition("QDB-012", "APR-013", "C-1", "verify")
    act_as(V1)
    data_store.update_condition("QDB-012", "APR-013", "C-1", "verify")
    assert data_store.verify_implementation("QDB-012", "Deployed v1.0 checked") == "In Production"


# ---------------------------------------------------------------- tasks
def test_task_inbox(act_as):
    titles = lambda who: [t["title"] for t in data_loader.tasks_for(repository_user(who))]  # noqa: E731
    assert any("Approve or reject" in t for t in titles(CRO))
    assert any("Verify implementation" in t for t in titles(V1))
    assert any("IR-3" in t for t in titles("Model Developer 4"))
    assert any("Scope VAL-015" in t for t in titles(V2))


def repository_user(name):
    return next(u for u in repository.list_users() if u["name"] == name)


# ---------------------------------------------------------------- administration
def test_rename_person_propagates_but_audit_keeps_history(act_as):
    act_as(ADMIN)
    n = data_store.save_user("Model Validator 2", "Jane Example", "External validation consultant", "LOD2")
    assert n > 5
    assert repository.get_model("QDB-006")["validator"] == "Jane Example (External validation consultant)"
    assert repository.get_request("VAL-014")["assigned_to"].startswith("Jane Example")
    assert any(e["user"] == "Model Validator 2" for e in repository.list_audit())  # history untouched
    assert repository.verify_audit_chain() == (True, None)


def test_rename_model_id_updates_references(act_as):
    act_as(ADMIN)
    data_store.rename_model_id("QDB-001", "QDB-101")
    assert repository.get_model("QDB-001") is None
    assert "QDB-101" in repository.get_model("QDB-004")["dependencies"]["upstream"]
    assert all(r["model_id"] != "QDB-001" for r in repository.list_requests())
    assert data_loader.get_model("QDB-101")["last_validation"] is not None
    with pytest.raises(ValueError):
        data_store.rename_model_id("QDB-002", "IF-2")
    with pytest.raises(ValueError, match="already"):
        data_store.rename_model_id("QDB-002", "QDB-003")


def test_only_admin_administers(act_as):
    act_as(CRO)
    with pytest.raises(PermissionError):
        data_store.save_user(None, "X", "Y", "LOD1")
