"""Phase 3 — KMPI library, quarterly returns, review, tasks."""

from datetime import date

import pytest

import data_loader
import data_store
import kmpi
import repository

OWNER1, DEV1 = "Model Owner 1", "Model Developer 1"
V1, V2 = "Model Validator 1", "Model Validator 2"
ADMIN = "MRM Administrator 1"
Q = "2026-Q3"


# ---------------------------------------------------------------- pure rules
@pytest.mark.parametrize("value,direction,amber,red,expected", [
    (0.60, kmpi.HIGHER, 0.55, 0.45, "Green"),
    (0.50, kmpi.HIGHER, 0.55, 0.45, "Amber"),
    (0.40, kmpi.HIGHER, 0.55, 0.45, "Red"),
    (12, kmpi.LOWER, 15, 25, "Green"),
    (20, kmpi.LOWER, 15, 25, "Amber"),
    (30, kmpi.LOWER, 15, 25, "Red"),
    (1.0, kmpi.RANGE, [0.8, 1.2], [0.65, 1.4], "Green"),
    (1.3, kmpi.RANGE, [0.8, 1.2], [0.65, 1.4], "Amber"),
    (0.6, kmpi.RANGE, [0.8, 1.2], [0.65, 1.4], "Red"),
    (None, kmpi.LOWER, 15, 25, "Not reported"),
])
def test_rag(value, direction, amber, red, expected):
    assert kmpi.rag(value, direction, amber, red) == expected


def test_periods_and_due_dates():
    assert kmpi.reporting_period(date(2026, 10, 3)) == "2026-Q3"
    assert kmpi.reporting_period(date(2026, 1, 15)) == "2025-Q4"
    assert kmpi.due_date("2026-Q3") == date(2026, 10, 30)
    assert kmpi.recent_periods(3, date(2026, 10, 3)) == ["2026-Q1", "2026-Q2", "2026-Q3"]
    assert kmpi.is_due({"frequency": "Annual"}, "2026-Q4") and not kmpi.is_due({"frequency": "Annual"}, "2026-Q3")
    assert kmpi.is_overdue(None, "2026-Q3", date(2026, 11, 1))
    assert not kmpi.is_overdue({"status": "Submitted"}, "2026-Q3", date(2026, 11, 1))


def test_threshold_parsing_and_consistency():
    assert kmpi.parse_threshold("0.8-1.2", kmpi.RANGE) == [0.8, 1.2]
    assert kmpi.parse_threshold("0.5", kmpi.HIGHER) == 0.5
    with pytest.raises(ValueError):
        kmpi.parse_threshold("1.2-0.8", kmpi.RANGE)
    with pytest.raises(ValueError, match="below"):
        kmpi.check_thresholds(kmpi.HIGHER, 0.4, 0.5)


# ---------------------------------------------------------------- library
def test_owner_defines_kmpi_and_threshold_change_needs_reason(act_as):
    act_as("Model Developer 4")  # developer of QDB-013 (in development, no KMPIs yet)
    kid = data_store.save_kmpi("QDB-013", {
        "name": "Combined-grade agreement (%)", "category": "Overrides and use", "unit": "%",
        "description": "Agreement between combined and approved grade",
        "definition": "Obligors whose approved grade equals the combined grade ÷ obligors rated",
        "direction": kmpi.HIGHER, "amber": 80.0, "red": 70.0, "frequency": "Quarterly"})
    assert kid == "KMPI-045"
    with pytest.raises(ValueError, match="reason"):
        data_store.save_kmpi("QDB-013", {"amber": 75.0}, kmpi_id=kid)
    data_store.save_kmpi("QDB-013", {"amber": 75.0}, kmpi_id=kid, reason="Agreed with validator")
    k = next(x for x in repository.list_kmpis() if x["kmpi_id"] == kid)
    assert k["amber"] == 75.0 and k["changes"][-1]["before"] == {"amber": 80.0}
    with pytest.raises(ValueError, match="red threshold"):
        data_store.save_kmpi("QDB-013", {"red": 90.0}, kmpi_id=kid, reason="x")


def test_only_first_line_of_the_model_defines_kmpis(act_as):
    act_as("Model Owner 5")      # owns op-risk, not QDB-001
    with pytest.raises(PermissionError):
        data_store.save_kmpi("QDB-001", {"amber": 0.5}, kmpi_id="KMPI-001", reason="x")
    act_as(V1)
    with pytest.raises(PermissionError):
        data_store.save_kmpi("QDB-001", {"amber": 0.5}, kmpi_id="KMPI-001", reason="x")


# ---------------------------------------------------------------- returns
def _entries(model_id, values, comment=""):
    ks = kmpi.due_kmpis([k for k in repository.list_kmpis() if k["model_id"] == model_id], Q)
    return {k["kmpi_id"]: {"value": v, "comment": comment} for k, v in zip(ks, values)}


def test_draft_then_submit_with_explanations_and_attestation(act_as):
    act_as(DEV1)   # QDB-001 return is a draft with three values missing
    with pytest.raises(ValueError, match="KMPI-003"):
        data_store.save_kmpi_return("QDB-001", Q, {}, submit=True, attest=True)
    # fallback PD exposure 6% is red: needs an explanation
    entries = _entries("QDB-001", [0.62, 1.15, 0, 0.08, 6.0])
    with pytest.raises(ValueError, match="explain the red"):
        data_store.save_kmpi_return("QDB-001", Q, entries, submit=True, attest=True)
    entries["KMPI-005"]["comment"] = "Ratings backlog after CreditLens upgrade"
    with pytest.raises(ValueError, match="attestation"):
        data_store.save_kmpi_return("QDB-001", Q, entries, submit=True)
    assert data_store.save_kmpi_return("QDB-001", Q, entries, submit=True, attest=True) == kmpi.SUBMITTED
    ret = data_loader.kmpi_return("QDB-001", Q)
    assert ret["values"]["KMPI-005"]["rag"] == "Red" and ret["values"]["KMPI-005"]["red"] == 5.0
    with pytest.raises(ValueError, match="no longer"):
        data_store.save_kmpi_return("QDB-001", Q, entries)
    assert repository.verify_audit_chain() == (True, None)


def test_missing_value_allowed_with_reason(act_as):
    act_as(OWNER1)
    entries = _entries("QDB-001", [0.62, 1.15, 0, 0.08, None])
    entries["KMPI-005"]["comment"] = "Rating-date extract not available this quarter"
    data_store.save_kmpi_return("QDB-001", Q, entries, submit=True, attest=True)
    assert data_loader.kmpi_return("QDB-001", Q)["values"]["KMPI-005"]["rag"] == "Not reported"


def test_only_owner_or_developer_enters(act_as):
    for who in (V1, ADMIN, "Model Owner 5"):
        act_as(who)
        with pytest.raises(PermissionError):
            data_store.save_kmpi_return("QDB-001", Q, _entries("QDB-001", [0.6]))


def test_validator_returns_then_reviews_and_raises_finding(act_as):
    act_as(V1)     # QDB-008's validator is Model Validator 2
    with pytest.raises(PermissionError):
        data_store.save_kmpi_return("QDB-008", Q, {})
    act_as(V2)
    with pytest.raises(ValueError, match="corrected"):
        data_store.review_kmpi_return("QDB-008", Q, accept=False)
    data_store.review_kmpi_return("QDB-008", Q, accept=False, comment="Attach the Gini workings")
    assert data_loader.kmpi_return("QDB-008", Q)["status"] == kmpi.RETURNED
    act_as(OWNER1)
    data_store.save_kmpi_return("QDB-008", Q, {}, submit=True, attest=True, note="Workings attached")
    act_as(V2)
    fid = data_store.review_kmpi_return("QDB-008", Q, accept=True, comment="Agree a segment fix",
                                        raise_finding=True, severity="Medium")
    ret = data_loader.kmpi_return("QDB-008", Q)
    assert ret["status"] == kmpi.REVIEWED and ret["finding_id"] == fid
    f = repository.get_request(fid)
    assert f["type"] == "FND" and f["source"] == "Monitoring" and "KMPI-023" in f["description"]


def test_owner_cannot_review_own_return(act_as):
    act_as(OWNER1)
    with pytest.raises(PermissionError):
        data_store.review_kmpi_return("QDB-003", Q, accept=True)


def test_overview_and_tasks(act_as):
    rows = {r["model_id"]: r for r in data_loader.kmpi_overview(Q, today=date(2026, 10, 3))}
    assert rows["QDB-003"]["status"] == kmpi.SUBMITTED and rows["QDB-004"]["status"] == kmpi.RETURNED
    assert "QDB-016" not in rows            # annual KMPIs only — nothing due in Q3
    assert "QDB-013" not in rows            # not in use
    assert not rows["QDB-009"]["overdue"]
    user = lambda n: next(u for u in repository.list_users() if u["name"] == n)  # noqa: E731
    dev_tasks = [t["title"] for t in data_loader.tasks_for(user(DEV1))]
    assert any("Correct and resubmit the 2026-Q3" in t for t in dev_tasks)   # QDB-004 returned
    assert any("Review the 2026-Q3 KMPI return" in t["title"] and t["model_id"] == "QDB-008"
               for t in data_loader.tasks_for(user(V2)))


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
