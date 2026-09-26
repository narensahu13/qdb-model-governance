import pandas as pd

import streamlit as st
import auth
import tiering
import utils

utils.header(
    "Model Governance Framework",
    "Proposed Model Risk Management framework for Qatar Development Bank — the policy foundation behind this platform.",
)

st.markdown(
    """
This page summarises the proposed **Model Risk Management (MRM) Framework** that this platform
operationalises. It is aligned to leading international standards — **Fed SR 11-7**
(Supervisory Guidance on Model Risk Management), **PRA SS1/23**, **ECB guidance on internal models** —
and to Qatar's local regulatory context: **Qatar Central Bank (QCB)** instructions, **IFRS 9**
requirements, and **Qatar AML/CFT Law No. 20 of 2019**.
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
Following SR 11-7, a **model** is a quantitative method, system, or approach that applies
statistical, economic, financial, or mathematical theories, techniques, and assumptions to
process input data into quantitative estimates. This includes:

- **Statistical and machine-learning models** (scorecards, rating models, ML classifiers)
- **Parameter estimation models** (IFRS 9 PD/LGD/EAD, CCFs, haircuts)
- **Projection and simulation models** (stress testing, liquidity cashflow projections, IRRBB)
- **Vendor and third-party models** (AML monitoring, sanctions screening, pricing services) —
  vendor models are **in scope** and subject to compensating validation controls
- **Deterministic tools with judgemental calibration** (scenario weights, overlays, haircut tables)

**Excluded:** purely arithmetic calculators with no estimation component (e.g. simple interest
computation), subject to a documented End-User Computing (EUC) register.
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
is their sum (3–9). The tier is then assigned **automatically by rule** — no manual override
without Model Risk Committee approval:
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
                "High materiality or regulatory impact (IFRS 9 suite, ICAAP, AML, liquidity)",
                "Moderate materiality; complex but advisory; vendor pricing",
                "Low materiality, simple, transparent methods",
            ],
            "Validation Frequency": ["Annual", "Biennial", "Triennial"],
            "Validator": [
                "Independent (external or dedicated MVU)",
                "Model Validation Unit",
                "Model Validation Unit (proportionate scope)",
            ],
            "Approval Body": [
                "Model Risk Committee (+ Board committee noting for financial-statement models)",
                "Model Risk Committee",
                "Head of Model Validation (delegated)",
            ],
            "Documentation Standard": ["Full suite (6 artefacts)", "Full suite", "Proportionate (core 4 artefacts)"],
        }
        )
        st.dataframe(tier_df, hide_index=True, width="stretch")
        st.caption(
            "Tiers are computed by the rules above; any expert-judgement adjustment requires "
            "Model Risk Committee approval and is recorded in the model's audit trail."
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
    Approval [label="4. Approval\\n(MRC / delegated)"];
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

- No model enters production without independent validation and formal approval (exception process requires MRC-approved interim use with compensating controls and a defined expiry)
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
**Committee structure (proposed)**

- **Board Risk Committee** — approves MRM policy and risk appetite; receives quarterly model risk report; notes Tier 1 approvals affecting financial statements
- **Model Risk Committee (MRC)** *(new — to be established)* — approves models and tiering, tracks validation findings and remediation, owns the inventory; meets monthly; chaired by CRO
- **ALCO / Board Compliance Committee** — use-level approval for treasury and financial-crime models respectively, in coordination with MRC
"""
        )
    with c2:
        st.markdown(
            """
**Three lines of defence**

- **1st line — Model owners & developers:** develop, use, document and monitor models; maintain data quality; report breaches
- **2nd line — Model Validation Unit (MVU)** *(new — to be established)*: independent validation, tiering methodology, inventory management, policy compliance monitoring
- **3rd line — Internal Audit:** periodic audit of the MRM framework's design and operating effectiveness
"""
        )
    st.info(
        "For a bank of QDB's size, the MVU can start as 1-2 dedicated FTEs supplemented by "
        "external validators (Big-4 or specialist firms) for Tier 1 and technically complex models — "
        "the operating model reflected in this PoC's mock data.",
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

- **Validation workflow (2nd line).** The Model Validation Unit records validations
  (initial, periodic, targeted, model-change reviews, vendor reviews) with outcome, tests
  and evidence attached **on that validation**. LoD 1 can also attach a supporting
  development pack to Material / Non-material Model Change validations without being
  the validator. The model's validation schedule updates automatically.
- **Model change workflow (1st line).** Model owners record changes with a
  **Material / Non-material** classification and may attach a change memo / code /
  approval email on the change itself; material changes move the model to
  *In Validation* — next step is the **Validation** tab to support revalidation.
- **Issue lifecycle (2nd/3rd → 1st → raiser).** Validation or Internal Audit raise issues
  (with optional evidence on the raise); the accountable first line **replies with
  remediation updates and evidence on the response**; the issue is closed **only by the
  line that raised it** (or the MRM Administrator), optionally with closure evidence.
- **Evidence in context (all lines).** There is no separate Evidence tab. Artefacts are
  attached where the work happens — validation, issue / response, model change, or
  audit review — with a file, category, and short description.
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
        "Enforced in code via a single permissions module (auth.py) — the one place where "
        "real authentication (SSO / AD roles) plugs in later without touching page code. "
        "Issue closure is further restricted to the specific line that raised the issue."
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
                "'In Validation' and the new version must not be used until the MVU records "
                "a satisfactory revalidation",
                "MVU notification only (automatic via the audit trail); deployment may proceed",
            ],
        }),
        hide_index=True, width="stretch",
    )

# ---------------------------------------------------------------- roadmap
with tab_roadmap:
    st.subheader("Implementation Roadmap (proposed)")
    roadmap = pd.DataFrame(
        {
            "Phase": ["Phase 1 (0-3 months)", "Phase 2 (3-6 months)", "Phase 3 (6-12 months)", "Phase 4 (12+ months)"],
            "Milestones": [
                "Board-approved MRM policy; complete model identification exercise; populate inventory; assign owners and tiers; establish MRC",
                "Stand up Model Validation Unit; prioritised validation of Tier 1 models never validated; remediation plans for all high findings",
                "Complete first full validation cycle; ongoing monitoring live for all Tier 1-2 models; quarterly board model risk reporting",
                "Workflow automation (approvals, attestations); integration with data lineage tooling (BCBS 239); annual framework review by Internal Audit",
            ],
        }
    )
    st.dataframe(roadmap, hide_index=True, width="stretch")
    st.markdown(
        """
**Immediate priorities visible in this PoC's data**

1. Regularise the **macroeconomic scenario model (QDB-IF-005)** — in production without validation or approval
2. Commission overdue validations: **SME Behavioural Scorecard (QDB-CR-002)** and **Liquidity Stress Testing model (QDB-ML-003)**
3. Close high-severity findings: **AML threshold tuning (QDB-OF-001)**, **corporate rating overrides (QDB-CR-003)**, **Al Dhameen claims calibration (QDB-CR-004)**
"""
    )
