"""One-off generator for the pilot seed data in data/seed/.

It builds QDB's pilot inventory (the IFRS 9 suite, CreditLens rating models,
pricing, the scoring models in development and placeholder models for other
risk types) with a consistent history of validations, changes, findings,
evidence, KMPIs with quarterly returns and audit events.

Model NAMES and their relationships reflect QDB's real landscape; every other
attribute (people, dates, exposures, metrics, findings) is MOCK data to be
edited. After this first generation, edit the JSON files in data/seed/
directly and run `python scripts/reset_db.py` — do not re-run this script
unless you want to discard those edits.

Run from the project root:  python scripts/build_pilot_seed.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tiering import compute_tier  # noqa: E402

SEED = ROOT / "data" / "seed"
random.seed(7)

# ---------------------------------------------------------------- people (mock)
USERS = [
    {"name": "Model Owner 1", "title": "Head of Credit Risk", "role": "LOD1"},
    {"name": "Model Owner 2", "title": "Head of Financial Control", "role": "LOD1"},
    {"name": "Model Owner 3", "title": "Head of Market & Liquidity Risk", "role": "LOD1"},
    {"name": "Model Owner 4", "title": "MLRO / Head of Compliance", "role": "LOD1"},
    {"name": "Model Owner 5", "title": "Head of Operational Risk", "role": "LOD1"},
    {"name": "Model Owner 6", "title": "Head of Pricing & Strategy", "role": "LOD1"},
    {"name": "Model Developer 1", "title": "Risk Analytics", "role": "LOD1"},
    {"name": "Model Developer 2", "title": "Risk Analytics", "role": "LOD1"},
    {"name": "Model Developer 3", "title": "Credit Modelling", "role": "LOD1"},
    {"name": "Model Developer 4", "title": "Data Science", "role": "LOD1"},
    # Sponsors are senior executives; a CRO or CFO approves as the sponsor of their models.
    {"name": "Model Sponsor 1", "title": "Chief Risk Officer", "role": "SPONSOR"},
    {"name": "Model Sponsor 2", "title": "Chief Financial Officer", "role": "SPONSOR"},
    {"name": "Model Sponsor 3", "title": "Head of SME & Corporate Lending", "role": "SPONSOR"},
    {"name": "Model Sponsor 4", "title": "Chief Compliance Officer", "role": "SPONSOR"},
    {"name": "Model User 1", "title": "Credit Underwriting", "role": "VIEWER"},
    {"name": "Model Validator 1", "title": "QDB validator", "role": "LOD2"},
    {"name": "Model Validator 2", "title": "External validation consultant", "role": "LOD2"},
    {"name": "Internal Auditor 1", "title": "Internal Audit", "role": "LOD3"},
    {"name": "MRM Administrator 1", "title": "MRM Administrator", "role": "ADMIN"},
]
TITLE = {u["name"]: u["title"] for u in USERS}
ROLE = {u["name"]: u["role"] for u in USERS}


def label(name: str) -> str:
    return f"{name} ({TITLE[name]})" if name in TITLE else name


HASSAN = "Model Validator 1"
PRIYA = "Model Validator 2"
AUDITOR = "Internal Auditor 1"

FULL_DOCS = [
    "Model Development Document",
    "Methodology Document",
    "Data Quality Assessment",
    "User Guide / Operating Manual",
    "Validation Report",
    "Ongoing Monitoring Plan",
]
CORE_DOCS = [
    "Model Development Document",
    "Methodology Document",
    "Validation Report",
    "Ongoing Monitoring Plan",
]

LOD_BY_OWNER_AREA = {
    "credit": "Credit Risk / Risk Analytics (development, use, monitoring)",
    "finance": "Financial Control (use of ECL results, vendor configuration)",
    "treasury": "Market & Liquidity Risk / Treasury (development, use, monitoring)",
    "oprisk": "Operational Risk (development, use, monitoring)",
    "compliance": "Compliance / MLRO (configuration, use, monitoring)",
    "pricing": "Pricing & Strategy (use), Risk Analytics (development)",
}


def model(
    model_id, name, *, version, risk_type, category, business_line, methodology,
    source, description, owner, developer, validator, sponsor, area, scores,
    tier_rationale, status, approval_date, regulatory_mapping, upstream,
    docs_done, monitoring_metrics, data_sources, platform, usage, users,
    assumptions, limitations, exposure, change_log, audit_reviews=None,
    vendor=None, ai_system=False, qcb_ai_high_risk=None, placeholder=False,
    pending_revalidation=False,
):
    tier = compute_tier(**scores)["tier"]
    checklist = FULL_DOCS if tier in (1, 2) else CORE_DOCS
    return {
        "model_id": model_id,
        "name": name,
        "version": version,
        "risk_type": risk_type,
        "category": category,
        "business_line": business_line,
        "methodology": methodology,
        "source": source,
        "vendor": vendor,
        "description": description,
        "owner": label(owner),
        "developer": developer if developer not in TITLE else label(developer),
        "validator": label(validator) if validator else "Not yet assigned",
        "sponsor": sponsor,
        "lod_mapping": {
            "first_line": LOD_BY_OWNER_AREA[area],
            "second_line": "Model validator — QDB validator or external consultant (independent validation)",
            "third_line": "Internal Audit (periodic review of the model governance framework)",
        },
        "tier_scores": scores,
        "tier_rationale": tier_rationale,
        "status": status,
        "approval_date": approval_date,
        "regulatory_mapping": regulatory_mapping,
        "dependencies": {"upstream": upstream, "downstream": []},
        "documentation": {d: (d in docs_done) for d in checklist},
        "change_log": change_log,
        "audit_reviews": audit_reviews or [],
        "data_sources": data_sources,
        "implementation_platform": platform,
        "usage_frequency": usage,
        "model_users": users,
        "key_assumptions": assumptions,
        "known_limitations": limitations,
        "exposure_covered_qar_mn": exposure,
        "ai_system": ai_system,
        "qcb_ai_high_risk": qcb_ai_high_risk,
        "ai_functional_category": "Credit assessment and decisioning" if ai_system else None,
        "ai_provider_role": "Provider (built by QDB)" if ai_system else None,
        "ai_autonomy": "Human-in-the-loop" if ai_system else None,
        "qcb_approval_status": "Required — not yet sought" if qcb_ai_high_risk else (
            "Not required" if ai_system else None),
        "placeholder": placeholder,
        "pending_revalidation": pending_revalidation,
        "uses": [],
        "tier_override": None,
        "tier_assessment": {
            "scores": dict(scores),
            "rationale": tier_rationale,
            "proposed_by": owner,
            "proposed_on": (approval_date or change_log[0]["date"]),
            "status": "Confirmed",
            "confirmed_by": "MRM Administrator 1",
            "confirmed_on": (approval_date or change_log[0]["date"]),
            "override_tier": None,
            "override_reason": None,
        },
        "tier_history": [],
    }


def chg(date, version, description, author, classification, justification):
    return {
        "date": date, "version": version, "description": description,
        "author": author, "classification": classification,
        "justification": justification,
    }


IFRS9_REG = ["IFRS 9 Financial Instruments", "QCB IFRS 9 implementation instructions", "SR 26-2 (benchmark)"]
CREDIT_REG = ["QCB credit risk instructions", "IFRS 9 (feeds PD)", "SR 26-2 (benchmark)"]

MODELS = [
    # ------------------------------------------------------------ IFRS 9
    model(
        "QDB-001", "IFRS 9 PD Model (point-in-time term structure)",
        version="2.1", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Through-the-cycle rating-to-PD mapping with macro-linked point-in-time adjustment and lifetime term structure",
        description="Converts obligor ratings into 12-month and lifetime point-in-time PDs for ECL, using the scenario-weighted macroeconomic outlook.",
        owner="Model Owner 1", developer="Model Developer 1", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "High", "regulatory_impact": "High"},
        tier_rationale="Drives Stage 1 and Stage 2 ECL across the whole financing book; output feeds the financial statements.",
        status="Approved with Conditions", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG, upstream=["QDB-007", "QDB-008", "QDB-005"],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["PD Backtest Ratio", "PSI"],
        data_sources=["Core banking loan tape", "CreditLens rating history", "Default register"],
        platform="Python (Risk Analytics) feeding the ECL engine", usage="Monthly batch",
        users=["Risk Analytics", "Financial Control"],
        assumptions=["Default definition: 90+ DPD or unlikely to pay, per QDB interpretation", "Rating migration history 2016 onward is representative"],
        limitations=["Low default counts in some sectors; sector PDs pooled", "Point-in-time adjustment not yet back-tested by segment"],
        exposure=9500,
        change_log=[
            chg("2023-11-01", "2.0", "Redevelopment with lifetime term structure and macro-linked PiT adjustment.", "Model Developer 1", "Material", "New methodology."),
            chg("2026-04-02", "2.1", "Annual PD recalibration within approved ranges.", "Model Developer 1", "Non-material", "Parameter refresh within the approved methodology."),
        ],
    ),
    model(
        "QDB-002", "IFRS 9 LGD Model (collateral haircut approach)",
        version="0.9", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Collateral haircut approach; LGD decomposed into cure rate and workout LGD with discounted recoveries",
        description="New LGD model for the SME and corporate book, built from a 10-year account-level loan tape. Replaces the current expert LGD assumptions once validated.",
        owner="Model Owner 1", developer="Model Developer 2", validator=None,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "High", "regulatory_impact": "High"},
        tier_rationale="Will drive ECL for every exposure; feeds the financial statements.",
        status="In Development", approval_date=None,
        regulatory_mapping=IFRS9_REG, upstream=[],
        docs_done=["Data Quality Assessment"],
        monitoring_metrics=[],
        data_sources=["Core banking loan tape 2016–2026", "Collection report", "Collateral register (requested)", "Guarantee register (requested)"],
        platform="Python (Risk Analytics)", usage="Monthly batch (planned)",
        users=["Risk Analytics", "Financial Control"],
        assumptions=["Recovery cash flows discounted at the effective interest rate", "Haircuts by collateral type calibrated on realised sale proceeds"],
        limitations=["Collateral data not in the current extract", "Workout recoveries cannot yet be separated from normal repayments"],
        exposure=9500,
        change_log=[chg("2026-06-15", "0.9", "Development build: default population and recovery curves.", "Model Developer 2", "Material", "New model under development.")],
    ),
    model(
        "QDB-003", "IFRS 9 EAD / CCF Model",
        version="1.2", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Amortisation schedules for term financing; credit conversion factors for undrawn limits",
        description="Projects exposure at default over the lifetime of each facility, including drawdown of undrawn limits on revolving products.",
        owner="Model Owner 1", developer="Model Developer 3", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Feeds ECL directly; regulatory impact drives Tier 1.",
        status="In Production", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG, upstream=[],
        docs_done=FULL_DOCS, monitoring_metrics=["CCF Backtest Ratio"],
        data_sources=["Core banking limits and utilisation", "Repayment schedules"],
        platform="Python (Risk Analytics)", usage="Monthly batch",
        users=["Risk Analytics", "Financial Control"],
        assumptions=["Contractual schedules hold absent prepayment", "CCF stable across the cycle"],
        limitations=["Limited history of drawdowns before default"],
        exposure=3100,
        change_log=[chg("2023-10-20", "1.2", "CCF re-estimation on 2016–2023 data.", "Model Developer 3", "Material", "Parameter re-estimation.")],
    ),
    model(
        "QDB-004", "IFRS 9 Staging Model (SICR)",
        version="1.3", risk_type="IFRS 9 / Provisioning", category="Classification rules",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Rules: 30 DPD backstop, rating-downgrade thresholds, watch-list and restructuring triggers, cure periods",
        description="Allocates each exposure to Stage 1, 2 or 3 using significant-increase-in-credit-risk criteria and default triggers.",
        owner="Model Owner 1", developer="Model Developer 1", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "Low", "regulatory_impact": "High"},
        tier_rationale="Stage allocation decides 12-month vs lifetime ECL for the whole book.",
        status="In Production", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG, upstream=["QDB-001"],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["Stage 2 Ratio (%)", "Staging Override Rate (%)"],
        data_sources=["Core banking DPD", "CreditLens ratings", "Watch-list register"],
        platform="ETL tool feeding the ECL engine", usage="Monthly batch",
        users=["Risk Analytics", "Financial Control", "Credit Administration"],
        assumptions=["Rating downgrade of three notches since origination signals SICR"],
        limitations=["Cure period rule applied but not documented"],
        exposure=9500,
        change_log=[chg("2024-02-10", "1.3", "Added restructuring flag as a Stage 2 trigger.", "Model Developer 1", "Material", "New SICR trigger.")],
    ),
    model(
        "QDB-005", "IFRS 9 Macroeconomic Scenario Weights",
        version="2.0", risk_type="IFRS 9 / Provisioning", category="Forward-looking information",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Five scenarios on Qatar non-oil GDP; density-based likelihood weights centred on the current IMF forecast",
        description="Sets the probability weights of the five macroeconomic scenarios used in the PD model and the ECL engine.",
        owner="Model Owner 1", developer="Model Developer 1", validator=HASSAN,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Weights move ECL for every exposure; expert judgement involved.",
        status="In Production - Approval Pending", approval_date="2024-12-20",
        regulatory_mapping=IFRS9_REG, upstream=[],
        docs_done=["Methodology Document", "Validation Report"],
        monitoring_metrics=["Scenario Forecast Error (%)"],
        data_sources=["IMF World Economic Outlook", "Planning and Statistics Authority GDP releases"],
        platform="Excel workbook (controlled)", usage="Quarterly",
        users=["Risk Analytics", "Financial Control"],
        assumptions=["The IMF forecast is the central (base) scenario", "Scenario anchors are fixed and reviewed annually"],
        limitations=["Weights are a likelihood weighting of fixed states, not integrated probability mass", "Version 2.0 in use before revalidation"],
        exposure=9500, pending_revalidation=True,
        change_log=[
            chg("2024-11-15", "1.0", "First documented version: weights from historical mean.", "Model Developer 1", "Material", "New model."),
            chg("2026-07-20", "2.0", "Redesigned to density-based weights centred on the current IMF forecast; fixes downside weights moving the wrong way.", "Model Developer 1", "Material", "Methodology change."),
        ],
    ),
    model(
        "QDB-006", "ECL Calculation Engine (LIC)",
        version="4.2", risk_type="IFRS 9 / Provisioning", category="Calculation engine",
        business_line="Finance & Risk — IFRS 9", source="Vendor", vendor="LIC",
        methodology="Vendor engine: PD × LGD × EAD, discounted at the effective interest rate and probability-weighted across scenarios",
        description="Web-based vendor engine that computes ECL from the staged data prepared by the ETL tool.",
        owner="Model Owner 2", developer="Vendor (LIC), configured by Risk Analytics", validator=PRIYA,
        sponsor="Model Sponsor 2 (Chief Financial Officer)", area="finance",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Produces the reported ECL figure.",
        status="Approved with Conditions", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG + ["QCB outsourcing instructions"], upstream=["QDB-001", "QDB-002", "QDB-003", "QDB-004", "QDB-005"],
        docs_done=["User Guide / Operating Manual", "Validation Report"],
        monitoring_metrics=["Unexplained ECL Movement (%)"],
        data_sources=["ETL consolidated data template"],
        platform="LIC web tool (vendor-hosted SQL procedures)", usage="Monthly",
        users=["Financial Control", "Risk Analytics"],
        assumptions=["Vendor SQL procedures implement the approved methodology"],
        limitations=["Engine internals are a black box; no independent recalculation yet"],
        exposure=9500,
        change_log=[chg("2023-09-01", "4.2", "Upgrade to vendor release 4.2.", "Model Owner 2", "Material", "Vendor release upgrade.")],
        audit_reviews=[{"date": "2025-09-22", "auditor": label(AUDITOR), "rating": "Needs Improvement", "scope": "Controls over vendor ECL engine configuration and change management."}],
    ),
    # ------------------------------------------------------------ CreditLens ratings
    model(
        "QDB-007", "Obligor Rating Model — Manufacturing (CreditLens)",
        version="3.0", risk_type="Credit Rating & Scoring", category="Rating",
        business_line="SME & Corporate Lending", source="Vendor", vendor="Moody's CreditLens",
        methodology="Vendor scorecard (financial and qualitative factors) calibrated to QDB's manufacturing portfolio",
        description="Assigns obligor risk grades to manufacturing borrowers at origination and annual review.",
        owner="Model Owner 1", developer="Moody's CreditLens (vendor), calibrated by Credit Modelling", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Largest sector in the book; grades feed IFRS 9 PD and approval authority.",
        status="Approved with Conditions", approval_date="2025-12-10",
        regulatory_mapping=CREDIT_REG, upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "User Guide / Operating Manual", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["Gini", "Override Rate (%)"],
        data_sources=["Audited financial statements", "CreditLens spreading", "Relationship manager assessments"],
        platform="Moody's CreditLens", usage="At origination and annual review",
        users=["Credit Underwriting", "Relationship Managers", "Credit Risk"],
        assumptions=["Vendor factor weights hold for Qatari manufacturing SMEs after calibration"],
        limitations=["Override rate above policy threshold", "Thin history for start-ups"],
        exposure=4200,
        change_log=[chg("2025-09-01", "3.0", "Calibration of vendor scorecard to QDB manufacturing default history.", "Model Developer 3", "Material", "Recalibration.")],
        audit_reviews=[{"date": "2026-01-15", "auditor": label(AUDITOR), "rating": "Satisfactory", "scope": "Override governance in the rating process."}],
    ),
    model(
        "QDB-008", "Obligor Rating Model — Services (CreditLens)",
        version="3.0", risk_type="Credit Rating & Scoring", category="Rating",
        business_line="SME & Corporate Lending", source="Vendor", vendor="Moody's CreditLens",
        methodology="Vendor scorecard (financial and qualitative factors) calibrated to QDB's services portfolio",
        description="Assigns obligor risk grades to services-sector borrowers at origination and annual review.",
        owner="Model Owner 1", developer="Moody's CreditLens (vendor), calibrated by Credit Modelling", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Second-largest sector; grades feed IFRS 9 PD and approval authority.",
        status="In Production", approval_date="2025-12-10",
        regulatory_mapping=CREDIT_REG, upstream=[],
        docs_done=FULL_DOCS, monitoring_metrics=["Gini", "PSI"],
        data_sources=["Audited financial statements", "CreditLens spreading", "Relationship manager assessments"],
        platform="Moody's CreditLens", usage="At origination and annual review",
        users=["Credit Underwriting", "Relationship Managers", "Credit Risk"],
        assumptions=["Vendor factor weights hold for Qatari services SMEs after calibration"],
        limitations=["Discriminatory power drifting down since 2025"],
        exposure=2600,
        change_log=[chg("2025-09-01", "3.0", "Calibration of vendor scorecard to QDB services default history.", "Model Developer 3", "Material", "Recalibration.")],
    ),
    # ------------------------------------------------------------ pricing
    model(
        "QDB-009", "Risk-Based Pricing Model",
        version="1.4", risk_type="Pricing", category="Decision support",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Cost-plus pricing: funding cost, operating cost, expected loss (PD × LGD) and capital charge",
        description="Sets the minimum profit rate for new financing from the obligor's risk grade and facility terms.",
        owner="Model Owner 6", developer="Model Developer 2", validator=HASSAN,
        sponsor="Model Sponsor 3 (Chief Executive Officer)", area="pricing",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="Influences margins on new business; no direct regulatory output.",
        status="In Production", approval_date="2022-11-30",
        regulatory_mapping=["QCB pricing and fees instructions", "SR 26-2 (benchmark)"], upstream=["QDB-001", "QDB-002"],
        docs_done=["Model Development Document", "Methodology Document", "User Guide / Operating Manual", "Validation Report"],
        monitoring_metrics=["Realised vs Priced Margin Variance (%)"],
        data_sources=["Treasury funding curve", "Cost allocation", "Rating grade"],
        platform="Excel pricing tool", usage="Per financing proposal",
        users=["Relationship Managers", "Credit Committee"],
        assumptions=["Expected loss uses current IFRS 9 PD and expert LGD"],
        limitations=["Will need recalibration when the new LGD model goes live"],
        exposure=1800,
        change_log=[chg("2024-10-01", "1.4", "Funding curve and cost allocation refresh.", "Model Developer 2", "Non-material", "Parameter refresh.")],
    ),
    # ------------------------------------------------------------ in development
    model(
        "QDB-010", "Transaction Scoring Model (bank-statement based)",
        version="0.5", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME Lending", source="In-house",
        methodology="Gradient-boosted model on cash-flow, turnover and repayment-behaviour features from bank statements",
        description="Scores thin-file SMEs where audited financials are unreliable, using transaction behaviour from bank statements.",
        owner="Model Owner 1", developer="Model Developer 4", validator=PRIYA,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "Medium", "complexity": "High", "regulatory_impact": "Medium"},
        tier_rationale="Machine-learning model that will influence credit decisions for thin-file SMEs.",
        status="In Validation", approval_date=None,
        regulatory_mapping=["QCB Artificial Intelligence Guideline (2024)", "QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Data Quality Assessment"],
        monitoring_metrics=[],
        data_sources=["Bank statements (customer-provided)", "Core banking repayment history"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Statement features are stable across banks and formats"],
        limitations=["Short performance window", "Explainability and bias testing required under the QCB AI Guideline"],
        exposure=600, ai_system=True, qcb_ai_high_risk=True,
        change_log=[chg("2026-08-15", "0.5", "Prototype with 42 engineered features.", "Model Developer 4", "Material", "New model under development.")],
    ),
    model(
        "QDB-011", "Credit Bureau Score — Individual",
        version="1.0", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME Lending", source="In-house",
        methodology="Logistic regression on Qatar Credit Bureau attributes of owners and guarantors",
        description="Scores the individuals behind an SME (owners, guarantors) from their credit bureau records.",
        owner="Model Owner 1", developer="Model Developer 3", validator=HASSAN,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="One input to the combination module; moderate influence on decisions.",
        status="Awaiting Approval", approval_date=None,
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "Validation Report"], monitoring_metrics=[],
        data_sources=["Qatar Credit Bureau — individual reports"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Bureau coverage of owners is sufficient"],
        limitations=["Bureau history for expatriate owners is limited"],
        exposure=600,
        change_log=[chg("2026-07-01", "0.3", "Variable selection on bureau attributes.", "Model Developer 3", "Material", "New model under development."),
                    chg("2026-08-25", "1.0", "Final model submitted for validation.", "Model Developer 3", "Material", "First production version.")],
    ),
    model(
        "QDB-012", "Credit Bureau Score — Corporate",
        version="1.0", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Logistic regression on Qatar Credit Bureau company attributes",
        description="Scores the borrowing company from its credit bureau record.",
        owner="Model Owner 1", developer="Model Developer 3", validator=HASSAN,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="One input to the combination module; moderate influence on decisions.",
        status="Approved — Awaiting Implementation", approval_date="2026-09-25",
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "User Guide / Operating Manual", "Validation Report"], monitoring_metrics=[],
        data_sources=["Qatar Credit Bureau — company reports"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Bureau coverage of companies is sufficient"],
        limitations=["New companies have no bureau history"],
        exposure=1500,
        change_log=[chg("2026-07-01", "0.3", "Variable selection on bureau attributes.", "Model Developer 3", "Material", "New model under development."),
                    chg("2026-08-15", "1.0", "Final model submitted for validation.", "Model Developer 3", "Material", "First production version.")],
    ),
    model(
        "QDB-013", "Combination Module (rating, bureau and transaction scores)",
        version="0.2", risk_type="Credit Rating & Scoring", category="Decision",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Weighted combination of rating, bureau and transaction scores into a final grade, with an override matrix",
        description="Combines the CreditLens rating, the two bureau scores and the transaction score into one final risk grade for decisioning.",
        owner="Model Owner 1", developer="Model Developer 4", validator=None,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="credit",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="Will set the final grade used for approval authority across SME lending.",
        status="In Development", approval_date=None,
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"],
        upstream=["QDB-007", "QDB-008", "QDB-010", "QDB-011", "QDB-012"],
        docs_done=[], monitoring_metrics=[],
        data_sources=["Outputs of upstream models"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Component scores are complementary"],
        limitations=["Weights are expert-set until outcome data accumulates"],
        exposure=4500,
        change_log=[chg("2026-08-20", "0.2", "Initial weighting scheme agreed with Credit.", "Model Developer 4", "Material", "New model under development.")],
    ),
    # ------------------------------------------------------------ placeholders for other risk types
    model(
        "QDB-014", "Liquidity Stress Testing Model",
        version="1.1", risk_type="Market & Liquidity Risk", category="Projection",
        business_line="Treasury / ALM", source="In-house",
        methodology="Cash-flow projection under idiosyncratic and market-wide stress scenarios",
        description="Placeholder record — projects the survival horizon under liquidity stress.",
        owner="Model Owner 3", developer="Treasury analytics", validator=HASSAN,
        sponsor="Model Sponsor 2 (Chief Financial Officer)", area="treasury",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Feeds regulatory liquidity reporting.",
        status="In Production", approval_date="2021-06-30",
        regulatory_mapping=["QCB liquidity instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "Validation Report"],
        monitoring_metrics=["LCR Forecast Error (%)"],
        data_sources=["ALM system", "Treasury positions"], platform="Excel / ALM system", usage="Monthly",
        users=["Treasury", "ALCO"],
        assumptions=["Behavioural run-off rates per product"], limitations=["Run-off assumptions not evidenced"],
        exposure=3000, placeholder=True,
        change_log=[chg("2021-05-01", "1.1", "Scenario update.", "Model Owner 3", "Non-material", "Scenario parameters refresh.")],
    ),
    model(
        "QDB-015", "IRRBB Model (EVE and NII sensitivity)",
        version="1.0", risk_type="Market & Liquidity Risk", category="Measurement",
        business_line="Treasury / ALM", source="In-house",
        methodology="Repricing gap with standard rate shocks for economic value and net profit income",
        description="Placeholder record — measures interest (profit) rate risk in the banking book.",
        owner="Model Owner 3", developer="Treasury analytics", validator=HASSAN,
        sponsor="Model Sponsor 2 (Chief Financial Officer)", area="treasury",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="Internal limits with regulatory visibility.",
        status="In Production", approval_date="2022-03-15",
        regulatory_mapping=["QCB IRRBB instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["NII Forecast Error (%)"],
        data_sources=["ALM system"], platform="ALM system", usage="Monthly",
        users=["Treasury", "ALCO"],
        assumptions=["Repricing buckets per product"], limitations=["No behavioural prepayment model"],
        exposure=2000, placeholder=True,
        change_log=[chg("2022-02-01", "1.0", "First version.", "Model Owner 3", "Material", "New model.")],
    ),
    model(
        "QDB-016", "Operational Risk Scenario Analysis",
        version="1.0", risk_type="Operational & Non-Financial Risk", category="Assessment",
        business_line="Operational Risk", source="In-house",
        methodology="Expert-elicited frequency and severity per scenario, aggregated to an annual loss estimate",
        description="Placeholder record — estimates severe but plausible operational losses for risk appetite.",
        owner="Model Owner 5", developer="Operational Risk team", validator=HASSAN,
        sponsor="Model Sponsor 1 (Head of SME & Corporate Lending)", area="oprisk",
        scores={"materiality": "Low", "complexity": "Low", "regulatory_impact": "Medium"},
        tier_rationale="Management information and risk appetite only.",
        status="In Production", approval_date="2023-02-28",
        regulatory_mapping=["QCB operational risk instructions"], upstream=[],
        docs_done=["Methodology Document", "Validation Report"],
        monitoring_metrics=[],
        data_sources=["Loss event database", "Workshop outputs"], platform="Excel", usage="Annual",
        users=["Operational Risk", "Management Risk Committee"],
        assumptions=["Workshop estimates are unbiased"], limitations=["Few internal loss events"],
        exposure=0, placeholder=True,
        change_log=[chg("2023-01-15", "1.0", "First version.", "Model Owner 5", "Material", "New model.")],
    ),
    model(
        "QDB-017", "AML Customer Risk Rating",
        version="2.0", risk_type="Operational & Non-Financial Risk", category="Rating",
        business_line="Compliance", source="Vendor", vendor="AML platform vendor",
        methodology="Weighted risk factors (customer type, geography, product, channel) with vendor defaults",
        description="Placeholder record — rates customers for AML/CFT due diligence under Law No. 20 of 2019.",
        owner="Model Owner 4", developer="Vendor, configured by Compliance", validator=PRIYA,
        sponsor="Model Sponsor 4 (Chief Compliance Officer)", area="compliance",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Statutory AML/CFT compliance.",
        status="Approved with Conditions", approval_date="2024-06-30",
        regulatory_mapping=["Qatar AML/CFT Law No. 20 of 2019", "QCB AML/CFT instructions"], upstream=[],
        docs_done=["User Guide / Operating Manual", "Validation Report"],
        monitoring_metrics=["High-Risk Customer Share (%)"],
        data_sources=["Customer master", "Transaction monitoring alerts"], platform="AML platform", usage="Daily",
        users=["Compliance"],
        assumptions=["Vendor factor weights suit QDB's customer base"], limitations=["Weights not calibrated to QDB"],
        exposure=0, placeholder=True,
        change_log=[chg("2024-05-01", "2.0", "Vendor upgrade.", "Model Owner 4", "Material", "Vendor release.")],
    ),
    model(
        "QDB-018", "Legacy SME Rating Scorecard (pre-CreditLens)",
        version="3.2", risk_type="Credit Rating & Scoring", category="Rating",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Expert-weighted scorecard of financial and qualitative factors",
        description="Obligor rating used before the CreditLens sector models; retired when they went live.",
        owner="Model Owner 1", developer="Model Developer 3", validator=HASSAN,
        sponsor="", area="credit",
        scores={"materiality": "High", "complexity": "Low", "regulatory_impact": "Medium"},
        tier_rationale="Drove obligor grades for the whole SME book.",
        status="In Production", approval_date="2019-05-30",
        regulatory_mapping=CREDIT_REG, upstream=[],
        docs_done=["Model Development Document", "Methodology Document", "Validation Report"],
        monitoring_metrics=[],
        data_sources=["Financial statements", "Relationship manager questionnaire"], platform="Excel",
        usage="Per credit application", users=["Credit Underwriting"],
        assumptions=["Expert weights reflect default drivers"], limitations=["Not statistically calibrated"],
        exposure=0,
        change_log=[chg("2019-03-01", "3.2", "Last recalibration of weights.", "Model Developer 3", "Material",
                        "Annual review.")],
    ),
]

# ---------------------------------------------------------------- uses (mock)
USES = {
    "QDB-001": [("Stage 1 and 2 ECL", "Finance & Risk", "12-month and lifetime PD in the monthly ECL run"),
                   ("Risk-based pricing", "SME & Corporate Lending", "Expected-loss component of the profit rate")],
    "QDB-002": [("Stage 1–3 ECL", "Finance & Risk", "LGD in the monthly ECL run (planned)")],
    "QDB-003": [("Stage 1–3 ECL", "Finance & Risk", "Lifetime EAD in the monthly ECL run")],
    "QDB-004": [("Stage allocation", "Finance & Risk", "12-month vs lifetime ECL for each exposure")],
    "QDB-005": [("Forward-looking ECL", "Finance & Risk", "Probability weights of the five scenarios")],
    "QDB-006": [("Reported ECL", "Financial Control", "Monthly impairment figure for the financial statements")],
    "QDB-007": [("Credit approval", "SME & Corporate Lending", "Obligor grade drives approval authority"),
                   ("IFRS 9 PD", "Finance & Risk", "Grade mapped to PD")],
    "QDB-008": [("Credit approval", "SME & Corporate Lending", "Obligor grade drives approval authority"),
                   ("IFRS 9 PD", "Finance & Risk", "Grade mapped to PD")],
    "QDB-009": [("Pricing of new financing", "SME & Corporate Lending", "Minimum profit rate per proposal")],
    "QDB-010": [("Thin-file SME assessment", "SME Lending", "Score for SMEs without reliable financials (planned)")],
    "QDB-011": [("Owner / guarantor assessment", "SME Lending", "Bureau score input to the combination module (planned)")],
    "QDB-012": [("Company bureau assessment", "SME & Corporate Lending", "Bureau score input to the combination module (planned)")],
    "QDB-013": [("Final risk grade", "SME & Corporate Lending", "Combined grade for decisioning (planned)")],
    "QDB-014": [("Liquidity risk appetite", "Treasury / ALCO", "Survival horizon under stress")],
    "QDB-015": [("IRRBB limits", "Treasury / ALCO", "EVE and NII sensitivity against limits")],
    "QDB-016": [("Operational risk appetite", "Operational Risk", "Severe-but-plausible annual loss")],
    "QDB-017": [("Customer due diligence", "Compliance", "Customer risk rating sets the due-diligence level")],
}
for m in MODELS:
    status = "Planned" if m["status"] == "In Development" else "Active"
    m["uses"] = [{"use": u, "business_area": a, "decision": d, "status": status}
                 for u, a, d in USES.get(m["model_id"], [])]

# ---------------------------------------------------------------- EUC / AI tool register (mock)
TOOLS = [
    {
        "tool_id": "QDB-EUC-001", "name": "ECL ETL consolidation workbook",
        "classification": "EUC tool",
        "description": "Prepares and stages the consolidated data template consumed by the ECL engine.",
        "owner": label("Model Owner 2"), "business_area": "Financial Control",
        "platform": "Excel with macros", "materiality": "High",
        "controls": "Version control, input reconciliation to the general ledger, second-person review",
        "ai_system": False, "related_models": ["QDB-006"],
    },
    {
        "tool_id": "QDB-EUC-002", "name": "Provision journal calculator",
        "classification": "EUC tool",
        "description": "Turns ECL results into general-ledger journal entries by product and branch.",
        "owner": label("Model Owner 2"), "business_area": "Financial Control",
        "platform": "Excel", "materiality": "Medium",
        "controls": "Totals reconciled to ECL engine output",
        "ai_system": False, "related_models": ["QDB-006"],
    },
    {
        "tool_id": "QDB-AI-001", "name": "Financial statement spreading (OCR)",
        "classification": "AI tool (non-model)",
        "description": "Reads uploaded financial statements and pre-fills CreditLens spreads for analyst review.",
        "owner": label("Model Owner 1"), "business_area": "Credit Underwriting",
        "platform": "Moody's CreditLens add-on", "materiality": "Medium",
        "controls": "Analyst reviews every spread before rating",
        "ai_system": True, "qcb_ai_high_risk": False,
        "ai_functional_category": "Document processing",
        "ai_provider_role": "User / deployer (third-party system)",
        "ai_autonomy": "Human-in-the-loop", "qcb_approval_status": "Not required",
        "related_models": ["QDB-007", "QDB-008"],
    },
    {
        "tool_id": "QDB-NM-001", "name": "Repayment schedule calculator",
        "classification": "Not a model",
        "description": "Produces instalment schedules from contract terms; no estimation.",
        "owner": label("Model Developer 3"), "business_area": "Credit Administration",
        "platform": "Core banking", "materiality": "Low", "controls": "Core banking controls",
        "ai_system": False, "related_models": [],
    },
]
_ANSWERS = {
    "EUC tool": {"quantitative": True, "theory": False, "deterministic_only": True, "learns_from_data": False, "decision_use": True},
    "AI tool (non-model)": {"quantitative": False, "theory": False, "deterministic_only": False, "learns_from_data": True, "decision_use": True},
    "Not a model": {"quantitative": True, "theory": False, "deterministic_only": True, "learns_from_data": False, "decision_use": False},
}
for t in TOOLS:
    t["identification_answers"] = _ANSWERS[t["classification"]]
    t["registered_by"] = "MRM Administrator 1"
    t["registered_on"] = "2026-09-15"
    t["last_reviewed"] = "2026-09-15"

# downstream links mirror upstream
BY_ID = {m["model_id"]: m for m in MODELS}
for m in MODELS:
    for up in m["dependencies"]["upstream"]:
        BY_ID[up]["dependencies"]["downstream"].append(m["model_id"])

# change ids
n = 0
for m in sorted(MODELS, key=lambda x: x["model_id"]):
    for c in sorted(m["change_log"], key=lambda c: c["date"]):
        n += 1
        c["change_id"] = f"CHG-{n:03d}"
a = 0
for m in MODELS:
    for r in m["audit_reviews"]:
        a += 1
        r["audit_id"] = f"AUD-{a:03d}"

# ---------------------------------------------------------------- requests
REQUESTS: list[dict] = []
COUNTERS = {"VAL": 0, "MC": 0, "FND": 0}


def req(rtype, model_id, *, title, description, initiated_by, assigned_to, created,
        status, closed=None, outcome=None, severity=None, remediation=None, due=None,
        source=None, materiality=None, subtype=None, tests=None, thread=None):
    COUNTERS[rtype] += 1
    rid = f"{rtype}-{COUNTERS[rtype]:03d}"
    entries = []
    for i, (d, who, text) in enumerate(thread or [(created, initiated_by, description)], start=1):
        entries.append({
            "response_id": f"{rid}-R{i}", "date": d, "author": who,
            "role": ROLE.get(who, "LOD1"), "text": text, "evidence_ids": [],
        })
    r = {
        "request_id": rid, "type": rtype, "model_id": model_id, "status": status,
        "initiated_by": initiated_by, "initiated_by_role": ROLE[initiated_by],
        "assigned_to": label(assigned_to) if assigned_to in TITLE else assigned_to,
        "title": title, "description": description, "created_date": created,
        "closed_date": closed, "due_date": due, "outcome": outcome, "severity": severity,
        "remediation": remediation, "source": source, "materiality": materiality,
        "validation_subtype": subtype, "tests": tests or [], "thread": entries,
    }
    REQUESTS.append(r)
    return r


T_PD = ["Discriminatory power (Gini/KS)", "Calibration accuracy / backtest", "Population stability (PSI)", "Sensitivity analysis", "Documentation review"]
T_RULES = ["Implementation testing", "Sensitivity analysis", "Documentation review"]


def closed_val(model_id, date, subtype, outcome, validator, tests, summary):
    return req("VAL", model_id, title=f"{subtype} validation", description=summary,
               initiated_by=validator, assigned_to=validator, created=date, status="Closed",
               closed=date, outcome=outcome, source="Validation", subtype=subtype, tests=tests,
               thread=[(date, validator, summary), (date, validator, f"[Closure] Validation complete — rating: {outcome}.")])


closed_val("QDB-001", "2023-12-05", "Initial", "Fit for Purpose", PRIYA, T_PD, "Initial validation of the redeveloped PD model.")
closed_val("QDB-001", "2025-10-15", "Periodic", "Fit with Conditions", PRIYA, T_PD, "Annual validation: calibration adequate; PiT adjustment not back-tested by segment.")
closed_val("QDB-003", "2025-10-15", "Periodic", "Fit for Purpose", PRIYA, ["Calibration accuracy / backtest", "Implementation testing", "Documentation review"], "Annual validation of EAD/CCF.")
closed_val("QDB-004", "2025-10-15", "Periodic", "Fit for Purpose", PRIYA, T_RULES, "Annual validation of staging rules.")
closed_val("QDB-005", "2024-12-10", "Initial", "Fit with Conditions", HASSAN, ["Scenario testing", "Sensitivity analysis", "Benchmarking"], "Initial validation of scenario weights v1.0.")
closed_val("QDB-006", "2024-11-05", "Periodic", "Fit with Conditions", PRIYA, ["Implementation testing", "Benchmarking", "Documentation review"], "Annual review of the vendor ECL engine; no independent recalculation possible.")
closed_val("QDB-007", "2025-11-20", "Initial", "Fit with Conditions", PRIYA, T_PD + ["Override analysis"], "Validation of CreditLens manufacturing calibration.")
closed_val("QDB-008", "2025-11-20", "Initial", "Fit for Purpose", PRIYA, T_PD, "Validation of CreditLens services calibration.")
closed_val("QDB-009", "2024-11-10", "Periodic", "Fit for Purpose", HASSAN, ["Implementation testing", "Sensitivity analysis", "Benchmarking"], "Biennial review of the pricing model.")
closed_val("QDB-014", "2023-12-05", "Periodic", "Fit with Conditions", HASSAN, ["Scenario testing", "Documentation review"], "Placeholder — periodic review of liquidity stress testing.")
closed_val("QDB-015", "2025-02-20", "Periodic", "Fit for Purpose", HASSAN, ["Implementation testing", "Sensitivity analysis"], "Placeholder — biennial review of IRRBB.")
closed_val("QDB-016", "2024-03-15", "Periodic", "Fit for Purpose", HASSAN, ["Documentation review"], "Placeholder — triennial review of scenario analysis.")
closed_val("QDB-017", "2025-05-18", "Periodic", "Fit with Conditions", PRIYA, ["Data quality review", "Sensitivity analysis"], "Placeholder — annual review of AML customer risk rating.")

req("VAL", "QDB-010", title="Initial validation request", status="In Progress",
    description="Requesting initial validation of the transaction scoring model before pilot use, including bias and explainability testing under the QCB AI Guideline.",
    initiated_by="Model Developer 4", assigned_to=PRIYA, created="2026-09-01", source="LoD1 Request", subtype="Initial",
    thread=[("2026-09-01", "Model Developer 4", "Requesting initial validation of the transaction scoring model before pilot use, including bias and explainability testing under the QCB AI Guideline."),
            ("2026-09-08", PRIYA, "Accepted. Please upload the development document, feature list and the out-of-time results. I will send the information request list this week.")])
req("VAL", "QDB-006", title="Periodic validation (overdue)", status="Open",
    description="Periodic validation overdue since November 2025. Scope to include an independent recalculation of ECL for a sample portfolio.",
    initiated_by=HASSAN, assigned_to=PRIYA, created="2026-09-10", source="Validation", subtype="Periodic")

req("MC", "QDB-005", title="Material change v2.0 — density-based weights", status="In Progress",
    description="Weights redesigned around the current IMF forecast. Version 2.0 used for the June 2026 ECL run pending revalidation.",
    initiated_by="Model Developer 1", assigned_to=HASSAN, created="2026-07-20", source="Model Change", materiality="Material",
    thread=[("2026-07-20", "Model Developer 1", "Weights redesigned around the current IMF forecast. Version 2.0 used for the June 2026 ECL run pending revalidation."),
            ("2026-07-28", HASSAN, "Received. Please attach the design note and the comparison of v1 and v2 weights across the last four quarters."),
            ("2026-08-04", "Model Developer 1", "Design note attached. Comparison to follow with Q3 data.")])
req("MC", "QDB-001", title="Non-material change v2.1 — annual recalibration", status="Closed",
    description="Annual recalibration within approved ranges.", initiated_by="Model Developer 1", assigned_to=PRIYA,
    created="2026-04-02", closed="2026-04-20", outcome="Fit for Purpose", source="Model Change", materiality="Non-material",
    thread=[("2026-04-02", "Model Developer 1", "Annual recalibration within approved ranges."),
            ("2026-04-20", PRIYA, "[Closure] Confirmed non-material; parameters within approved ranges.")])

req("FND", "QDB-001", title="Point-in-time adjustment not back-tested by segment", status="Open", severity="Medium",
    description="The macro-linked PiT adjustment is only back-tested at portfolio level.",
    remediation="Back-test the PiT adjustment for each rating segment and document results.",
    initiated_by=PRIYA, assigned_to="Model Developer 1", created="2025-10-15", due="2026-04-15", source="Validation")
fnd_ecl = req("FND", "QDB-006", title="No independent recalculation of vendor ECL engine", status="Open", severity="High",
    description="ECL produced by the vendor engine cannot be reproduced; internals are not documented.",
    remediation="Build an independent recalculation for a sample portfolio and obtain vendor documentation of the SQL procedures.",
    initiated_by=PRIYA, assigned_to="Model Owner 2", created="2024-11-05", due="2025-05-05", source="Validation",
    thread=[("2024-11-05", PRIYA, "ECL produced by the vendor engine cannot be reproduced; internals are not documented."),
            ("2025-04-20", "Model Owner 2", "Vendor documentation requested; recalculation plan attached."),
            ("2026-03-02", "Model Developer 2", "Python recalculation covers Stage 1 and 2; Stage 3 pending.")])
req("FND", "QDB-004", title="Cure period rule not documented", status="Open", severity="Low",
    description="The 3-month cure period for exits from Stage 2 is applied in the ETL but not written in the methodology.",
    remediation="Document the cure period rule and its rationale in the methodology document.",
    initiated_by=PRIYA, assigned_to="Model Developer 1", created="2025-10-15", due="2026-10-15", source="Validation")
fnd_cr = req("FND", "QDB-007", title="Override rate above policy threshold", status="Open", severity="Medium",
    description="Rating overrides at 24% against a 15% policy threshold.",
    remediation="Analyse override reasons; tighten override governance; recalibrate qualitative factors if needed.",
    initiated_by=PRIYA, assigned_to="Model Owner 1", created="2025-11-20", due="2026-05-20", source="Validation",
    thread=[("2025-11-20", PRIYA, "Rating overrides at 24% against a 15% policy threshold."),
            ("2026-07-15", "Model Owner 1", "Q2 2026 override extract attached; overrides reasons being coded.")])
req("FND", "QDB-005", title="Downside weights moved in the wrong direction", status="Closed", severity="Medium",
    description="Under v1.0, a weaker GDP forecast lowered the downside scenario weight.",
    remediation="Redesign the weighting so weights respond in the expected direction.",
    initiated_by=HASSAN, assigned_to="Model Developer 1", created="2024-12-10", due="2025-12-10", closed="2026-07-25",
    outcome="Closed", source="Validation",
    thread=[("2024-12-10", HASSAN, "Under v1.0, a weaker GDP forecast lowered the downside scenario weight."),
            ("2026-07-20", "Model Developer 1", "Fixed by the v2.0 density-based redesign (see MC-001)."),
            ("2026-07-25", HASSAN, "[Closure] Verified on the v2.0 workbook: weights now move in the expected direction.")])
req("FND", "QDB-017", title="Risk factor weights not calibrated to QDB customers", status="Open", severity="High",
    description="Placeholder — vendor default weights used without calibration.",
    remediation="Calibrate factor weights to QDB's customer base and document the rationale.",
    initiated_by=PRIYA, assigned_to="Model Owner 4", created="2025-05-18", due="2025-11-18", source="Validation")
req("FND", "QDB-014", title="Behavioural run-off assumptions not evidenced", status="Open", severity="Medium",
    description="Placeholder — run-off rates are expert-set with no supporting analysis.",
    remediation="Evidence run-off rates from deposit history.",
    initiated_by=HASSAN, assigned_to="Model Owner 3", created="2023-12-05", due="2024-06-05", source="Validation")
req("FND", "QDB-002", title="Collateral register not available for LGD development", status="Open", severity="Medium",
    description="LGD development cannot calibrate haircuts without collateral values and allocation to facilities.",
    remediation="Deliver a collateral register extract (type, value, valuation date, allocation) to Risk Analytics.",
    initiated_by=AUDITOR, assigned_to="Model Owner 1", created="2026-08-20", due="2027-02-20", source="Internal Audit")
req("FND", "QDB-008", title="Sector mapping table not version-controlled", status="Closed", severity="Low",
    description="The mapping of economic activity codes to rating templates is kept in an uncontrolled spreadsheet.",
    remediation="Move the mapping under version control.", initiated_by=PRIYA, assigned_to="Model Developer 3",
    created="2025-11-20", due="2026-05-20", closed="2026-02-10", outcome="Closed", source="Validation",
    thread=[("2025-11-20", PRIYA, "The mapping of economic activity codes to rating templates is kept in an uncontrolled spreadsheet."),
            ("2026-02-01", "Model Developer 3", "Mapping now in the controlled repository."),
            ("2026-02-10", PRIYA, "[Closure] Verified.")])

v_cbi = closed_val("QDB-011", "2026-09-20", "Initial", "Fit with Conditions", HASSAN, T_PD,
                  "Initial validation of the individual bureau score.")
v_cbc = closed_val("QDB-012", "2026-09-10", "Initial", "Fit for Purpose", HASSAN, T_PD,
                   "Initial validation of the corporate bureau score.")
req("FND", "QDB-011", title="Coverage of expatriate owners not tested", status="Open", severity="Low",
    description="Discrimination was not tested separately for owners with short bureau histories.",
    remediation="Test performance on owners with under 24 months of bureau history.",
    initiated_by=HASSAN, assigned_to="Model Developer 3", created="2026-09-20", due="2027-03-20", source="Validation")


def engagement(stage, scope=None, tests=None, declared=None, irs=None, draft=None,
               owner_review=None, signed=None):
    return {
        "stage": stage, "scope": scope, "planned_tests": tests or [],
        "independence": {"declared_by": declared[0], "on": declared[1]} if declared else None,
        "info_requests": [
            {"ir_id": f"IR-{i}", "item": it, "owner": label(ow), "due": due, "status": st_,
             "response": resp, "answered_by": ow if resp else None,
             "answered_on": ans_on, "review_comment": None, "evidence_ids": []}
            for i, (it, ow, due, st_, resp, ans_on) in enumerate(irs or [], start=1)
        ],
        "draft": draft, "owner_review": owner_review, "signed_off": signed,
    }


val_tx = next(r for r in REQUESTS if r["model_id"] == "QDB-010" and r["type"] == "VAL")
val_tx["engagement"] = engagement(
    "Fieldwork", "Initial validation: conceptual soundness, feature engineering, out-of-time "
    "performance, bias and explainability tests required by the QCB AI Guideline.",
    T_PD + ["Bias and explainability testing"], (PRIYA, "2026-09-08"), [
        ("Model development document", "Model Developer 4", "2026-09-15", "Answered",
         "Development document v0.5 uploaded.", "2026-09-12"),
        ("Feature list with definitions and data lineage", "Model Developer 4", "2026-09-22", "Answered",
         "Feature dictionary attached (42 features).", "2026-09-24"),
        ("Out-of-time results on the 2025 cohort", "Model Developer 4", "2026-10-06", "Open", None, None),
        ("Bias test by sector and company age", "Model Developer 4", "2026-10-13", "Open", None, None),
    ])
mc_sw = next(r for r in REQUESTS if r["model_id"] == "QDB-005" and r["type"] == "MC")
mc_sw["engagement"] = engagement(
    "Fieldwork", "Revalidation of the v2.0 density-based weighting: design, sensitivity to the "
    "IMF forecast and the anchors, comparison with v1.0 over four quarters.",
    ["Scenario testing", "Sensitivity analysis", "Benchmarking"], (HASSAN, "2026-07-28"), [
        ("Design note for v2.0", "Model Developer 1", "2026-08-05", "Answered",
         "Design note attached to the thread.", "2026-08-04"),
        ("v1.0 vs v2.0 weights over the last four quarters", "Model Developer 1", "2026-09-30", "Open", None, None),
    ])
val_ecl = next(r for r in REQUESTS if r["model_id"] == "QDB-006" and r["type"] == "VAL" and r["status"] == "Open")
val_ecl["engagement"] = engagement("Scoping")
for v, rating, on, rev in ((v_cbi, "Fit with Conditions", "2026-09-20", "2026-09-17"),
                           (v_cbc, "Fit for Purpose", "2026-09-10", "2026-09-08")):
    v["engagement"] = engagement(
        "Signed off", "Initial validation before first use.", T_PD, (HASSAN, "2026-08-28"),
        [("Development document and code", "Model Developer 3", "2026-09-01", "Answered",
          "Uploaded.", "2026-08-31")],
        draft={"rating": rating, "summary": "Draft issued.", "issued_by": HASSAN, "issued_on": "2026-09-05"},
        owner_review={"comments": "No factual-accuracy comments.", "by": "Model Owner 1", "on": rev},
        signed={"rating": rating, "by": HASSAN, "on": on},
    )

REQ_BY_ID = {r["request_id"]: r for r in REQUESTS}

# ---------------------------------------------------------------- approvals and implementation (mock)
from datetime import date as _date, timedelta as _td  # noqa: E402

# Sponsor of each model (who approves it after its owner).
SPONSOR_BY_MODEL = {
    **{f"QDB-{i:03d}": "Model Sponsor 1" for i in (1, 2, 3, 4, 5, 7, 8, 16, 18)},   # CRO
    **{f"QDB-{i:03d}": "Model Sponsor 2" for i in (6, 14, 15)},                 # CFO
    **{f"QDB-{i:03d}": "Model Sponsor 3" for i in (9, 10, 11, 12, 13)},         # business
    "QDB-017": "Model Sponsor 4",                                               # compliance
}
for m in MODELS:
    m["sponsor"] = label(SPONSOR_BY_MODEL[m["model_id"]])
_apr = 0
for m in sorted(MODELS, key=lambda x: x["approval_date"] or "9999"):
    m["approvals"] = []
    m["implementation"] = []
    if not m["approval_date"]:
        continue
    _apr += 1
    tier = compute_tier(**m["tier_scores"])["tier"]
    with_cond = m["status"] in ("Approved with Conditions", "Approved — Awaiting Implementation") \
        or m["model_id"] == "QDB-005"
    conditions = []
    if m["model_id"] == "QDB-012":
        conditions = [{"cond_id": "C-1", "condition": "KMPIs and thresholds agreed with the validator before go-live",
                       "owner": label("Model Owner 1"), "due": "2026-10-31", "status": "Open", "set_by": "Model sponsor",
                       "note": None, "met_on": None, "verified_by": None, "verified_on": None}]
    elif with_cond:
        conditions = [{"cond_id": "C-1", "condition": "Remediate the validation findings by their due dates",
                       "owner": m["owner"], "due": None, "status": "Open", "set_by": "Model owner", "note": None,
                       "met_on": None, "verified_by": None, "verified_on": None}]
    decision = "Approved with conditions" if conditions else "Approved"
    m["approvals"].append({
        "approval_id": f"APR-{_apr:03d}", "date": m["approval_date"], "body": "Model owner and model sponsor",
        "decision": decision,
        "conditions": conditions, "version": "1.0" if m["model_id"] == "QDB-005" else m["version"],
        "signatures": [
            {"as": "Model owner", "by": m["owner"], "on": m["approval_date"],
             "decision": decision if conditions and conditions[0]["set_by"] == "Model owner" else "Approved",
             "comment": None},
            {"as": "Model sponsor", "by": m["sponsor"], "on": m["approval_date"], "decision": decision,
             "comment": None},
        ],
        "recorded_by": m["sponsor"],
        "comment": None,
    })
    if m["status"] != "Approved — Awaiting Implementation":
        m["implementation"].append({
            "version": "1.0" if m["model_id"] == "QDB-005" else m["version"], "verified_by": m["validator"] if m["validator"] != "Not yet assigned" else label(HASSAN),
            "verified_on": (_date.fromisoformat(m["approval_date"]) + _td(days=7)).isoformat(),
            "note": "Deployed version matches the validated version (backfilled).",
        })

# ---------------------------------------------------------------- evidence (placeholder files)
EVIDENCE = []


def evidence(model_id, linked_type, linked_id, filename, category, description, who, when, text, doc_type=None):
    eid = f"EV-{len(EVIDENCE) + 1:03d}"
    stamp = when.replace("-", "").replace(":", "").replace("T", "")
    stored = f"{model_id}/{stamp}_{filename}"
    path = SEED / "evidence" / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n\n(Placeholder evidence file for the PoC.)\n", encoding="utf-8")
    e = {
        "evidence_id": eid, "model_id": model_id, "linked_type": linked_type, "linked_id": linked_id,
        "filename": filename, "stored_path": stored, "category": category, "description": description,
        "uploaded_by": who, "role": ROLE[who], "uploaded_at": when,
    }
    if doc_type:
        e["doc_type"] = doc_type
    EVIDENCE.append(e)
    return eid


mc = next(r for r in REQUESTS if r["model_id"] == "QDB-005" and r["type"] == "MC")
eid = evidence("QDB-005", "request_response", mc["thread"][2]["response_id"], "scenario_weights_v2_design_note.txt",
               "Document", "Design note for density-based scenario weights", "Model Developer 1", "2026-08-04T10:00:00",
               "Scenario weights v2.0 — design note\nWeights = normal density at each fixed scenario anchor, centred on the IMF forecast, normalised to 100%.")
mc["thread"][2]["evidence_ids"].append(eid)
eid = evidence("QDB-006", "request_response", fnd_ecl["thread"][1]["response_id"], "ecl_recalculation_plan.txt",
               "Document", "Plan for independent ECL recalculation", "Model Owner 2", "2025-04-20T09:30:00",
               "Independent ECL recalculation plan\nScope: sample of 200 facilities across stages.")
fnd_ecl["thread"][1]["evidence_ids"].append(eid)
eid = evidence("QDB-007", "request_response", fnd_cr["thread"][1]["response_id"], "override_rate_extract_q2_2026.txt",
               "Data extract", "Q2 2026 rating override extract", "Model Owner 1", "2026-07-15T14:00:00",
               "Override extract Q2 2026\nOverrides: 24% of rated obligors.")
fnd_cr["thread"][1]["evidence_ids"].append(eid)
evidence("QDB-002", "model", "QDB-002", "lgd_data_gap_analysis.txt", "Document",
         "LGD data gap analysis on the 2016–2026 loan tape", "Model Developer 2", "2026-08-12T11:00:00",
         "LGD data gap analysis\nMissing: collateral register, guarantee register, collection split by cash type.",
         doc_type="Data Quality Assessment")
val_pd = next(r for r in REQUESTS if r["model_id"] == "QDB-001" and r["type"] == "VAL" and r["closed_date"] == "2025-10-15")
evidence("QDB-001", "validation_request", val_pd["request_id"], "pd_validation_report_2025.txt", "Document",
         "Annual validation report 2025", PRIYA, "2025-10-15T16:00:00",
         "IFRS 9 PD model — annual validation report 2025\nRating: Fit with Conditions.")

MODEL_BY_ID = {m["model_id"]: m for m in MODELS}
# ---------------------------------------------------------------- KMPI library (mock thresholds)
# (model, name, category, unit, direction, amber, red, frequency, description, definition, data source,
#  series start, series end, note used when the value is amber or red)
H, L, R = "Higher is better", "Lower is better", "Within range"
LIBRARY = [
    # QDB-001 IFRS 9 PD
    ("QDB-001", "Gini — 12-month PD rank ordering", "Discrimination", "ratio", H, 0.55, 0.45, "Quarterly",
     "How well the PD model ranks obligors that go on to default above those that do not.",
     "Gini = 2 × AUC − 1, using each obligor's 12-month PD at the start of the window and defaults observed over the following 12 months (performing SME and corporate obligors).",
     "Rating and PD history (CreditLens extract); default register", 0.66, 0.62, None),
    ("QDB-001", "Default-rate back-test (observed ÷ predicted)", "Calibration / back-testing", "ratio", R, [0.80, 1.20], [0.65, 1.40], "Quarterly",
     "Whether predicted PDs match the default rate actually observed.",
     "Observed 12-month default rate of the cohort performing 12 months before period end ÷ the cohort's exposure-weighted average predicted 12-month PD.",
     "Default register; PD history", 1.02, 1.15, None),
    ("QDB-001", "Rating grades failing the binomial test", "Calibration / back-testing", "count", L, 1, 3, "Quarterly",
     "Grade-level calibration: grades where defaults are significantly higher than the grade PD implies.",
     "Number of rating grades whose observed default count exceeds the 99% one-sided binomial bound implied by the grade PD.",
     "Default register; PD master scale", 0, 1, "One grade (B3) breached; driven by two large contracting-sector defaults — under review with Credit."),
    ("QDB-001", "Rating distribution stability (PSI)", "Stability", "ratio", L, 0.10, 0.25, "Quarterly",
     "Whether today's portfolio still looks like the population the model was built on.",
     "PSI = Σ (actual% − expected%) × ln(actual% ÷ expected%) over rating grades, current portfolio against the development sample.",
     "Rating history (CreditLens extract)", 0.04, 0.08, None),
    ("QDB-001", "Exposure on fallback PD (%)", "Data quality", "%", L, 2.0, 5.0, "Quarterly",
     "Exposure that gets no model PD because the obligor has no valid current rating.",
     "Exposure of obligors without a valid current rating, given the fallback PD ÷ total exposure in scope.",
     "ECL input file; CreditLens rating dates", 1.2, 1.6, None),
    # QDB-002 IFRS 9 LGD (in development — KMPIs planned)
    ("QDB-002", "LGD back-test (realised ÷ predicted)", "Calibration / back-testing", "ratio", R, [0.85, 1.15], [0.70, 1.30], "Quarterly",
     "Whether predicted losses match the losses realised on closed workouts.",
     "Realised LGD on workouts closed in the last 12 months ÷ LGD predicted at the date of default.",
     "Workout and recovery records; collateral register", None, None, None),
    ("QDB-002", "Collateral valuations older than 12 months (%)", "Data quality", "%", L, 10.0, 20.0, "Quarterly",
     "Stale collateral values overstate recoveries.",
     "Collateral value with a valuation date more than 12 months before period end ÷ total collateral value used in LGD.",
     "Collateral register", None, None, None),
    # QDB-003 EAD / CCF
    ("QDB-003", "CCF back-test (realised ÷ predicted EAD)", "Calibration / back-testing", "ratio", R, [0.90, 1.10], [0.80, 1.25], "Quarterly",
     "Whether undrawn commitments are drawn down at default as the model predicts.",
     "Realised exposure at default ÷ EAD predicted 12 months before default, facilities that defaulted in the last 12 months.",
     "Facility limits and balances history; default register", 0.93, 0.96, None),
    ("QDB-003", "Defaults drawn above the approved limit (%)", "Data quality", "%", L, 5.0, 10.0, "Quarterly",
     "Drawings above limit at default point to a CCF floor that is too low or to limit-control gaps.",
     "Defaulted facilities whose drawn balance at default exceeded the approved limit ÷ defaulted facilities in the last 12 months.",
     "Facility limits and balances history", 2.0, 3.0, None),
    # QDB-004 Staging (SICR)
    ("QDB-004", "Defaults not in Stage 2 twelve months before (%)", "Calibration / back-testing", "%", L, 30.0, 50.0, "Quarterly",
     "Tests whether the SICR criteria catch deterioration early — a default should normally pass through Stage 2 first.",
     "Obligors that defaulted in the last 12 months and were in Stage 1 twelve months before default ÷ all defaults in the last 12 months.",
     "Staging history; default register", 22.0, 27.0, None),
    ("QDB-004", "Stage 2 share of performing exposure (%)", "Stability", "%", R, [6.0, 14.0], [4.0, 18.0], "Quarterly",
     "Whether the Stage 2 population is moving outside the range expected for QDB's portfolio.",
     "Stage 2 exposure ÷ (Stage 1 + Stage 2) exposure at period end.",
     "ECL engine output", 8.5, 11.0, None),
    ("QDB-004", "Stage 2 triggered only by the 30-day backstop (%)", "Calibration / back-testing", "%", L, 20.0, 35.0, "Quarterly",
     "A high share means the PD-based criteria are reacting late and the backstop is doing the work.",
     "Stage 2 exposure where the only SICR trigger met is 30+ days past due ÷ total Stage 2 exposure.",
     "Staging trigger flags (ECL engine)", 12.0, 16.0, None),
    ("QDB-004", "Manual staging overrides (%)", "Overrides and use", "%", L, 8.0, 12.0, "Quarterly",
     "Reliance on judgement instead of the staging rules.",
     "Exposure whose stage was changed manually from the rule-based stage ÷ total exposure in scope.",
     "Staging override log", 3.5, 4.5, None),
    # QDB-005 Scenario weights
    ("QDB-005", "Base-case GDP forecast error (pp)", "Calibration / back-testing", "pp", L, 1.5, 3.0, "Quarterly",
     "How far the base scenario was from what actually happened.",
     "|Base-scenario forecast of Qatar real non-hydrocarbon GDP growth − published outturn (PSA)|, percentage points, for the quarter four quarters back.",
     "Scenario set archive; PSA national accounts", 0.6, 1.9, "Base case missed the 2025 construction slowdown; scenario anchors to be refreshed at the Q4 update."),
    ("QDB-005", "Days since scenarios were last refreshed", "Data quality", "days", L, 100, 190, "Quarterly",
     "Scenarios should be refreshed every quarter so the ECL reflects current conditions.",
     "Calendar days between period end and the approval date of the scenario set used in that period's ECL.",
     "Scenario set approvals", 60, 85, None),
    ("QDB-005", "Weighted-to-base ECL uplift (%)", "Business outcome", "%", R, [2.0, 15.0], [0.0, 25.0], "Quarterly",
     "Checks that the weights produce a sensible non-linearity — neither none nor an extreme one.",
     "(Probability-weighted ECL − base-scenario ECL) ÷ base-scenario ECL.",
     "ECL engine scenario runs", 6.0, 8.0, None),
    # QDB-006 ECL engine
    ("QDB-006", "Unexplained ECL movement (%)", "Business outcome", "%", L, 5.0, 10.0, "Quarterly",
     "The part of the quarter's ECL change that the ECL walk cannot explain.",
     "ECL movement not attributed to a driver (new business, repayments, stage transfers, risk parameters, macro, overlays) ÷ opening ECL.",
     "ECL walk", 2.0, 4.0, None),
    ("QDB-006", "Exposure reconciliation break to the ledger (%)", "Data quality", "%", L, 0.5, 1.0, "Quarterly",
     "Completeness of the engine's input against the books.",
     "|Exposure in the ECL engine − general-ledger exposure| ÷ general-ledger exposure, in-scope portfolios at period end.",
     "ECL engine input; general ledger", 0.10, 0.30, None),
    ("QDB-006", "Post-model adjustments (% of ECL)", "Overrides and use", "%", L, 10.0, 20.0, "Quarterly",
     "Growing overlays signal the models no longer capture the risk.",
     "Management overlays and post-model adjustments ÷ total reported ECL.",
     "ECL overlay register", 7.0, 12.0, "Overlay for the contracting sector (approved by the CFO) pending the PD redevelopment."),
    # QDB-007 CreditLens — Manufacturing
    ("QDB-007", "Gini — rating rank ordering", "Discrimination", "ratio", H, 0.50, 0.45, "Quarterly",
     "How well the scorecard ranks manufacturing obligors by default risk.",
     "Gini = 2 × AUC − 1 of the model grade against defaults over the following 12 months.",
     "CreditLens rating history; default register", 0.56, 0.53, None),
    ("QDB-007", "Rating overrides (%)", "Overrides and use", "%", L, 15.0, 25.0, "Quarterly",
     "Frequent overrides mean users do not trust the model grade.",
     "Obligors whose approved grade differs from the model grade by one notch or more ÷ obligors rated in the period.",
     "CreditLens override log", 18.0, 24.0, "Override rate above policy — FND-004 open; override reasons being analysed with Credit."),
    ("QDB-007", "Ratings older than 12 months (%)", "Data quality", "%", L, 5.0, 10.0, "Quarterly",
     "Stale ratings mean decisions and ECL use out-of-date risk.",
     "Obligors in scope whose last approved rating is more than 12 months old at period end ÷ obligors in scope.",
     "CreditLens rating dates", 3.0, 4.0, None),
    # QDB-008 CreditLens — Services
    ("QDB-008", "Gini — rating rank ordering", "Discrimination", "ratio", H, 0.50, 0.45, "Quarterly",
     "How well the scorecard ranks services obligors by default risk.",
     "Gini = 2 × AUC − 1 of the model grade against defaults over the following 12 months.",
     "CreditLens rating history; default register", 0.57, 0.48, "Decline concentrated in hospitality obligors onboarded since 2025; segment analysis under way."),
    ("QDB-008", "Rating distribution stability (PSI)", "Stability", "ratio", L, 0.10, 0.25, "Quarterly",
     "Whether today's services portfolio still looks like the development population.",
     "PSI over rating grades, current portfolio against the development sample.",
     "CreditLens rating history", 0.05, 0.12, "Shift towards hospitality and education obligors after the 2025 programme launch."),
    ("QDB-008", "Rating overrides (%)", "Overrides and use", "%", L, 15.0, 25.0, "Quarterly",
     "Frequent overrides mean users do not trust the model grade.",
     "Obligors whose approved grade differs from the model grade by one notch or more ÷ obligors rated in the period.",
     "CreditLens override log", 10.0, 12.0, None),
    # QDB-009 Pricing
    ("QDB-009", "Realised vs priced margin variance (%)", "Business outcome", "%", L, 8.0, 12.0, "Quarterly",
     "Whether loans earn the risk-adjusted margin the model priced.",
     "|Realised net interest margin − margin priced by the model| ÷ priced margin, loans disbursed in the last 12 months.",
     "Loan pricing records; finance margin report", 4.0, 6.0, None),
    ("QDB-009", "Deals priced below the model floor (%)", "Overrides and use", "%", L, 10.0, 20.0, "Quarterly",
     "Pricing exceptions erode the model's purpose.",
     "Loans disbursed in the period at a rate below the model's floor rate (approved exceptions) ÷ loans disbursed.",
     "Pricing exception log", 6.0, 9.0, None),
    # QDB-010 Transaction scoring (AI system, in validation — KMPIs planned)
    ("QDB-010", "Gini — transaction score", "Discrimination", "ratio", H, 0.40, 0.30, "Quarterly",
     "How well the bank-statement score ranks applicants by default risk.",
     "Gini = 2 × AUC − 1 of the score at application against 12-month default.",
     "Scoring log; default register", None, None, None),
    ("QDB-010", "Largest input-feature PSI", "Stability", "ratio", L, 0.10, 0.25, "Quarterly",
     "Drift in any input feature of a machine-learning model.",
     "Highest PSI across the model's input features, applications in the period against the development sample.",
     "Scoring log", None, None, None),
    ("QDB-010", "Approval-rate gap between customer segments (pp)", "Fairness (AI)", "pp", L, 5.0, 10.0, "Quarterly",
     "Fairness monitoring required for AI systems by the QCB AI Guideline.",
     "Largest difference in model-recommended approval rate between customer segments (sector, company age band, size band), percentage points.",
     "Scoring log; customer master", None, None, None),
    ("QDB-010", "Applications with insufficient statement history (%)", "Data quality", "%", L, 10.0, 20.0, "Quarterly",
     "Applicants the model cannot score reliably.",
     "Applications with fewer than 6 months of bank-statement data ÷ applications scored.",
     "Open-banking feed; scoring log", None, None, None),
    # QDB-011 / QDB-012 Credit bureau scores (pre-implementation — KMPIs planned)
    ("QDB-011", "Gini — bureau score (individuals)", "Discrimination", "ratio", H, 0.45, 0.35, "Quarterly",
     "How well the bureau score ranks individual guarantors and owners by default risk.",
     "Gini = 2 × AUC − 1 of the score against 12-month default.", "Credit bureau extract; default register", None, None, None),
    ("QDB-011", "Bureau hit rate (%)", "Data quality", "%", H, 90.0, 80.0, "Quarterly",
     "Applicants the bureau cannot match get no score.",
     "Applicants matched to a credit bureau record ÷ applicants scored.", "Credit bureau extract", None, None, None),
    ("QDB-012", "Gini — bureau score (corporates)", "Discrimination", "ratio", H, 0.45, 0.35, "Quarterly",
     "How well the corporate bureau score ranks companies by default risk.",
     "Gini = 2 × AUC − 1 of the score against 12-month default.", "Credit bureau extract; default register", None, None, None),
    ("QDB-012", "Bureau hit rate (%)", "Data quality", "%", H, 85.0, 75.0, "Quarterly",
     "Companies the bureau cannot match get no score.",
     "Companies matched to a credit bureau record ÷ companies scored.", "Credit bureau extract", None, None, None),
    # QDB-014 Liquidity stress testing
    ("QDB-014", "Actual ÷ modelled stressed outflow (%)", "Calibration / back-testing", "%", L, 80.0, 100.0, "Quarterly",
     "Whether real outflows approach what the stress model assumes.",
     "Largest actual 30-day net cash outflow in the period ÷ modelled 30-day stressed net outflow.",
     "Treasury cash-flow report; stress test output", 45.0, 60.0, None),
    ("QDB-014", "LCR forecast error (pp)", "Calibration / back-testing", "pp", L, 5.0, 8.0, "Quarterly",
     "Accuracy of the liquidity projection.",
     "|Forecast LCR − actual LCR| at period end, forecast made one quarter earlier.",
     "ALCO pack; regulatory LCR return", 2.5, 4.5, None),
    # QDB-015 IRRBB
    ("QDB-015", "NII forecast error (%)", "Calibration / back-testing", "%", L, 6.0, 10.0, "Quarterly",
     "Accuracy of the net interest income projection.",
     "|Forecast NII − actual NII| ÷ actual NII for the quarter, forecast made one quarter earlier.",
     "ALM system; finance NII", 3.0, 4.0, None),
    ("QDB-015", "Deposit run-off back-test (actual ÷ assumed)", "Calibration / back-testing", "ratio", R, [0.80, 1.20], [0.60, 1.40], "Quarterly",
     "Whether non-maturity deposits behave as the behavioural assumption says.",
     "Actual run-off of non-maturity deposits in the last 12 months ÷ run-off assumed by the model.",
     "Deposit balances history", 0.95, 1.10, None),
    # QDB-016 Operational risk scenarios (annual)
    ("QDB-016", "Losses exceeding scenario severity (count)", "Calibration / back-testing", "count", L, 0, 1, "Annual",
     "A loss larger than the severe-but-plausible scenario means the scenario is understated.",
     "Internal and relevant external loss events in the last 12 months larger than the severe loss of the matching scenario.",
     "Operational loss database", 0, 0, None),
    ("QDB-016", "Scenarios reviewed in the last 12 months (%)", "Data quality", "%", H, 90.0, 75.0, "Annual",
     "Scenarios must be refreshed by the business each year.",
     "Scenarios with a business review dated in the last 12 months ÷ scenarios in the register.",
     "Scenario register", 100.0, 92.0, None),
    # QDB-017 AML customer risk rating
    ("QDB-017", "High-risk customer share (%)", "Stability", "%", R, [5.0, 12.0], [3.0, 15.0], "Quarterly",
     "A share outside the expected range points to factor weights out of line with QDB's customers.",
     "Customers rated High risk ÷ active customers at period end.",
     "AML platform customer risk scores", 9.0, 16.5, "Driven by the uncalibrated nationality and sector weights — FND-006 open; recalibration in progress."),
    ("QDB-017", "Suspicious activity reports on low-risk customers (%)", "Discrimination", "%", L, 20.0, 35.0, "Quarterly",
     "If many reports concern customers rated Low risk, the rating misses risky customers.",
     "Suspicious activity reports filed in the last 12 months on customers rated Low risk at the time ÷ all reports filed.",
     "AML case management", 15.0, 18.0, None),
    ("QDB-017", "Customer risk reviews overdue (%)", "Data quality", "%", L, 5.0, 10.0, "Quarterly",
     "Overdue periodic reviews leave ratings stale.",
     "Customers whose periodic risk review is past due ÷ active customers.",
     "AML platform review dates", 3.0, 6.0, "Backlog from the June system migration; extra reviewers assigned until year end."),
]

import kmpi as _k  # noqa: E402

SEED_TODAY = _date(2026, 10, 4)          # the date the sample data is written for
DEFINED_BY = {"QDB-006": "Model Owner 2", "QDB-014": "Model Owner 3", "QDB-015": "Model Owner 3",
              "QDB-016": "Model Owner 5", "QDB-017": "Model Owner 4", "QDB-009": "Model Owner 6"}
# How often each model reports its KMPIs (default quarterly).
MODEL_FREQUENCY = {"QDB-014": "Monthly", "QDB-009": "Semi-annual", "QDB-016": "Annual"}
# A KMPI can be reported less often than its model.
KMPI_FREQUENCY = {"Rating grades failing the binomial test": "Annual"}
for m in MODELS:
    m["kmpi_frequency"] = MODEL_FREQUENCY.get(m["model_id"], "Quarterly")


def _fmt(v, unit):
    if v is None:
        return ""
    if unit in ("count", "days"):
        return f"{int(round(v))}" + (" days" if unit == "days" else "")
    if unit == "ratio":
        return f"{v:.2f}"
    return f"{v:.1f}" + ("%" if unit == "%" else " pp")


def _criterion(direction, amber, unit):
    def n(x):
        return _fmt(x, unit)
    if direction == H:
        return f"Pass if ≥ {n(amber)}, otherwise Fail."
    if direction == L:
        return f"Pass if ≤ {n(amber)}, otherwise Fail."
    return f"Pass if between {n(amber[0])} and {n(amber[1])}, otherwise Fail."


def _passes(v, direction, amber):
    if direction == H:
        return v >= amber
    if direction == L:
        return v <= amber
    return amber[0] <= v <= amber[1]


KMPIS, SERIES = [], {}
for i, (mid, name, cat, unit, direction, amber, red, freq, desc, definition, source, start, end, note) in enumerate(LIBRARY, 1):
    kid = f"KMPI-{i:03d}"
    KMPIS.append({
        "kmpi_id": kid, "model_id": mid, "name": name,
        "description": f"{_criterion(direction, amber, unit)} {definition}",
        "frequency": KMPI_FREQUENCY.get(name, "As model"), "active": True,
        "defined_by": label(DEFINED_BY.get(mid, "Model Developer 1")),
        "defined_on": "2024-10-15" if start is not None else "2026-09-01",
    })
    if start is not None:
        SERIES[kid] = (start, end, note, unit, direction, amber)

KMPI_RETURNS = []
# Current periods (as of SEED_TODAY): a mix of states so every role has something to do.
CURRENT_STATE = {"QDB-003": "Submitted", "QDB-008": "Submitted", "QDB-004": "Returned",
                 "QDB-001": "Draft", "QDB-006": "Draft", "QDB-014": "Submitted"}
LINKED_FINDING = {("QDB-007", "2026-Q2"): "FND-004", ("QDB-017", "2026-Q2"): "FND-006"}
GENERIC_FAIL = "Outside tolerance; driver analysis in the monitoring pack, actions agreed with the validator."

for m in MODELS:
    ks = [k for k in KMPIS if k["model_id"] == m["model_id"] and k["kmpi_id"] in SERIES]
    if not ks:
        continue
    freq = m["kmpi_frequency"]
    cutoff = max("2024-01-01", m["approval_date"] or "2024-01-01")
    periods = [p for p in reversed(_k.recent_periods(freq, 12 if freq == "Monthly" else 8, SEED_TODAY))
               if _k.period_end(p).isoformat() >= cutoff]
    current = periods[-1]
    reviewer = m["validator"] if m["validator"] != "Not yet assigned" else label(HASSAN)
    preparer = m["developer"] if m["developer"].split(" (")[0] in ROLE else m["owner"]
    for qi, p in enumerate(periods):
        due = _k.due_kmpis(ks, p)
        if not due:
            continue
        state = CURRENT_STATE.get(m["model_id"]) if p == current else "Reviewed"
        if p == current and state is None and _k.due_date(p) < SEED_TODAY:
            state = "Reviewed"            # e.g. a semi-annual return already due and done
        if state is None:
            continue
        values = {}
        for n, k in enumerate(due):
            start, end, note, unit, direction, amber = SERIES[k["kmpi_id"]]
            base = start + (end - start) * qi / max(len(periods) - 1, 1)
            if qi < len(periods) - 2:
                base += random.uniform(-1, 1) * abs(end - start) * 0.08
            result = "Pass" if _passes(round(base, 4), direction, amber) else "Fail"
            value = _fmt(base, unit)
            if state == "Draft" and m["model_id"] == "QDB-001" and n >= 2:
                value, result = "", None      # partly filled draft
            values[k["kmpi_id"]] = {"name": k["name"], "description": k["description"], "value": value,
                                    "result": result,
                                    "comment": (note or GENERIC_FAIL) if result == "Fail" else ""}
        end_d = _k.period_end(p)
        on = lambda days: (end_d + _td(days=days)).isoformat()  # noqa: E731
        history = [{"action": "Saved", "by": preparer, "on": on(10), "comment": None}]
        ret = {"model_id": m["model_id"], "period": p, "status": state, "values": values,
               "history": history, "entered_by": preparer, "updated_on": on(10)}
        if state in ("Submitted", "Reviewed", "Returned"):
            history.append({"action": "Submitted", "by": preparer, "on": on(20), "comment": None})
            ret.update({"submitted_by": preparer, "submitted_on": on(20), "attestation": _k.ATTESTATION})
        if state == "Reviewed":
            fails = [v for v in values.values() if v["result"] == "Fail"]
            fid = LINKED_FINDING.get((m["model_id"], p))
            comment = (f"Reviewed. Fail tracked in {fid}." if fid else
                       "Reviewed; fails explained and accepted for now — re-check next period." if fails
                       else "Reviewed; results agree to the monitoring pack.")
            history.append({"action": "Reviewed", "by": reviewer, "on": on(27), "comment": comment})
            ret.update({"reviewed_by": reviewer, "reviewed_on": on(27), "review_comment": comment})
            if fid:
                ret["finding_id"] = fid
        if p == current and state in ("Draft", "Submitted", "Returned"):
            for h in history:
                h["on"] = "2026-10-01" if h["action"] == "Saved" else "2026-10-02"
            ret["updated_on"] = "2026-10-01"
            if state != "Draft":
                ret["submitted_on"] = "2026-10-02"
        if state == "Returned":
            msg = ("The Stage 2 share does not agree to the Q3 staging MI pack (11.0% here, 11.6% in the pack) — "
                   "please recheck and resubmit.")
            history.append({"action": "Returned", "by": reviewer, "on": "2026-10-03", "comment": msg})
        KMPI_RETURNS.append(ret)

# ---------------------------------------------------------------- annual confirmations (mock)
LAST_CONFIRMED = {"QDB-001": "2026-02-10", "QDB-003": "2026-02-10", "QDB-004": "2026-02-10",
                  "QDB-005": "2026-02-10", "QDB-006": "2026-03-05", "QDB-007": "2026-01-20",
                  "QDB-008": "2026-01-20", "QDB-009": "2025-11-10", "QDB-014": "2025-09-20",
                  "QDB-015": "2026-03-15", "QDB-016": "2026-04-02"}          # QDB-017: never confirmed
CONFIRMATION_STATEMENTS = [
    "The record is accurate: purpose, uses, users, data sources and platform",
    "The model is used as approved, with no unrecorded changes",
    "The known limitations and the KMPIs are still appropriate",
]
for m in MODELS:
    m["confirmations"] = []
    if m["model_id"] in LAST_CONFIRMED:
        m["confirmations"].append({"on": LAST_CONFIRMED[m["model_id"]], "by": m["owner"],
                                   "statements": CONFIRMATION_STATEMENTS, "comment": None})

# ---------------------------------------------------------------- decommissioned model (mock)
_legacy = MODEL_BY_ID["QDB-018"]
_legacy.update({
    "status": "Retired", "status_before_retirement": "In Production", "retired_on": "2025-12-31",
    "decommission": {"status": "Approved", "reason": "Replaced by another model", "replaced_by": "QDB-007",
                     "last_use": "2025-12-31", "note": "Replaced by the CreditLens sector models (QDB-007, QDB-008).",
                     "requested_by": label("Model Owner 1"), "requested_on": "2025-11-15",
                     "decided_by": label("Model Sponsor 1"), "decided_on": "2025-11-30",
                     "decision_comment": "All SME obligors re-rated in CreditLens."},
})


# ---------------------------------------------------------------- audit events (history)
AUDIT = []


def event(ts, user, action, entity_type, entity_id, model_id, details):
    AUDIT.append({
        "timestamp": ts if "T" in ts else f"{ts}T09:00:00", "user": user,
        "role": ROLE.get(user, "LOD1"), "action": action, "entity_type": entity_type,
        "entity_id": entity_id, "model_id": model_id, "details": details,
        "before": None, "after": None,
    })


for m in MODELS:
    first = min([c["date"] for c in m["change_log"]] + [m["approval_date"] or "9999"])
    event(first, "MRM Administrator 1", "register_model", "model", m["model_id"], m["model_id"],
          f"Model registered in the inventory: {m['name']}")
    for c in m["change_log"]:
        author = c["author"] if c["author"] in ROLE else "MRM Administrator 1"
        event(c["date"], author, "record_change", "change", c["change_id"], m["model_id"],
              f"{c['classification']} change to v{c['version']}: {c['description'][:80]}")
    for r in m["audit_reviews"]:
        event(r["date"], AUDITOR, "record_audit", "audit_review", r["audit_id"], m["model_id"],
              f"Internal audit review recorded — rating: {r['rating']}")
for r in REQUESTS:
    event(r["created_date"], r["initiated_by"], f"initiate_{r['type'].lower()}", "validation_request",
          r["request_id"], r["model_id"], f"{r['type']} opened: {r['title'][:80]}")
    for t in r["thread"][1:]:
        if t["text"].startswith("[Closure]"):
            event(f"{t['date']}T17:00:00", t["author"], "close_request", "validation_request", r["request_id"],
                  r["model_id"], f"Closed ({r['outcome']}): {t['text'][10:90]}")
        else:
            event(f"{t['date']}T12:00:00", t["author"], "respond_request", "validation_request", r["request_id"],
                  r["model_id"], f"Response added: {t['text'][:80]}")
for e in EVIDENCE:
    event(e["uploaded_at"], e["uploaded_by"], "upload_evidence", "evidence", e["evidence_id"], e["model_id"],
          f"Evidence uploaded ({e['category']}): {e['filename']}")
for m in MODELS:
    ta = m["tier_assessment"]
    event(ta["confirmed_on"] + "T10:00:00", ta["confirmed_by"], "confirm_tier", "tier_assessment",
          m["model_id"], m["model_id"], "Tier confirmed (G1)")
for m in MODELS:
    for ap in m["approvals"]:
        for i, sig in enumerate(ap["signatures"]):
            event(f"{ap['date']}T1{4 + i}:00:00", sig["by"].split(" (")[0], "record_approval", "approval",
                  ap["approval_id"], m["model_id"], f"{sig['decision']} by the {sig['as'].lower()} (G4)")
    for im in m["implementation"]:
        event(im["verified_on"] + "T11:00:00", HASSAN, "verify_implementation", "implementation",
              m["model_id"], m["model_id"], f"Implementation of v{im['version']} verified (G5)")
for m in MODELS:
    for c in m.get("confirmations", []):
        event(c["on"] + "T10:00:00", c["by"].split(" (")[0], "confirm_model", "confirmation", m["model_id"],
              m["model_id"], "Annual confirmation by the owner")
    d = m.get("decommission")
    if d:
        event(d["requested_on"] + "T10:00:00", d["requested_by"].split(" (")[0], "request_decommission",
              "decommission", m["model_id"], m["model_id"], f"Decommissioning requested: {d['reason']}")
        event(d["decided_on"] + "T10:00:00", d["decided_by"].split(" (")[0], "decide_decommission",
              "decommission", m["model_id"], m["model_id"], "Retired — decommissioning approved by the sponsor")
for k in KMPIS:
    event(k["defined_on"] + "T09:30:00", k["defined_by"].split(" (")[0], "save_kmpi", "kmpi", k["kmpi_id"],
          k["model_id"], f"KMPI {k['kmpi_id']} added: {k['name']}")
_KR_ACTION = {"Saved": "save_kmpi_return", "Submitted": "submit_kmpi_return",
              "Reviewed": "review_kmpi_return", "Returned": "return_kmpi_return"}
for r in KMPI_RETURNS:
    for i, h in enumerate(r["history"]):
        event(f"{h['on']}T1{i}:00:00", h["by"].split(" (")[0], _KR_ACTION[h["action"]], "kmpi_return",
              f"{r['model_id']}/{r['period']}", r["model_id"],
              f"KMPI return {r['period']} {h['action'].lower()}" + (f": {h['comment'][:60]}" if h.get("comment") else ""))
for t in TOOLS:
    event(t["registered_on"], t["registered_by"], "register_tool", "tool", t["tool_id"], "",
          f"{t['classification']} registered: {t['name']}")
AUDIT.sort(key=lambda e: e["timestamp"])


def main():
    SEED.mkdir(parents=True, exist_ok=True)

    def dump(name, obj):
        with open(SEED / name, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")

    dump("users.json", USERS)
    dump("models.json", MODELS)
    dump("validation_requests.json", REQUESTS)
    dump("evidence.json", EVIDENCE)
    dump("tools.json", TOOLS)
    dump("audit_log.json", AUDIT)
    dump("kmpis.json", KMPIS)
    dump("kmpi_returns.json", KMPI_RETURNS)
    (SEED / "monitoring.csv").unlink(missing_ok=True)
    print(f"{len(MODELS)} models, {len(REQUESTS)} requests, {len(EVIDENCE)} evidence files, "
          f"{len(KMPIS)} KMPIs, {len(KMPI_RETURNS)} KMPI returns, {len(AUDIT)} audit events written to {SEED}")


if __name__ == "__main__":
    main()
