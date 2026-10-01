from datetime import date

import governance
import tiering


def test_tier_rules():
    assert tiering.compute_tier("High", "Low", "Low")["tier"] == 1        # materiality override
    assert tiering.compute_tier("Low", "Low", "High")["tier"] == 1        # regulatory override
    assert tiering.compute_tier("Medium", "High", "Medium")["tier"] == 1  # composite 7
    assert tiering.compute_tier("Medium", "Medium", "Medium")["tier"] == 2
    assert tiering.compute_tier("Low", "Low", "Medium")["tier"] == 3


def test_frequency_and_approval_body_follow_tier():
    assert governance.validation_frequency(1) == "Annual"
    assert governance.validation_frequency(3) == "Triennial"
    assert governance.approval_body(1) == "Management Risk Committee"
    assert governance.approval_body(2) == "CRO"


def test_validation_dates_derived_from_latest_rated_validation():
    reqs = [
        {"type": "VAL", "status": "Closed", "outcome": "Fit for Purpose", "closed_date": "2024-01-10"},
        {"type": "VAL", "status": "Closed", "outcome": "Approved with Conditions", "closed_date": "2025-03-01"},
        {"type": "MC", "materiality": "Non-material", "status": "Closed", "outcome": "Fit for Purpose", "closed_date": "2026-01-01"},
        {"type": "VAL", "status": "In Progress", "outcome": None, "closed_date": None},
    ]
    d = governance.derive_validation_dates(2, reqs)
    assert d["last_validation"] == "2025-03-01"
    assert d["last_rating"] == "Fit with Conditions"       # legacy label normalised
    assert d["next_validation_due"] == "2027-03-01"        # biennial


def test_validation_status():
    today = date(2026, 9, 30)
    assert governance.validation_status({"last_validation": None, "status": "In Development"}, today) == "Pre-implementation"
    assert governance.validation_status({"last_validation": None, "status": "In Production"}, today) == "Never Validated"
    assert governance.validation_status({"last_validation": "2025-01-01", "next_validation_due": "2026-01-01"}, today) == "Overdue"
    assert governance.validation_status({"last_validation": "2025-01-01", "next_validation_due": "2026-11-01"}, today) == "Due Soon"
    assert governance.validation_status({"last_validation": "2025-01-01", "next_validation_due": "2027-06-01"}, today) == "On Track"


def test_independence_rule():
    m = {"model_id": "X", "owner": "Model Owner 1 (Head of Credit Risk)", "developer": "Model Developer 1 (Risk Analytics)"}
    assert governance.independence_conflict(m, "Model Developer 1 (Risk Analytics)", "VAL")
    assert governance.independence_conflict(m, "Model Owner 1", "MC")
    assert governance.independence_conflict(m, "Model Validator 2 (External validation consultant)", "VAL") is None
    assert governance.independence_conflict(m, "Model Owner 1", "FND") is None  # findings go to owners
