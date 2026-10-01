"""Phase 1 — identification, registration, record editing, tier sign-off, factsheet."""

import pytest

import data_loader
import data_store
import governance
import repository

OWNER = "Model Owner 1"
DEVELOPER = "Model Developer 1"
OTHER_LOD1 = "Model Owner 4"
VALIDATOR = "Model Validator 1"
CONSULTANT = "Model Validator 2"
ADMIN = "MRM Administrator 1"
CRO = "CRO"

MODEL_ANSWERS = {"quantitative": True, "theory": True}
EUC_ANSWERS = {"quantitative": True, "deterministic_only": True, "decision_use": True}
AI_TOOL_ANSWERS = {"learns_from_data": True, "decision_use": True}


def new_model_record(**over):
    rec = {
        "name": "SME Early Warning Model", "risk_type": "Credit Rating & Scoring",
        "methodology": "Logistic regression on account conduct", "description": "Flags SMEs at risk.",
        "owner": "Model Owner 1 (Head of Credit Risk)", "developer": "Model Developer 3 (Credit Modelling)",
        "upstream": ["QDB-007"], "uses": [{"use": "Watch-list", "business_area": "Credit",
                                             "decision": "Watch-list entry", "status": "Planned"}],
        "tier_scores": {"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Low"},
        "tier_rationale": "Advisory early-warning signal.",
    }
    rec.update(over)
    return rec


# ---------------------------------------------------------------- identification
@pytest.mark.parametrize("answers,expected", [
    (MODEL_ANSWERS, governance.CLASS_MODEL),
    ({"quantitative": True, "learns_from_data": True}, governance.CLASS_MODEL),
    (EUC_ANSWERS, governance.CLASS_EUC),
    (AI_TOOL_ANSWERS, governance.CLASS_AI_TOOL),
    ({"quantitative": True, "deterministic_only": True}, governance.CLASS_NOT_MODEL),
])
def test_identification(answers, expected):
    assert governance.identify(answers)["classification"] == expected


# ---------------------------------------------------------------- registration
def test_register_model_creates_proposed_tier_and_mirrors_dependencies(act_as):
    act_as(OWNER)
    mid = data_store.register_model(new_model_record(), MODEL_ANSWERS)
    assert mid == "QDB-018"
    m = data_loader.get_model(mid)
    assert m["tier"] == 2 and not m["tier_confirmed"]
    assert m["tier_assessment"]["proposed_by"] == OWNER
    assert mid in repository.get_model("QDB-007")["dependencies"]["downstream"]
    assert data_loader.validation_status(m) == "Pre-implementation"
    assert repository.list_audit()[-1]["action"] == "register_model"


def test_register_rejects_non_model_and_tools_reject_models(act_as):
    act_as(OWNER)
    with pytest.raises(ValueError, match="Not a model"):
        data_store.register_model(new_model_record(), EUC_ANSWERS)
    with pytest.raises(ValueError, match="is a model"):
        data_store.register_tool({"name": "x", "description": "y", "owner": OWNER}, MODEL_ANSWERS)


def test_register_tools_by_class(act_as):
    act_as(OWNER)
    euc = data_store.register_tool({"name": "Limit tracker", "description": "Excel",
                                    "owner": OWNER}, EUC_ANSWERS)
    ai = data_store.register_tool({"name": "Chat assistant", "description": "Drafts emails",
                                   "owner": OWNER, "ai_autonomy": "Fully autonomous",
                                   "ai_functional_category": "Customer interaction"}, AI_TOOL_ANSWERS)
    assert euc == "QDB-EUC-003" and ai == "QDB-AI-002"
    row = next(r for r in data_loader.ai_register() if r["id"] == ai)
    assert row["qcb_approval_required"]  # fully autonomous AI always needs QCB approval


def test_validator_cannot_register(act_as):
    act_as(VALIDATOR)
    with pytest.raises(PermissionError):
        data_store.register_model(new_model_record(), MODEL_ANSWERS)


# ---------------------------------------------------------------- editing
def test_owner_edits_own_model_and_change_is_audited(act_as):
    act_as(DEVELOPER)  # developer of QDB-005
    changed = data_store.update_model("QDB-005", {
        "known_limitations": "Weights are a likelihood weighting\nNew limitation",
        "exposure_covered_qar_mn": 9600,
    })
    assert set(changed) == {"known_limitations", "exposure_covered_qar_mn"}
    ev = repository.list_audit()[-1]
    assert ev["action"] == "edit_model" and ev["before"] and ev["after"]


def test_lod1_cannot_edit_someone_elses_model(act_as):
    act_as(OTHER_LOD1)
    with pytest.raises(PermissionError, match="owner or developer"):
        data_store.update_model("QDB-005", {"description": "x"})


def test_owner_cannot_change_accountability(act_as):
    act_as(OWNER)
    with pytest.raises(PermissionError):
        data_store.update_model("QDB-005", {"validator": "Model Validator 2 (External validation consultant)"})


def test_admin_validator_assignment_respects_independence(act_as):
    act_as(ADMIN)
    with pytest.raises(PermissionError, match="independence"):
        data_store.update_model("QDB-005", {"validator": "Model Developer 1 (Risk Analytics)"})
    assert data_store.update_model("QDB-005", {"validator": "Model Validator 2 (External validation consultant)"}) == ["validator"]


def test_upstream_edit_keeps_downstream_in_sync(act_as):
    act_as(ADMIN)
    data_store.update_model("QDB-009", {"upstream": ["QDB-001"]})  # drop QDB-002
    assert "QDB-009" not in repository.get_model("QDB-002")["dependencies"]["downstream"]
    assert "QDB-009" in repository.get_model("QDB-001")["dependencies"]["downstream"]


def test_tier_fields_not_editable(act_as):
    act_as(ADMIN)
    with pytest.raises(ValueError, match="cannot be edited"):
        data_store.update_model("QDB-005", {"tier_scores": {}})


# ---------------------------------------------------------------- tier sign-off
def test_tier_proposal_confirmation_flow(act_as):
    act_as(DEVELOPER)
    data_store.propose_tier("QDB-005", {"materiality": "Low", "complexity": "Medium",
                                           "regulatory_impact": "Low"}, "Lower reliance")
    m = data_loader.get_model("QDB-005")
    assert m["tier"] == 1 and not m["tier_confirmed"]   # old tier in force until confirmed
    with pytest.raises(ValueError, match="already awaiting"):
        data_store.propose_tier("QDB-005", {"materiality": "Low", "complexity": "Low",
                                               "regulatory_impact": "Low"}, "again")
    act_as(CONSULTANT)
    assert data_store.confirm_tier("QDB-005") == governance.TIER_CONFIRMED
    m = data_loader.get_model("QDB-005")
    assert m["tier"] == 3 and m["tier_confirmed"] and len(m["tier_history"]) == 1
    assert m["validation_frequency"] == "Triennial"


def test_proposer_cannot_confirm_own_tier(act_as):
    act_as(ADMIN)
    data_store.propose_tier("QDB-004", {"materiality": "High", "complexity": "Low",
                                           "regulatory_impact": "High"}, "Annual review")
    with pytest.raises(PermissionError, match="proposed"):
        data_store.confirm_tier("QDB-004")


def test_override_needs_reason_and_cro(act_as):
    act_as(OWNER)
    mid = data_store.register_model(new_model_record(), MODEL_ANSWERS)  # rule-based tier 2
    act_as(VALIDATOR)
    with pytest.raises(ValueError, match="reason"):
        data_store.confirm_tier(mid, override_tier=1)
    assert data_store.confirm_tier(mid, override_tier=1, override_reason="Feeds credit decisions") \
        == governance.TIER_OVERRIDE_PENDING
    assert data_loader.get_model(mid)["tier"] == 2      # not in force until the CRO approves
    with pytest.raises(PermissionError):
        data_store.decide_tier_override(mid, True)      # validator is not the CRO
    act_as(CRO)
    data_store.decide_tier_override(mid, True, "Agreed")
    m = data_loader.get_model(mid)
    assert m["tier"] == 1 and m["computed_tier"] == 2 and m["tier_confirmed"]
    assert m["approval_body"] == "Management Risk Committee"
    assert "Data Quality Assessment" in m["documentation"]   # tier-1 checklist


def test_cro_rejection_keeps_rule_based_tier(act_as):
    act_as(OWNER)
    mid = data_store.register_model(new_model_record(), MODEL_ANSWERS)
    act_as(VALIDATOR)
    data_store.confirm_tier(mid, override_tier=3, override_reason="Advisory only")
    act_as(CRO)
    data_store.decide_tier_override(mid, False, "Keep rule-based tier")
    m = data_loader.get_model(mid)
    assert m["tier"] == 2 and m["tier_override"] is None and m["tier_confirmed"]


# ---------------------------------------------------------------- factsheet
def test_factsheet_is_a_one_page_pdf():
    from io import BytesIO

    from pypdf import PdfReader

    pdf = data_loader.factsheet_pdf("QDB-006")
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "QDB-006" in text and "FND-002" in text
