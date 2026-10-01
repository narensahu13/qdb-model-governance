"""One-off generator for the pilot seed data in data/seed/.

It builds QDB's pilot inventory (the IFRS 9 suite, CreditLens rating models,
pricing, the scoring models in development and placeholder models for other
risk types) with a consistent history of validations, changes, findings,
evidence, monitoring and audit events.

Model NAMES and their relationships reflect QDB's real landscape; every other
attribute (people, dates, exposures, metrics, findings) is MOCK data to be
edited. After this first generation, edit the JSON files in data/seed/
directly and run `python scripts/reset_db.py` — do not re-run this script
unless you want to discard those edits.

Run from the project root:  python scripts/build_pilot_seed.py
"""

from __future__ import annotations

import csv
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
    {"name": "Ahmed Al-Kuwari", "title": "Head of Credit Risk", "role": "LOD1"},
    {"name": "Lina Haddad", "title": "Risk Analytics", "role": "LOD1"},
    {"name": "Rajesh Nair", "title": "Risk Analytics", "role": "LOD1"},
    {"name": "Omar Farouk", "title": "Credit Modelling", "role": "LOD1"},
    {"name": "David Chen", "title": "Data Science", "role": "LOD1"},
    {"name": "Fatima Al-Sulaiti", "title": "Head of Financial Control", "role": "LOD1"},
    {"name": "Mohammed Al-Marri", "title": "Head of Market & Liquidity Risk", "role": "LOD1"},
    {"name": "Noora Al-Thani", "title": "MLRO / Head of Compliance", "role": "LOD1"},
    {"name": "Sara Al-Naimi", "title": "Head of Operational Risk", "role": "LOD1"},
    {"name": "Yousef Al-Emadi", "title": "Head of Pricing & Strategy", "role": "LOD1"},
    {"name": "Hassan Al-Mohannadi", "title": "Model Validator (QDB)", "role": "LOD2"},
    {"name": "Priya Menon", "title": "External Validation Consultant", "role": "LOD2"},
    {"name": "Abdulla Al-Sayed", "title": "Internal Audit", "role": "LOD3"},
    {"name": "Maryam Al-Kaabi", "title": "MRM Administrator", "role": "ADMIN"},
    {"name": "Khalid Al-Mannai", "title": "Chief Risk Officer", "role": "CRO"},
]
TITLE = {u["name"]: u["title"] for u in USERS}
ROLE = {u["name"]: u["role"] for u in USERS}


def label(name: str) -> str:
    return f"{name} ({TITLE[name]})" if name in TITLE else name


HASSAN = "Hassan Al-Mohannadi"
PRIYA = "Priya Menon"
AUDITOR = "Abdulla Al-Sayed"

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
        "monitoring_metrics": monitoring_metrics,
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
            "confirmed_by": "Maryam Al-Kaabi",
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
        "QDB-IF-001", "IFRS 9 PD Model (point-in-time term structure)",
        version="2.1", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Through-the-cycle rating-to-PD mapping with macro-linked point-in-time adjustment and lifetime term structure",
        description="Converts obligor ratings into 12-month and lifetime point-in-time PDs for ECL, using the scenario-weighted macroeconomic outlook.",
        owner="Ahmed Al-Kuwari", developer="Lina Haddad", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "High", "complexity": "High", "regulatory_impact": "High"},
        tier_rationale="Drives Stage 1 and Stage 2 ECL across the whole financing book; output feeds the financial statements.",
        status="Approved with Conditions", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG, upstream=["QDB-CR-001", "QDB-CR-002", "QDB-IF-005"],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["PD Backtest Ratio", "PSI"],
        data_sources=["Core banking loan tape", "CreditLens rating history", "Default register"],
        platform="Python (Risk Analytics) feeding the ECL engine", usage="Monthly batch",
        users=["Risk Analytics", "Financial Control"],
        assumptions=["Default definition: 90+ DPD or unlikely to pay, per QDB interpretation", "Rating migration history 2016 onward is representative"],
        limitations=["Low default counts in some sectors; sector PDs pooled", "Point-in-time adjustment not yet back-tested by segment"],
        exposure=9500,
        change_log=[
            chg("2023-11-01", "2.0", "Redevelopment with lifetime term structure and macro-linked PiT adjustment.", "Lina Haddad", "Material", "New methodology."),
            chg("2026-04-02", "2.1", "Annual PD recalibration within approved ranges.", "Lina Haddad", "Non-material", "Parameter refresh within the approved methodology."),
        ],
    ),
    model(
        "QDB-IF-002", "IFRS 9 LGD Model (collateral haircut approach)",
        version="0.9", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Collateral haircut approach; LGD decomposed into cure rate and workout LGD with discounted recoveries",
        description="New LGD model for the SME and corporate book, built from a 10-year account-level loan tape. Replaces the current expert LGD assumptions once validated.",
        owner="Ahmed Al-Kuwari", developer="Rajesh Nair", validator=None,
        sponsor="Chief Risk Officer", area="credit",
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
        change_log=[chg("2026-06-15", "0.9", "Development build: default population and recovery curves.", "Rajesh Nair", "Material", "New model under development.")],
    ),
    model(
        "QDB-IF-003", "IFRS 9 EAD / CCF Model",
        version="1.2", risk_type="IFRS 9 / Provisioning", category="Parameter estimation",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Amortisation schedules for term financing; credit conversion factors for undrawn limits",
        description="Projects exposure at default over the lifetime of each facility, including drawdown of undrawn limits on revolving products.",
        owner="Ahmed Al-Kuwari", developer="Omar Farouk", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
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
        change_log=[chg("2023-10-20", "1.2", "CCF re-estimation on 2016–2023 data.", "Omar Farouk", "Material", "Parameter re-estimation.")],
    ),
    model(
        "QDB-IF-004", "IFRS 9 Staging Model (SICR)",
        version="1.3", risk_type="IFRS 9 / Provisioning", category="Classification rules",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Rules: 30 DPD backstop, rating-downgrade thresholds, watch-list and restructuring triggers, cure periods",
        description="Allocates each exposure to Stage 1, 2 or 3 using significant-increase-in-credit-risk criteria and default triggers.",
        owner="Ahmed Al-Kuwari", developer="Lina Haddad", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "High", "complexity": "Low", "regulatory_impact": "High"},
        tier_rationale="Stage allocation decides 12-month vs lifetime ECL for the whole book.",
        status="In Production", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG, upstream=["QDB-IF-001"],
        docs_done=["Model Development Document", "Methodology Document", "Data Quality Assessment", "Validation Report", "Ongoing Monitoring Plan"],
        monitoring_metrics=["Stage 2 Ratio (%)", "Staging Override Rate (%)"],
        data_sources=["Core banking DPD", "CreditLens ratings", "Watch-list register"],
        platform="ETL tool feeding the ECL engine", usage="Monthly batch",
        users=["Risk Analytics", "Financial Control", "Credit Administration"],
        assumptions=["Rating downgrade of three notches since origination signals SICR"],
        limitations=["Cure period rule applied but not documented"],
        exposure=9500,
        change_log=[chg("2024-02-10", "1.3", "Added restructuring flag as a Stage 2 trigger.", "Lina Haddad", "Material", "New SICR trigger.")],
    ),
    model(
        "QDB-IF-005", "IFRS 9 Macroeconomic Scenario Weights",
        version="2.0", risk_type="IFRS 9 / Provisioning", category="Forward-looking information",
        business_line="Finance & Risk — IFRS 9", source="In-house",
        methodology="Five scenarios on Qatar non-oil GDP; density-based likelihood weights centred on the current IMF forecast",
        description="Sets the probability weights of the five macroeconomic scenarios used in the PD model and the ECL engine.",
        owner="Ahmed Al-Kuwari", developer="Lina Haddad", validator=HASSAN,
        sponsor="Chief Risk Officer", area="credit",
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
            chg("2024-11-15", "1.0", "First documented version: weights from historical mean.", "Lina Haddad", "Material", "New model."),
            chg("2026-07-20", "2.0", "Redesigned to density-based weights centred on the current IMF forecast; fixes downside weights moving the wrong way.", "Lina Haddad", "Material", "Methodology change."),
        ],
    ),
    model(
        "QDB-IF-006", "ECL Calculation Engine (LIC)",
        version="4.2", risk_type="IFRS 9 / Provisioning", category="Calculation engine",
        business_line="Finance & Risk — IFRS 9", source="Vendor", vendor="LIC",
        methodology="Vendor engine: PD × LGD × EAD, discounted at the effective interest rate and probability-weighted across scenarios",
        description="Web-based vendor engine that computes ECL from the staged data prepared by the ETL tool.",
        owner="Fatima Al-Sulaiti", developer="Vendor (LIC), configured by Risk Analytics", validator=PRIYA,
        sponsor="Chief Financial Officer", area="finance",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "High"},
        tier_rationale="Produces the reported ECL figure.",
        status="Approved with Conditions", approval_date="2023-12-18",
        regulatory_mapping=IFRS9_REG + ["QCB outsourcing instructions"], upstream=["QDB-IF-001", "QDB-IF-002", "QDB-IF-003", "QDB-IF-004", "QDB-IF-005"],
        docs_done=["User Guide / Operating Manual", "Validation Report"],
        monitoring_metrics=["Unexplained ECL Movement (%)"],
        data_sources=["ETL consolidated data template"],
        platform="LIC web tool (vendor-hosted SQL procedures)", usage="Monthly",
        users=["Financial Control", "Risk Analytics"],
        assumptions=["Vendor SQL procedures implement the approved methodology"],
        limitations=["Engine internals are a black box; no independent recalculation yet"],
        exposure=9500,
        change_log=[chg("2023-09-01", "4.2", "Upgrade to vendor release 4.2.", "Fatima Al-Sulaiti", "Material", "Vendor release upgrade.")],
        audit_reviews=[{"date": "2025-09-22", "auditor": label(AUDITOR), "rating": "Needs Improvement", "scope": "Controls over vendor ECL engine configuration and change management."}],
    ),
    # ------------------------------------------------------------ CreditLens ratings
    model(
        "QDB-CR-001", "Obligor Rating Model — Manufacturing (CreditLens)",
        version="3.0", risk_type="Credit Rating & Scoring", category="Rating",
        business_line="SME & Corporate Lending", source="Vendor", vendor="Moody's CreditLens",
        methodology="Vendor scorecard (financial and qualitative factors) calibrated to QDB's manufacturing portfolio",
        description="Assigns obligor risk grades to manufacturing borrowers at origination and annual review.",
        owner="Ahmed Al-Kuwari", developer="Moody's CreditLens (vendor), calibrated by Credit Modelling", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
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
        change_log=[chg("2025-09-01", "3.0", "Calibration of vendor scorecard to QDB manufacturing default history.", "Omar Farouk", "Material", "Recalibration.")],
        audit_reviews=[{"date": "2026-01-15", "auditor": label(AUDITOR), "rating": "Satisfactory", "scope": "Override governance in the rating process."}],
    ),
    model(
        "QDB-CR-002", "Obligor Rating Model — Services (CreditLens)",
        version="3.0", risk_type="Credit Rating & Scoring", category="Rating",
        business_line="SME & Corporate Lending", source="Vendor", vendor="Moody's CreditLens",
        methodology="Vendor scorecard (financial and qualitative factors) calibrated to QDB's services portfolio",
        description="Assigns obligor risk grades to services-sector borrowers at origination and annual review.",
        owner="Ahmed Al-Kuwari", developer="Moody's CreditLens (vendor), calibrated by Credit Modelling", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
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
        change_log=[chg("2025-09-01", "3.0", "Calibration of vendor scorecard to QDB services default history.", "Omar Farouk", "Material", "Recalibration.")],
    ),
    # ------------------------------------------------------------ pricing
    model(
        "QDB-PR-001", "Risk-Based Pricing Model",
        version="1.4", risk_type="Pricing", category="Decision support",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Cost-plus pricing: funding cost, operating cost, expected loss (PD × LGD) and capital charge",
        description="Sets the minimum profit rate for new financing from the obligor's risk grade and facility terms.",
        owner="Yousef Al-Emadi", developer="Rajesh Nair", validator=HASSAN,
        sponsor="Chief Executive Officer", area="pricing",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="Influences margins on new business; no direct regulatory output.",
        status="In Production", approval_date="2022-11-30",
        regulatory_mapping=["QCB pricing and fees instructions", "SR 26-2 (benchmark)"], upstream=["QDB-IF-001", "QDB-IF-002"],
        docs_done=["Model Development Document", "Methodology Document", "User Guide / Operating Manual", "Validation Report"],
        monitoring_metrics=["Realised vs Priced Margin Variance (%)"],
        data_sources=["Treasury funding curve", "Cost allocation", "Rating grade"],
        platform="Excel pricing tool", usage="Per financing proposal",
        users=["Relationship Managers", "Credit Committee"],
        assumptions=["Expected loss uses current IFRS 9 PD and expert LGD"],
        limitations=["Will need recalibration when the new LGD model goes live"],
        exposure=1800,
        change_log=[chg("2024-10-01", "1.4", "Funding curve and cost allocation refresh.", "Rajesh Nair", "Non-material", "Parameter refresh.")],
    ),
    # ------------------------------------------------------------ in development
    model(
        "QDB-CR-010", "Transaction Scoring Model (bank-statement based)",
        version="0.5", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME Lending", source="In-house",
        methodology="Gradient-boosted model on cash-flow, turnover and repayment-behaviour features from bank statements",
        description="Scores thin-file SMEs where audited financials are unreliable, using transaction behaviour from bank statements.",
        owner="Ahmed Al-Kuwari", developer="David Chen", validator=PRIYA,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "Medium", "complexity": "High", "regulatory_impact": "Medium"},
        tier_rationale="Machine-learning model that will influence credit decisions for thin-file SMEs.",
        status="In Development", approval_date=None,
        regulatory_mapping=["QCB Artificial Intelligence Guideline (2024)", "QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=["Data Quality Assessment"],
        monitoring_metrics=[],
        data_sources=["Bank statements (customer-provided)", "Core banking repayment history"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Statement features are stable across banks and formats"],
        limitations=["Short performance window", "Explainability and bias testing required under the QCB AI Guideline"],
        exposure=600, ai_system=True, qcb_ai_high_risk=True,
        change_log=[chg("2026-08-15", "0.5", "Prototype with 42 engineered features.", "David Chen", "Material", "New model under development.")],
    ),
    model(
        "QDB-CR-011", "Credit Bureau Score — Individual",
        version="0.3", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME Lending", source="In-house",
        methodology="Logistic regression on Qatar Credit Bureau attributes of owners and guarantors",
        description="Scores the individuals behind an SME (owners, guarantors) from their credit bureau records.",
        owner="Ahmed Al-Kuwari", developer="Omar Farouk", validator=None,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="One input to the combination module; moderate influence on decisions.",
        status="In Development", approval_date=None,
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=[], monitoring_metrics=[],
        data_sources=["Qatar Credit Bureau — individual reports"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Bureau coverage of owners is sufficient"],
        limitations=["Bureau history for expatriate owners is limited"],
        exposure=600,
        change_log=[chg("2026-07-01", "0.3", "Variable selection on bureau attributes.", "Omar Farouk", "Material", "New model under development.")],
    ),
    model(
        "QDB-CR-012", "Credit Bureau Score — Corporate",
        version="0.3", risk_type="Credit Rating & Scoring", category="Scoring",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Logistic regression on Qatar Credit Bureau company attributes",
        description="Scores the borrowing company from its credit bureau record.",
        owner="Ahmed Al-Kuwari", developer="Omar Farouk", validator=None,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "Medium", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="One input to the combination module; moderate influence on decisions.",
        status="In Development", approval_date=None,
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"], upstream=[],
        docs_done=[], monitoring_metrics=[],
        data_sources=["Qatar Credit Bureau — company reports"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Bureau coverage of companies is sufficient"],
        limitations=["New companies have no bureau history"],
        exposure=1500,
        change_log=[chg("2026-07-01", "0.3", "Variable selection on bureau attributes.", "Omar Farouk", "Material", "New model under development.")],
    ),
    model(
        "QDB-CR-013", "Combination Module (rating, bureau and transaction scores)",
        version="0.2", risk_type="Credit Rating & Scoring", category="Decision",
        business_line="SME & Corporate Lending", source="In-house",
        methodology="Weighted combination of rating, bureau and transaction scores into a final grade, with an override matrix",
        description="Combines the CreditLens rating, the two bureau scores and the transaction score into one final risk grade for decisioning.",
        owner="Ahmed Al-Kuwari", developer="David Chen", validator=None,
        sponsor="Chief Risk Officer", area="credit",
        scores={"materiality": "High", "complexity": "Medium", "regulatory_impact": "Medium"},
        tier_rationale="Will set the final grade used for approval authority across SME lending.",
        status="In Development", approval_date=None,
        regulatory_mapping=["QCB credit risk instructions", "SR 26-2 (benchmark)"],
        upstream=["QDB-CR-001", "QDB-CR-002", "QDB-CR-010", "QDB-CR-011", "QDB-CR-012"],
        docs_done=[], monitoring_metrics=[],
        data_sources=["Outputs of upstream models"],
        platform="Python", usage="At application (planned)",
        users=["Credit Underwriting (planned)"],
        assumptions=["Component scores are complementary"],
        limitations=["Weights are expert-set until outcome data accumulates"],
        exposure=4500,
        change_log=[chg("2026-08-20", "0.2", "Initial weighting scheme agreed with Credit.", "David Chen", "Material", "New model under development.")],
    ),
    # ------------------------------------------------------------ placeholders for other risk types
    model(
        "QDB-ML-001", "Liquidity Stress Testing Model",
        version="1.1", risk_type="Market & Liquidity Risk", category="Projection",
        business_line="Treasury / ALM", source="In-house",
        methodology="Cash-flow projection under idiosyncratic and market-wide stress scenarios",
        description="Placeholder record — projects the survival horizon under liquidity stress.",
        owner="Mohammed Al-Marri", developer="Treasury analytics", validator=HASSAN,
        sponsor="Chief Financial Officer", area="treasury",
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
        change_log=[chg("2021-05-01", "1.1", "Scenario update.", "Mohammed Al-Marri", "Non-material", "Scenario parameters refresh.")],
    ),
    model(
        "QDB-ML-002", "IRRBB Model (EVE and NII sensitivity)",
        version="1.0", risk_type="Market & Liquidity Risk", category="Measurement",
        business_line="Treasury / ALM", source="In-house",
        methodology="Repricing gap with standard rate shocks for economic value and net profit income",
        description="Placeholder record — measures interest (profit) rate risk in the banking book.",
        owner="Mohammed Al-Marri", developer="Treasury analytics", validator=HASSAN,
        sponsor="Chief Financial Officer", area="treasury",
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
        change_log=[chg("2022-02-01", "1.0", "First version.", "Mohammed Al-Marri", "Material", "New model.")],
    ),
    model(
        "QDB-OR-001", "Operational Risk Scenario Analysis",
        version="1.0", risk_type="Operational & Non-Financial Risk", category="Assessment",
        business_line="Operational Risk", source="In-house",
        methodology="Expert-elicited frequency and severity per scenario, aggregated to an annual loss estimate",
        description="Placeholder record — estimates severe but plausible operational losses for risk appetite.",
        owner="Sara Al-Naimi", developer="Operational Risk team", validator=HASSAN,
        sponsor="Chief Risk Officer", area="oprisk",
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
        change_log=[chg("2023-01-15", "1.0", "First version.", "Sara Al-Naimi", "Material", "New model.")],
    ),
    model(
        "QDB-NF-001", "AML Customer Risk Rating",
        version="2.0", risk_type="Operational & Non-Financial Risk", category="Rating",
        business_line="Compliance", source="Vendor", vendor="AML platform vendor",
        methodology="Weighted risk factors (customer type, geography, product, channel) with vendor defaults",
        description="Placeholder record — rates customers for AML/CFT due diligence under Law No. 20 of 2019.",
        owner="Noora Al-Thani", developer="Vendor, configured by Compliance", validator=PRIYA,
        sponsor="Chief Compliance Officer", area="compliance",
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
        change_log=[chg("2024-05-01", "2.0", "Vendor upgrade.", "Noora Al-Thani", "Material", "Vendor release.")],
    ),
]

# ---------------------------------------------------------------- uses (mock)
USES = {
    "QDB-IF-001": [("Stage 1 and 2 ECL", "Finance & Risk", "12-month and lifetime PD in the monthly ECL run"),
                   ("Risk-based pricing", "SME & Corporate Lending", "Expected-loss component of the profit rate")],
    "QDB-IF-002": [("Stage 1–3 ECL", "Finance & Risk", "LGD in the monthly ECL run (planned)")],
    "QDB-IF-003": [("Stage 1–3 ECL", "Finance & Risk", "Lifetime EAD in the monthly ECL run")],
    "QDB-IF-004": [("Stage allocation", "Finance & Risk", "12-month vs lifetime ECL for each exposure")],
    "QDB-IF-005": [("Forward-looking ECL", "Finance & Risk", "Probability weights of the five scenarios")],
    "QDB-IF-006": [("Reported ECL", "Financial Control", "Monthly impairment figure for the financial statements")],
    "QDB-CR-001": [("Credit approval", "SME & Corporate Lending", "Obligor grade drives approval authority"),
                   ("IFRS 9 PD", "Finance & Risk", "Grade mapped to PD")],
    "QDB-CR-002": [("Credit approval", "SME & Corporate Lending", "Obligor grade drives approval authority"),
                   ("IFRS 9 PD", "Finance & Risk", "Grade mapped to PD")],
    "QDB-PR-001": [("Pricing of new financing", "SME & Corporate Lending", "Minimum profit rate per proposal")],
    "QDB-CR-010": [("Thin-file SME assessment", "SME Lending", "Score for SMEs without reliable financials (planned)")],
    "QDB-CR-011": [("Owner / guarantor assessment", "SME Lending", "Bureau score input to the combination module (planned)")],
    "QDB-CR-012": [("Company bureau assessment", "SME & Corporate Lending", "Bureau score input to the combination module (planned)")],
    "QDB-CR-013": [("Final risk grade", "SME & Corporate Lending", "Combined grade for decisioning (planned)")],
    "QDB-ML-001": [("Liquidity risk appetite", "Treasury / ALCO", "Survival horizon under stress")],
    "QDB-ML-002": [("IRRBB limits", "Treasury / ALCO", "EVE and NII sensitivity against limits")],
    "QDB-OR-001": [("Operational risk appetite", "Operational Risk", "Severe-but-plausible annual loss")],
    "QDB-NF-001": [("Customer due diligence", "Compliance", "Customer risk rating sets the due-diligence level")],
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
        "owner": label("Fatima Al-Sulaiti"), "business_area": "Financial Control",
        "platform": "Excel with macros", "materiality": "High",
        "controls": "Version control, input reconciliation to the general ledger, second-person review",
        "ai_system": False, "related_models": ["QDB-IF-006"],
    },
    {
        "tool_id": "QDB-EUC-002", "name": "Provision journal calculator",
        "classification": "EUC tool",
        "description": "Turns ECL results into general-ledger journal entries by product and branch.",
        "owner": label("Fatima Al-Sulaiti"), "business_area": "Financial Control",
        "platform": "Excel", "materiality": "Medium",
        "controls": "Totals reconciled to ECL engine output",
        "ai_system": False, "related_models": ["QDB-IF-006"],
    },
    {
        "tool_id": "QDB-AI-001", "name": "Financial statement spreading (OCR)",
        "classification": "AI tool (non-model)",
        "description": "Reads uploaded financial statements and pre-fills CreditLens spreads for analyst review.",
        "owner": label("Ahmed Al-Kuwari"), "business_area": "Credit Underwriting",
        "platform": "Moody's CreditLens add-on", "materiality": "Medium",
        "controls": "Analyst reviews every spread before rating",
        "ai_system": True, "qcb_ai_high_risk": False,
        "ai_functional_category": "Document processing",
        "ai_provider_role": "User / deployer (third-party system)",
        "ai_autonomy": "Human-in-the-loop", "qcb_approval_status": "Not required",
        "related_models": ["QDB-CR-001", "QDB-CR-002"],
    },
    {
        "tool_id": "QDB-NM-001", "name": "Repayment schedule calculator",
        "classification": "Not a model",
        "description": "Produces instalment schedules from contract terms; no estimation.",
        "owner": label("Omar Farouk"), "business_area": "Credit Administration",
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
    t["registered_by"] = "Maryam Al-Kaabi"
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


closed_val("QDB-IF-001", "2023-12-05", "Initial", "Fit for Purpose", PRIYA, T_PD, "Initial validation of the redeveloped PD model.")
closed_val("QDB-IF-001", "2025-10-15", "Periodic", "Fit with Conditions", PRIYA, T_PD, "Annual validation: calibration adequate; PiT adjustment not back-tested by segment.")
closed_val("QDB-IF-003", "2025-10-15", "Periodic", "Fit for Purpose", PRIYA, ["Calibration accuracy / backtest", "Implementation testing", "Documentation review"], "Annual validation of EAD/CCF.")
closed_val("QDB-IF-004", "2025-10-15", "Periodic", "Fit for Purpose", PRIYA, T_RULES, "Annual validation of staging rules.")
closed_val("QDB-IF-005", "2024-12-10", "Initial", "Fit with Conditions", HASSAN, ["Scenario testing", "Sensitivity analysis", "Benchmarking"], "Initial validation of scenario weights v1.0.")
closed_val("QDB-IF-006", "2024-11-05", "Periodic", "Fit with Conditions", PRIYA, ["Implementation testing", "Benchmarking", "Documentation review"], "Annual review of the vendor ECL engine; no independent recalculation possible.")
closed_val("QDB-CR-001", "2025-11-20", "Initial", "Fit with Conditions", PRIYA, T_PD + ["Override analysis"], "Validation of CreditLens manufacturing calibration.")
closed_val("QDB-CR-002", "2025-11-20", "Initial", "Fit for Purpose", PRIYA, T_PD, "Validation of CreditLens services calibration.")
closed_val("QDB-PR-001", "2024-11-10", "Periodic", "Fit for Purpose", HASSAN, ["Implementation testing", "Sensitivity analysis", "Benchmarking"], "Biennial review of the pricing model.")
closed_val("QDB-ML-001", "2023-12-05", "Periodic", "Fit with Conditions", HASSAN, ["Scenario testing", "Documentation review"], "Placeholder — periodic review of liquidity stress testing.")
closed_val("QDB-ML-002", "2025-02-20", "Periodic", "Fit for Purpose", HASSAN, ["Implementation testing", "Sensitivity analysis"], "Placeholder — biennial review of IRRBB.")
closed_val("QDB-OR-001", "2024-03-15", "Periodic", "Fit for Purpose", HASSAN, ["Documentation review"], "Placeholder — triennial review of scenario analysis.")
closed_val("QDB-NF-001", "2025-05-18", "Periodic", "Fit with Conditions", PRIYA, ["Data quality review", "Sensitivity analysis"], "Placeholder — annual review of AML customer risk rating.")

req("VAL", "QDB-CR-010", title="Initial validation request", status="In Progress",
    description="Requesting initial validation of the transaction scoring model before pilot use, including bias and explainability testing under the QCB AI Guideline.",
    initiated_by="David Chen", assigned_to=PRIYA, created="2026-09-01", source="LoD1 Request", subtype="Initial",
    thread=[("2026-09-01", "David Chen", "Requesting initial validation of the transaction scoring model before pilot use, including bias and explainability testing under the QCB AI Guideline."),
            ("2026-09-08", PRIYA, "Accepted. Please upload the development document, feature list and the out-of-time results. I will send the information request list this week.")])
req("VAL", "QDB-IF-006", title="Periodic validation (overdue)", status="Open",
    description="Periodic validation overdue since November 2025. Scope to include an independent recalculation of ECL for a sample portfolio.",
    initiated_by=HASSAN, assigned_to=PRIYA, created="2026-09-10", source="Validation", subtype="Periodic")

req("MC", "QDB-IF-005", title="Material change v2.0 — density-based weights", status="In Progress",
    description="Weights redesigned around the current IMF forecast. Version 2.0 used for the June 2026 ECL run pending revalidation.",
    initiated_by="Lina Haddad", assigned_to=HASSAN, created="2026-07-20", source="Model Change", materiality="Material",
    thread=[("2026-07-20", "Lina Haddad", "Weights redesigned around the current IMF forecast. Version 2.0 used for the June 2026 ECL run pending revalidation."),
            ("2026-07-28", HASSAN, "Received. Please attach the design note and the comparison of v1 and v2 weights across the last four quarters."),
            ("2026-08-04", "Lina Haddad", "Design note attached. Comparison to follow with Q3 data.")])
req("MC", "QDB-IF-001", title="Non-material change v2.1 — annual recalibration", status="Closed",
    description="Annual recalibration within approved ranges.", initiated_by="Lina Haddad", assigned_to=PRIYA,
    created="2026-04-02", closed="2026-04-20", outcome="Fit for Purpose", source="Model Change", materiality="Non-material",
    thread=[("2026-04-02", "Lina Haddad", "Annual recalibration within approved ranges."),
            ("2026-04-20", PRIYA, "[Closure] Confirmed non-material; parameters within approved ranges.")])

req("FND", "QDB-IF-001", title="Point-in-time adjustment not back-tested by segment", status="Open", severity="Medium",
    description="The macro-linked PiT adjustment is only back-tested at portfolio level.",
    remediation="Back-test the PiT adjustment for each rating segment and document results.",
    initiated_by=PRIYA, assigned_to="Lina Haddad", created="2025-10-15", due="2026-04-15", source="Validation")
fnd_ecl = req("FND", "QDB-IF-006", title="No independent recalculation of vendor ECL engine", status="Open", severity="High",
    description="ECL produced by the vendor engine cannot be reproduced; internals are not documented.",
    remediation="Build an independent recalculation for a sample portfolio and obtain vendor documentation of the SQL procedures.",
    initiated_by=PRIYA, assigned_to="Fatima Al-Sulaiti", created="2024-11-05", due="2025-05-05", source="Validation",
    thread=[("2024-11-05", PRIYA, "ECL produced by the vendor engine cannot be reproduced; internals are not documented."),
            ("2025-04-20", "Fatima Al-Sulaiti", "Vendor documentation requested; recalculation plan attached."),
            ("2026-03-02", "Rajesh Nair", "Python recalculation covers Stage 1 and 2; Stage 3 pending.")])
req("FND", "QDB-IF-004", title="Cure period rule not documented", status="Open", severity="Low",
    description="The 3-month cure period for exits from Stage 2 is applied in the ETL but not written in the methodology.",
    remediation="Document the cure period rule and its rationale in the methodology document.",
    initiated_by=PRIYA, assigned_to="Lina Haddad", created="2025-10-15", due="2026-10-15", source="Validation")
fnd_cr = req("FND", "QDB-CR-001", title="Override rate above policy threshold", status="Open", severity="Medium",
    description="Rating overrides at 24% against a 15% policy threshold.",
    remediation="Analyse override reasons; tighten override governance; recalibrate qualitative factors if needed.",
    initiated_by=PRIYA, assigned_to="Ahmed Al-Kuwari", created="2025-11-20", due="2026-05-20", source="Validation",
    thread=[("2025-11-20", PRIYA, "Rating overrides at 24% against a 15% policy threshold."),
            ("2026-07-15", "Ahmed Al-Kuwari", "Q2 2026 override extract attached; overrides reasons being coded.")])
req("FND", "QDB-IF-005", title="Downside weights moved in the wrong direction", status="Closed", severity="Medium",
    description="Under v1.0, a weaker GDP forecast lowered the downside scenario weight.",
    remediation="Redesign the weighting so weights respond in the expected direction.",
    initiated_by=HASSAN, assigned_to="Lina Haddad", created="2024-12-10", due="2025-12-10", closed="2026-07-25",
    outcome="Closed", source="Validation",
    thread=[("2024-12-10", HASSAN, "Under v1.0, a weaker GDP forecast lowered the downside scenario weight."),
            ("2026-07-20", "Lina Haddad", "Fixed by the v2.0 density-based redesign (see MC-001)."),
            ("2026-07-25", HASSAN, "[Closure] Verified on the v2.0 workbook: weights now move in the expected direction.")])
req("FND", "QDB-NF-001", title="Risk factor weights not calibrated to QDB customers", status="Open", severity="High",
    description="Placeholder — vendor default weights used without calibration.",
    remediation="Calibrate factor weights to QDB's customer base and document the rationale.",
    initiated_by=PRIYA, assigned_to="Noora Al-Thani", created="2025-05-18", due="2025-11-18", source="Validation")
req("FND", "QDB-ML-001", title="Behavioural run-off assumptions not evidenced", status="Open", severity="Medium",
    description="Placeholder — run-off rates are expert-set with no supporting analysis.",
    remediation="Evidence run-off rates from deposit history.",
    initiated_by=HASSAN, assigned_to="Mohammed Al-Marri", created="2023-12-05", due="2024-06-05", source="Validation")
req("FND", "QDB-IF-002", title="Collateral register not available for LGD development", status="Open", severity="Medium",
    description="LGD development cannot calibrate haircuts without collateral values and allocation to facilities.",
    remediation="Deliver a collateral register extract (type, value, valuation date, allocation) to Risk Analytics.",
    initiated_by=AUDITOR, assigned_to="Ahmed Al-Kuwari", created="2026-08-20", due="2027-02-20", source="Internal Audit")
req("FND", "QDB-CR-002", title="Sector mapping table not version-controlled", status="Closed", severity="Low",
    description="The mapping of economic activity codes to rating templates is kept in an uncontrolled spreadsheet.",
    remediation="Move the mapping under version control.", initiated_by=PRIYA, assigned_to="Omar Farouk",
    created="2025-11-20", due="2026-05-20", closed="2026-02-10", outcome="Closed", source="Validation",
    thread=[("2025-11-20", PRIYA, "The mapping of economic activity codes to rating templates is kept in an uncontrolled spreadsheet."),
            ("2026-02-01", "Omar Farouk", "Mapping now in the controlled repository."),
            ("2026-02-10", PRIYA, "[Closure] Verified.")])

REQ_BY_ID = {r["request_id"]: r for r in REQUESTS}

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


mc = next(r for r in REQUESTS if r["model_id"] == "QDB-IF-005" and r["type"] == "MC")
eid = evidence("QDB-IF-005", "request_response", mc["thread"][2]["response_id"], "scenario_weights_v2_design_note.txt",
               "Document", "Design note for density-based scenario weights", "Lina Haddad", "2026-08-04T10:00:00",
               "Scenario weights v2.0 — design note\nWeights = normal density at each fixed scenario anchor, centred on the IMF forecast, normalised to 100%.")
mc["thread"][2]["evidence_ids"].append(eid)
eid = evidence("QDB-IF-006", "request_response", fnd_ecl["thread"][1]["response_id"], "ecl_recalculation_plan.txt",
               "Document", "Plan for independent ECL recalculation", "Fatima Al-Sulaiti", "2025-04-20T09:30:00",
               "Independent ECL recalculation plan\nScope: sample of 200 facilities across stages.")
fnd_ecl["thread"][1]["evidence_ids"].append(eid)
eid = evidence("QDB-CR-001", "request_response", fnd_cr["thread"][1]["response_id"], "override_rate_extract_q2_2026.txt",
               "Data extract", "Q2 2026 rating override extract", "Ahmed Al-Kuwari", "2026-07-15T14:00:00",
               "Override extract Q2 2026\nOverrides: 24% of rated obligors.")
fnd_cr["thread"][1]["evidence_ids"].append(eid)
evidence("QDB-IF-002", "model", "QDB-IF-002", "lgd_data_gap_analysis.txt", "Document",
         "LGD data gap analysis on the 2016–2026 loan tape", "Rajesh Nair", "2026-08-12T11:00:00",
         "LGD data gap analysis\nMissing: collateral register, guarantee register, collection split by cash type.",
         doc_type="Data Quality Assessment")
val_pd = next(r for r in REQUESTS if r["model_id"] == "QDB-IF-001" and r["type"] == "VAL" and r["closed_date"] == "2025-10-15")
evidence("QDB-IF-001", "validation_request", val_pd["request_id"], "pd_validation_report_2025.txt", "Document",
         "Annual validation report 2025", PRIYA, "2025-10-15T16:00:00",
         "IFRS 9 PD model — annual validation report 2025\nRating: Fit with Conditions.")

# ---------------------------------------------------------------- monitoring
QUARTERS = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
SERIES = [
    ("QDB-IF-001", "PD Backtest Ratio", 1.02, 1.12, 0.02, 1.20, 1.40, False),
    ("QDB-IF-001", "PSI", 0.04, 0.08, 0.008, 0.10, 0.25, False),
    ("QDB-IF-003", "CCF Backtest Ratio", 0.92, 0.96, 0.02, 1.10, 1.25, False),
    ("QDB-IF-004", "Stage 2 Ratio (%)", 8.5, 11.0, 0.4, 14.0, 18.0, False),
    ("QDB-IF-004", "Staging Override Rate (%)", 3.5, 4.5, 0.4, 8.0, 12.0, False),
    ("QDB-IF-005", "Scenario Forecast Error (%)", 6.0, 11.5, 0.8, 10.0, 15.0, False),
    ("QDB-IF-006", "Unexplained ECL Movement (%)", 2.0, 4.0, 0.5, 5.0, 10.0, False),
    ("QDB-CR-001", "Gini", 0.56, 0.53, 0.01, 0.50, 0.45, True),
    ("QDB-CR-001", "Override Rate (%)", 18.0, 24.0, 1.0, 15.0, 25.0, False),
    ("QDB-CR-002", "Gini", 0.57, 0.48, 0.01, 0.50, 0.45, True),
    ("QDB-CR-002", "PSI", 0.05, 0.12, 0.008, 0.10, 0.25, False),
    ("QDB-PR-001", "Realised vs Priced Margin Variance (%)", 4.0, 6.0, 0.7, 8.0, 12.0, False),
    ("QDB-ML-001", "LCR Forecast Error (%)", 2.5, 4.5, 0.6, 5.0, 8.0, False),
    ("QDB-ML-002", "NII Forecast Error (%)", 3.0, 4.0, 0.6, 6.0, 10.0, False),
    ("QDB-NF-001", "High-Risk Customer Share (%)", 9.0, 16.0, 0.6, 12.0, 15.0, False),
]


def rag(value, amber, red, hib):
    if hib:
        return "Red" if value < red else "Amber" if value < amber else "Green"
    return "Red" if value > red else "Amber" if value > amber else "Green"


MONITORING = []
for mid, metric, start, end, noise, amber, red, hib in SERIES:
    for i, q in enumerate(QUARTERS):
        base = start + (end - start) * i / (len(QUARTERS) - 1)
        v = round(base + random.uniform(-noise, noise), 4)
        if i == len(QUARTERS) - 1:
            v = round(end, 4)
        MONITORING.append({
            "model_id": mid, "metric": metric, "period": q, "value": v,
            "amber_threshold": amber, "red_threshold": red, "higher_is_better": hib,
            "rag": rag(v, amber, red, hib),
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
    event(first, "Maryam Al-Kaabi", "register_model", "model", m["model_id"], m["model_id"],
          f"Model registered in the inventory: {m['name']}")
    for c in m["change_log"]:
        author = c["author"] if c["author"] in ROLE else "Maryam Al-Kaabi"
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
    with open(SEED / "monitoring.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(MONITORING[0].keys()))
        w.writeheader()
        w.writerows(MONITORING)
    print(f"{len(MODELS)} models, {len(REQUESTS)} requests, {len(EVIDENCE)} evidence files, "
          f"{len(MONITORING)} monitoring rows, {len(AUDIT)} audit events written to {SEED}")


if __name__ == "__main__":
    main()
