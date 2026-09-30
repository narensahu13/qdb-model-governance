import pandas as pd

import streamlit as st
import auth
import governance
import tiering
import utils

utils.header(
    "Model Governance Framework",
    "Proposed Model Risk Management framework for Qatar Development Bank — the policy foundation behind this platform.",
)

st.markdown(
    """
This page summarises the proposed **Model Risk Management (MRM) Framework** that this platform
operationalises. It is benchmarked to international guidance — the Federal Reserve's **SR 26-2**
(Revised Guidance on Model Risk Management, April 2026, which replaced SR 11-7), **PRA SS1/23** and
the **ECB guide to internal models** — and to Qatar's regulatory context: **Qatar Central Bank (QCB)**
instructions, the **QCB Artificial Intelligence Guideline** (2024, which applies to QDB as a
QCB-licensed bank), **IFRS 9**, and **Qatar AML/CFT Law No. 20 of 2019**.
"""
)

tab_def, tab_tier, tab_lifecycle, tab_committee, tab_workflow, tab_roadmap = st.tabs(
    ["Model Definition & Scope", "Risk Tiering", "Model Lifecycle", "Committees & 3LoD",
     "Workflows & Roles", "Implementation Roadmap"]
)

# ---------------------------------------------------------------- definition
with tab_def:
    st.subheader("What is a Model?")
    st.markdown(
        """
Following SR 26-2, a **model** is a complex quantitative method, system, or approach that applies
statistical, economic, financial, or mathematical theories, techniques, and assumptions to
process input data into quantitative estimates. This includes:

- **Statistical and machine-learning models** (scorecards, rating models, ML classifiers)
- **Parameter estimation models** (IFRS 9 PD/LGD/EAD, CCFs, haircuts)
- **Projection and simulation models** (stress testing, liquidity cashflow projections, IRRBB)
- **Vendor and third-party models** (AML monitoring, sanctions screening, pricing services) —
  vendor models are **in scope** and subject to compensating validation controls
- **Deterministic tools with judgemental calibration** (scenario weights, overlays, haircut tables)

**Excluded:** purely arithmetic calculators and deterministic rules with no estimation component
(e.g. simple interest computation), subject to a documented End-User Computing (EUC) register.

**AI systems:** SR 26-2 leaves generative and agentic AI out of scope, but the **QCB AI Guideline**
covers every AI system QDB develops, buys or outsources. AI models are therefore flagged in the
inventory (e.g. the transaction scoring model), recorded in the AI register filed with QCB, and
tested for bias and explainability at validation.
"""
    )
    st.info(
        "**Model risk** is the potential for adverse consequences from decisions based on incorrect "
        "or misused model outputs — arising from data deficiencies, methodological flaws, "
        "implementation errors, or inappropriate use.",
        icon="📌",
    )

# ---------------------------------------------------------------- tiering
with tab_tier:
    st.subheader("Risk-Based Tiering Methodology")
    st.markdown(
        """
Every model is assigned a tier at inventory registration (and re-assessed at each validation)
based on three dimensions scored High / Medium / Low:

1. **Materiality** — financial exposure influenced by the model (balance sheet coverage, P&L / provision impact)
2. **Complexity** — methodological sophistication, data intensity, transparency (ML and black-box vendor models score higher)
3. **Regulatory impact** — whether outputs feed regulatory returns, financial statements, or statutory compliance obligations

Each rating maps to points (High = 3, Medium = 2, Low = 1) and the **composite score**
is their sum (3–9). The tier is then assigned **automatically by rule** — any override needs
CRO approval and is reported to the Management Risk Committee:
"""
    )
    st.dataframe(
        pd.DataFrame(tiering.TIER_RULES, columns=["Tier", "Rule"]),
        hide_index=True, width="stretch",
    )

    with st.expander("Scoring criteria per dimension"):
        st.dataframe(pd.DataFrame(tiering.criteria_rows()), hide_index=True, width="stretch")

    st.subheader("Tiering Calculator")
    st.caption("Any combination of ratings — the tier is assigned automatically.")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        calc_mat = st.selectbox("Materiality", tiering.LEVELS, index=1, key="calc_materiality")
    with cc2:
        calc_comp = st.selectbox("Complexity", tiering.LEVELS, index=1, key="calc_complexity")
    with cc3:
        calc_reg = st.selectbox("Regulatory Impact", tiering.LEVELS, index=1, key="calc_regulatory")

    result = tiering.compute_tier(calc_mat, calc_comp, calc_reg)
    r1, r2 = st.columns([1, 3])
    r1.metric("Composite Score", f"{result['composite']} / 9")
    with r2:
        st.markdown(
            f"{utils.tier_badge(result['tier'])} <span style='color:#444;'>{result['explanation']}</span>",
            unsafe_allow_html=True,
        )
    with st.expander("Tier expectations (frequency, validator, approval)"):
        tier_df = pd.DataFrame(
        {
            "Tier": ["Tier 1 (High)", "Tier 2 (Medium)", "Tier 3 (Low)"],
            "Typical Profile": [
                "High materiality or regulatory impact (IFRS 9 suite, rating models, liquidity, AML)",
                "Moderate materiality; complex but advisory (pricing, bureau scores)",
                "Low materiality, simple, transparent methods",
            ],
            "Validation Frequency": [
                governance.FREQUENCY_BY_TIER[1][0],
                governance.FREQUENCY_BY_TIER[2][0],
                governance.FREQUENCY_BY_TIER[3][0],
            ],
            "Validator": [
                "Validator independent of the model; external consultant preferred",
                "QDB validator or consultant",
                "QDB validator or consultant (proportionate scope)",
            ],
            "Approval Body": [
                governance.APPROVAL_BODY_BY_TIER[1] + " (board noting for financial-statement models)",
                governance.APPROVAL_BODY_BY_TIER[2],
                governance.APPROVAL_BODY_BY_TIER[3],
            ],
            "Documentation Standard": ["Full suite (6 artefacts)", "Full suite", "Proportionate (core 4 artefacts)"],
        }
        )
        st.dataframe(tier_df, hide_index=True, width="stretch")
        st.caption(
            "Tiers are computed by the rules above; any expert-judgement adjustment requires "
            "CRO approval and is recorded in the model's audit trail."
        )

# ---------------------------------------------------------------- lifecycle
with tab_lifecycle:
    st.subheader("Model Lifecycle")
    st.graphviz_chart(
        """
digraph {
    rankdir=LR;
    node [shape=box, style="rounded,filled", fillcolor="#e8eef7", fontname="Arial", fontsize=11];
    Initiation [label="1. Initiation &\\nBusiness Case"];
    Development [label="2. Development\\n(data, methodology,\\ndocumentation)"];
    Validation [label="3. Independent\\nValidation"];
    Approval [label="4. Approval\\n(Mgmt Risk Committee / CRO)"];
    Implementation [label="5. Implementation\\n& UAT"];
    Monitoring [label="6. Ongoing Monitoring\\n& Annual Review"];
    Change [label="7. Change /\\nRecalibration"];
    Retirement [label="8. Retirement &\\nDecommissioning"];
    Initiation -> Development -> Validation -> Approval -> Implementation -> Monitoring;
    Monitoring -> Change [label="trigger breach /\\nperiodic revalidation"];
    Change -> Validation;
    Monitoring -> Retirement [label="obsolete /\\nreplaced"];
}
"""
    )
    st.markdown(
        """
**Key lifecycle controls**

- No model enters production without independent validation and formal approval (interim use needs CRO approval, compensating controls and a defined expiry)
- Every model has a named **owner**, **developer** and **independent validator** — the developer can never validate their own model
- **Ongoing monitoring** with model-appropriate KPIs and RAG thresholds; breaches trigger targeted review
- **Material changes** (methodology, key assumptions, use extension) require revalidation before deployment
- All lifecycle events are recorded in the inventory **audit trail**
"""
    )

# ---------------------------------------------------------------- committees
with tab_committee:
    st.subheader("Governance Structure & Three Lines of Defence")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            """
**Approval and oversight (QDB structure)**
- **Board Risk Committee** — approves the MRM policy and model risk appetite; receives a quarterly model risk report; notes Tier 1 approvals that affect the financial statements
- **Management Risk Committee** — approves Tier 1 models and their conditions; receives the model risk dashboard, overdue validations and open high findings
- **CRO** — approves Tier 2 and Tier 3 models (may delegate Tier 3), tier overrides, finding extensions and interim use before validation
- **ALCO / Compliance** — use-level sign-off for treasury and financial-crime models, alongside the approval above
"""
        )
    with c2:
        st.markdown(
            """
**Three lines of defence**
- **1st line — Model owners & developers:** develop, use, document and monitor models; maintain data quality; answer findings
- **2nd line — Validator:** a QDB validator or an external consultant performs independent validation and verifies finding closure; the MRM Administrator keeps the inventory and schedules work but has no approval or closure rights
- **3rd line — Internal Audit:** periodic audit of the MRM framework's design and operating effectiveness; may raise findings
"""
        )
    st.info(
        "QDB has no dedicated model validation unit: validation is done by one QDB validator or an "
        "external consultant. The platform enforces independence per model — an owner or developer "
        "can never be assigned to validate their own model.",
        icon="💡",
    )

# ---------------------------------------------------------------- workflows & roles
with tab_workflow:
    st.subheader("Governance Workflows Implemented in this Platform")
    st.markdown(
        """
The platform is a **workflow tool for all three lines of defence**, not just a read-only
register. Each user acts in a role (simulated via the sidebar selector in this PoC;
replaced by single sign-on in production), and every action is permission-checked and
recorded in the model's **audit trail**:

- **Three request types.** Work is tracked as **Model Change (MC)**, **Validation (VAL)**,
  or **Finding (FND)** — with typed IDs (`MC-###`, `VAL-###`, `FND-###`). Material vs
  non-material is a field on Model Change requests, not a separate type. Validation
  nature (Initial / Periodic / Targeted / Ad-hoc) is a light dropdown on VAL.
- **Model change (LoD1 / LoD2).** Owners record changes with a Material / Non-material
  classification; an MC request opens automatically. Material changes move the model to
  *In Validation* until the validator closes the MC with a rating.
- **Validation (LoD1 / LoD2 / LoD3).** Owners may request validation; the validator records
  it with a rating on the four-level scale (Fit for Purpose, Fit with Conditions, Restricted
  Use, Not Fit for Purpose), tests and evidence. Closed requests are read-only.
- **Finding lifecycle (LoD2/LoD3 → LoD1 → raiser).** The validator or Internal Audit raise
  findings; owners and validators discuss them in the thread with evidence; the finding is
  closed **only by the line that raised it** — never by the MRM Administrator.
- **Independence.** Validations and model changes cannot be assigned to the model's owner
  or developer.
- **Evidence in context (all lines).** Artefacts are attached where the work happens —
  request, thread response, model change, or audit review — with a file, category, and
  short description. Closed requests reject new uploads.
"""
    )

    st.subheader("Permissions Matrix (who can do what)")
    perm_rows = []
    for action, roles in auth.PERMISSIONS.items():
        row = {"Action": auth.ACTION_LABELS.get(action, action)}
        for role, label in auth.ROLE_LABELS.items():
            row[label] = "✅" if role in roles else "—"
        perm_rows.append(row)
    st.dataframe(pd.DataFrame(perm_rows), hide_index=True, width="stretch")
    st.caption(
        "Enforced twice — in the pages and again in the data layer, so no page can bypass it. "
        "Finding closure is further restricted to the line that raised the finding, and the "
        "MRM Administrator has no approval or closure rights (segregation of duties)."
    )

    st.subheader("Model Change Classification Policy")
    st.dataframe(
        pd.DataFrame({
            "Classification": ["Material", "Non-material"],
            "Examples": [
                "Methodology change, key assumption change, scope or use extension, "
                "recalibration materially affecting outputs",
                "Parameter refresh within approved ranges, cosmetic or reporting changes",
            ],
            "Required Process": [
                "Independent revalidation before deployment — model status moves to "
                "'In Validation' and the new version must not be used until the validator "
                "records a satisfactory rating",
                "Notification to the validator only (automatic via the audit trail); deployment may proceed",
            ],
        }),
        hide_index=True, width="stretch",
    )

# ---------------------------------------------------------------- roadmap
with tab_roadmap:
    st.subheader("Implementation Roadmap")
    st.caption("Six phases of about 30 weeks in total, each ending with a demo and sign-off. "
               "The PoC runs on free tools; production components only if QDB decides to go further.")
    roadmap = pd.DataFrame(
        {
            "Phase": [
                "0 Foundations (weeks 1–4)",
                "1 Inventory (weeks 5–8)",
                "2 Validation workflow (weeks 9–16)",
                "3 Issues and monitoring (weeks 17–22)",
                "4 Reporting (weeks 23–26)",
                "5 Pilot (weeks 27–30)",
            ],
            "Delivers": [
                "SQLite database, append-only hash-chained audit log, evidence fingerprints, "
                "governance rules enforced in the data layer, pilot inventory",
                "Identification questionnaire, model uses and versions, EUC and AI registers, "
                "tier sign-off, model factsheet export",
                "Lifecycle gates G1–G5, validation engagements with information requests, "
                "approval decisions with conditions, task inbox",
                "Remediation plans, extensions and risk acceptance, exceptions register, "
                "monitoring submissions with breach escalation",
                "Model landscape map, health heatmap, Management Risk Committee pack, "
                "audit dossier, annual attestation",
                "User testing with the pilot models; decision on production",
            ],
        }
    )
    st.dataframe(roadmap, hide_index=True, width="stretch")
    st.markdown(
        """
**Priorities visible in the pilot inventory**

1. Revalidate the **macroeconomic scenario weights (QDB-IF-005)** — version 2.0 is in use before revalidation
2. Commission the overdue validation of the **ECL engine (QDB-IF-006)** and close its high finding on independent recalculation
3. Complete initial validation of the **transaction scoring model (QDB-CR-010)**, including QCB AI Guideline bias and explainability tests, before pilot use
4. Unblock the **LGD model (QDB-IF-002)** by delivering the collateral register
"""
    )
