"""Phase 3 — KMPIs (pass/fail, per-model frequency, upload), annual confirmation, decommissioning."""

import io
from datetime import date

import pandas as pd
import pytest

import data_loader
import data_store
import governance
import kmpi
import repository

OWNER1, DEV1, DEV4 = "Model Owner 1", "Model Developer 1", "Model Developer 4"
V1, V2 = "Model Validator 1", "Model Validator 2"
ADMIN, SPONSOR1 = "MRM Administrator 1", "Model Sponsor 1"
TODAY = date(2026, 10, 4)
Q = kmpi.reporting_period("Quarterly")


def user(name):
    return next(u for u in repository.list_users() if u["name"] == name)


# ---------------------------------------------------------------- periods and frequencies
def test_periods_for_every_frequency():
    assert kmpi.reporting_period("Quarterly", TODAY) == "2026-Q3"
    assert kmpi.reporting_period("Monthly", TODAY) == "2026-09"
    assert kmpi.reporting_period("Semi-annual", TODAY) == "2026-H1"
    assert kmpi.reporting_period("Annual", TODAY) == "2025"
    assert kmpi.reporting_period("Monthly", date(2026, 1, 5)) == "2025-12"
    assert kmpi.previous_period("2026-Q1") == "2025-Q4" and kmpi.previous_period("2026-01") == "2025-12"
    assert kmpi.due_date("2026-Q3") == date(2026, 10, 30)
    assert kmpi.due_date("2026-H1") == date(2026, 7, 30)
    assert kmpi.recent_periods("Semi-annual", 3, TODAY) == ["2026-H1", "2025-H2", "2025-H1"]


def test_kmpi_can_be_reported_less_often_than_its_model():
    ks = [{"kmpi_id": "A", "frequency": "As model"}, {"kmpi_id": "B", "frequency": "Annual"},
          {"kmpi_id": "C", "frequency": "Monthly"}]          # monthly on a quarterly model -> quarterly
    assert [k["kmpi_id"] for k in kmpi.due_kmpis(ks, "2026-Q3")] == ["A", "C"]
    assert [k["kmpi_id"] for k in kmpi.due_kmpis(ks, "2026-Q4")] == ["A", "B", "C"]


def test_submission_needs_result_and_comment_for_fails():
    due = [{"kmpi_id": "A"}, {"kmpi_id": "B"}]
    assert kmpi.submission_problems(due, {"A": {"result": "Pass"}, "B": {"result": "Fail"}}) == [
        "B: say why it is 'Fail' and what is being done"]
    assert kmpi.submission_problems(due, {"A": {"result": "Pass"}, "B": {"result": "Fail", "comment": "x"}}) == []


def test_template_round_trip():
    due = [{"kmpi_id": "KMPI-001", "name": "Gini", "description": "Pass if >= 0.55"}]
    data = kmpi.template_xlsx(due)
    df = pd.read_excel(io.BytesIO(data), dtype=str)
    df.loc[0, ["Value", "Result", "Comment"]] = ["0.61", "pass", ""]
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    assert kmpi.parse_upload(buf.getvalue(), "q3.xlsx") == {"KMPI-001": {"value": "0.61", "result": "Pass",
                                                                         "comment": ""}}
    with pytest.raises(ValueError, match="Pass, Fail"):
        kmpi.parse_upload(b"KMPI ID,Result\nKMPI-001,Maybe\n", "q3.csv")


# ---------------------------------------------------------------- library
def test_library_add_edit_retire(act_as):
    act_as(DEV4)  # developer of QDB-013 (no KMPIs yet)
    added = data_store.save_kmpi_library("QDB-013", [
        {"name": "Combined-grade agreement", "description": "Pass if at least 80% agree; otherwise Fail."}])
    assert added == ["KMPI-045"]
    with pytest.raises(ValueError, match="pass/fail"):
        data_store.save_kmpi_library("QDB-013", [{"kmpi_id": "KMPI-045", "name": "x", "description": ""}])
    # leaving it out of the list retires it, never deletes it
    data_store.save_kmpi_library("QDB-013", [])
    k = next(x for x in repository.list_kmpis() if x["kmpi_id"] == "KMPI-045")
    assert k["active"] is False


def test_only_first_line_of_the_model_defines_kmpis(act_as):
    for who in ("Model Owner 5", V1, SPONSOR1):
        act_as(who)
        with pytest.raises(PermissionError):
            data_store.save_kmpi_library("QDB-001", [])


def test_owner_sets_the_frequency(act_as):
    act_as(OWNER1)
    data_store.set_kmpi_frequency("QDB-004", "Monthly")
    m = data_loader.get_model("QDB-004")
    assert data_loader.model_frequency(m) == "Monthly"
    assert data_loader.current_period(m, TODAY) == "2026-09"


# ---------------------------------------------------------------- returns
def _entries(results, comment=""):
    return {kid: {"value": "x", "result": r, "comment": comment} for kid, r in results.items()}


def test_draft_then_submit(act_as):
    act_as(DEV1)   # QDB-001: draft with two KMPIs still empty
    with pytest.raises(ValueError, match="KMPI-004"):
        data_store.save_kmpi_return("QDB-001", Q, {}, submit=True, attest=True)
    entries = _entries({"KMPI-004": "Pass", "KMPI-005": "Fail"})
    with pytest.raises(ValueError, match="KMPI-005"):
        data_store.save_kmpi_return("QDB-001", Q, entries, submit=True, attest=True)
    entries["KMPI-005"]["comment"] = "Ratings backlog after the CreditLens upgrade"
    with pytest.raises(ValueError, match="confirmation"):
        data_store.save_kmpi_return("QDB-001", Q, entries, submit=True)
    assert data_store.save_kmpi_return("QDB-001", Q, entries, submit=True, attest=True) == kmpi.SUBMITTED
    ret = data_loader.kmpi_return("QDB-001", Q)
    assert ret["values"]["KMPI-005"]["result"] == "Fail" and "Pass if" in ret["values"]["KMPI-005"]["description"]
    with pytest.raises(ValueError, match="no longer"):
        data_store.save_kmpi_return("QDB-001", Q, entries)
    assert repository.verify_audit_chain() == (True, None)


def test_upload_fills_the_draft(act_as):
    act_as(OWNER1)
    csv = b"KMPI ID,Value,Result,Comment\nKMPI-004,0.08,Pass,\nKMPI-005,1.7%,Pass,\n"
    data_store.save_kmpi_return("QDB-001", Q, kmpi.parse_upload(csv, "q3.csv"))
    ret = data_loader.kmpi_return("QDB-001", Q)
    assert ret["status"] == kmpi.DRAFT and ret["values"]["KMPI-005"]["value"] == "1.7%"
    assert ret["values"]["KMPI-001"]["result"] == "Pass"          # earlier entries kept
    with pytest.raises(ValueError, match="KMPI-099"):
        data_store.save_kmpi_return("QDB-001", Q, {"KMPI-099": {"result": "Pass"}})


def test_only_owner_or_developer_reports(act_as):
    for who in (V1, ADMIN, "Model Owner 5"):
        act_as(who)
        with pytest.raises(PermissionError):
            data_store.save_kmpi_return("QDB-001", Q, {})


def test_validator_returns_then_reviews_and_raises_finding(act_as):
    act_as(V2)     # QDB-008 return is submitted with two fails
    with pytest.raises(ValueError, match="corrected"):
        data_store.review_kmpi_return("QDB-008", Q, accept=False)
    data_store.review_kmpi_return("QDB-008", Q, accept=False, comment="Attach the Gini workings")
    assert data_loader.kmpi_return("QDB-008", Q)["status"] == kmpi.RETURNED
    act_as(OWNER1)
    data_store.save_kmpi_return("QDB-008", Q, {}, submit=True, attest=True, note="Workings attached")
    act_as(V2)
    fid = data_store.review_kmpi_return("QDB-008", Q, accept=True, comment="Agree a segment fix",
                                        raise_finding=True)
    ret = data_loader.kmpi_return("QDB-008", Q)
    assert ret["status"] == kmpi.REVIEWED and ret["finding_id"] == fid
    f = repository.get_request(fid)
    assert f["type"] == "FND" and f["source"] == "Monitoring" and "KMPI-023" in f["description"]


def test_owner_cannot_review_own_return(act_as):
    act_as(OWNER1)
    with pytest.raises(PermissionError):
        data_store.review_kmpi_return("QDB-003", Q, accept=True)


def test_overview_uses_each_models_frequency():
    rows = {r["model_id"]: r for r in data_loader.kmpi_overview(TODAY)}
    assert rows["QDB-014"]["period"] == "2026-09" and rows["QDB-014"]["status"] == kmpi.SUBMITTED
    assert rows["QDB-009"]["period"] == "2026-H1" and rows["QDB-009"]["status"] == kmpi.REVIEWED
    assert rows["QDB-016"]["period"] == "2025"
    assert rows["QDB-004"]["status"] == kmpi.RETURNED
    assert "QDB-013" not in rows and "QDB-018" not in rows      # not in use / retired


def test_kmpi_tasks():
    dev = [t["title"] for t in data_loader.tasks_for(user(DEV1))]
    assert any("Correct and resubmit the 2026-Q3" in t for t in dev)       # QDB-004 sent back
    v1 = [(t["model_id"], t["title"]) for t in data_loader.tasks_for(user(V1))]
    assert ("QDB-014", "Review the 2026-09 KMPI return") in v1               # monthly model


def test_kmpis_needed_before_go_live(act_as):
    with repository.tx() as conn:
        for k in repository.list_kmpis(conn):
            if k["model_id"] == "QDB-012":
                repository.put_kmpi(conn, {**k, "active": False})
    act_as(V1)
    with pytest.raises(ValueError, match="KMPI"):
        data_store.verify_implementation("QDB-012", "Deployed v1.0 checked")


def test_rename_model_moves_kmpis(act_as):
    act_as(ADMIN)
    data_store.rename_model_id("QDB-001", "QDB-101")
    assert all(k["model_id"] != "QDB-001" for k in repository.list_kmpis())
    assert data_loader.kmpi_return("QDB-101", "2026-Q2")["status"] == kmpi.REVIEWED


# ---------------------------------------------------------------- annual confirmation
def test_annual_confirmation(act_as):
    m = data_loader.get_model("QDB-014")                     # last confirmed Sep 2025
    assert governance.confirmation_status(m, TODAY) == "Overdue"
    assert any(t["kind"] == "Annual confirmation" and t["model_id"] == "QDB-014"
               for t in data_loader.tasks_for(user("Model Owner 3")))
    act_as("Model Developer 1")
    with pytest.raises(PermissionError):
        data_store.confirm_model("QDB-014", [True, True, True])
    act_as("Model Owner 3")
    with pytest.raises(ValueError, match="Tick every"):
        data_store.confirm_model("QDB-014", [True, False, True])
    data_store.confirm_model("QDB-014", [True, True, True], "No changes this year")
    assert governance.confirmation_status(data_loader.get_model("QDB-014")) == "Confirmed"


# ---------------------------------------------------------------- decommissioning
def test_decommission_requested_by_owner_approved_by_sponsor(act_as):
    act_as("Model Owner 5")                                  # owner of QDB-016, sponsor is Model Sponsor 1
    with pytest.raises(ValueError, match="Choose a reason"):
        data_store.request_decommission("QDB-016", "Bored", "2026-12-31")
    data_store.request_decommission("QDB-016", "No longer used", "2026-12-31")
    assert any(t["kind"] == "Decommissioning" for t in data_loader.tasks_for(user(SPONSOR1)))
    act_as("Model Sponsor 3")
    with pytest.raises(PermissionError):
        data_store.decide_decommission("QDB-016", True)
    act_as(SPONSOR1)
    with pytest.raises(ValueError, match="reason"):
        data_store.decide_decommission("QDB-016", False)
    data_store.decide_decommission("QDB-016", True, "Agreed")
    m = data_loader.get_model("QDB-016")
    assert m["status"] == "Retired" and m["retired_on"] == "2026-12-31"
    assert data_loader.validation_status(m) == "Retired" and m["next_validation_due"] is None
    act_as("Model Owner 5")
    with pytest.raises(ValueError, match="read-only"):
        data_store.update_model("QDB-016", {"description": "x"})


def test_decommission_needs_a_plan_for_downstream_models(act_as):
    act_as(OWNER1)                                           # QDB-001 feeds the ECL engine and others
    with pytest.raises(ValueError, match="fed by this one"):
        data_store.request_decommission("QDB-001", "Replaced by another model", "2027-03-31")
    data_store.request_decommission("QDB-001", "Replaced by another model", "2027-03-31",
                                    note="ECL engine switches to the new PD model on 1 April")
    data_store.withdraw_decommission("QDB-001")
    assert "decommission" not in repository.get_model("QDB-001")
