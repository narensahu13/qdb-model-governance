import pandas as pd

import streamlit as st
import auth
import governance
import tiering
import utils

utils.header(
    "How It Works",
    "Quick guide to the platform, then the model risk management framework behind it.",
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

tab_guide, tab_def, tab_tier, tab_lifecycle, tab_committee, tab_workflow, tab_roadmap = st.tabs(
    ["Quick guide", "Model Definition & Scope", "Risk Tiering", "Model Lifecycle", "Approval & 3LoD",
     "Workflows & Roles", "Implementation Roadmap"]
)

with tab_guide:
    st.markdown(
        """
**Start with *My Tasks*** — it lists everything waiting on you. Each model's page shows its
**next step** at the top.

**Who is who**

| Role | What they do here |
|---|---|
| **Model owner** | Accountable for the model. Registers it, keeps its record up to date, submits it for validation, approves it first, answers findings, reports KMPIs, gives the annual confirmation, requests decommissioning |
| **Model developer** | Builds and changes the model. Uploads documents, answers the validator's information requests, records model changes, reports KMPIs |
| **Model sponsor** | Senior executive accountable for the model's use — for example the CRO, CFO or a business head. Approves the model after its owner, decides on tier overrides and on decommissioning |
| **Model user** | Uses the model's output. Read-only |
| **Model validator** | QDB validator or external consultant, independent of the model. Validates, raises findings, verifies conditions and implementation, reviews KMPI returns |
| **Internal auditor** | Third line. Reviews the framework, may raise findings |
| **MRM administrator** | Keeps the inventory and people up to date, assigns validators, chases late KMPI returns and confirmations. Cannot approve or close |

**A model's five steps before use**

1. **Tier confirmed** — the owner proposes a tier; the MRM function confirms it.
2. **Submitted for validation** — once the required documents are uploaded.
3. **Validation signed off** — the validator scopes the work, asks for information, sends a draft to the
   owner for a factual check (7 days), then signs off with a rating.
4. **Approved** — by the model owner, then the model sponsor, possibly with conditions.
5. **Implementation verified** — a validator checks the deployed version is the approved one.

Models already in use are revalidated on their cycle (annual, two-yearly or three-yearly by tier);
a **material change** sends a model back through steps 3–5. Findings are raised during validation or
audit, answered by the owner and closed by whoever raised them.

**While in use**

- **KMPIs** — each model has key model performance indicators (KMPI-001 …), each with a description
  that states its pass/fail criterion. The model's owner sets how often they are reported (monthly,
  quarterly, semi-annual or annual). Within 30 days of each period end the owner or developer fills
  in Value, Result (Pass / Fail / Not available) and Comment — in the table or by uploading the Excel
  template — and submits; the validator reviews, sends it back, or raises a finding. A model needs at
  least one KMPI before it goes into use.
- **Annual confirmation** — once a year the owner ticks three statements: the record is accurate,
  the model is used as approved, the limitations and KMPIs still fit.
- **Decommissioning** — the owner asks to retire a model (reason, replacement, last day of use); the
  sponsor approves. The record is kept, read-only.
"""
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

**How a candidate is classified:** the *Register Model / Tool* page asks five identification
questions. Models go to the inventory; calculation tools used for decisions go to the EUC
register; AI systems that are not models go to the AI register; everything else is recorded
as "not a model" so the decision can be evidenced.
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
is their sum (3–9). The tier is then assigned **automatically by rule** — any override needs a
written reason and the model sponsor's approval:
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
            "KMPI reporting (typical)": [
                "Quarterly or monthly; KMPIs for discrimination, calibration, stability and data",
                "Quarterly or semi-annual",
                "Semi-annual or annual, proportionate",
            ],
            "Documentation Standard": ["Full suite (6 artefacts)", "Full suite", "Proportionate (core 4 artefacts)"],
        }
        )
        st.dataframe(tier_df, hide_index=True, width="stretch")
        st.caption(
            "Tiers are computed by the rules above; any expert-judgement adjustment requires "
            "the model sponsor's approval and is recorded in the model's audit trail. Every tier is "
            "approved by its owner and then its sponsor."
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
    Approval [label="4. Approval\\n(owner, then sponsor)"];
    Implementation [label="5. Implementation\\n& UAT"];
    Monitoring [label="6. KMPIs, annual confirmation\\n& periodic revalidation"];
    Change [label="7. Change /\\nRecalibration"];
    Retirement [label="8. Decommissioning\\n(owner asks, sponsor approves)"];
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

- No model enters production without independent validation and approval by its owner and sponsor (interim use needs the sponsor's approval, compensating controls and a defined expiry)
- Every model has a named **owner**, **developer** and **independent validator** — the developer can never validate their own model
- **Ongoing monitoring** through KMPIs with pass/fail criteria, reported at each model's own frequency; the validator reviews each return and raises a finding for fails that need action
- **Annual confirmation** by each owner that the record still holds; **decommissioning** approved by the sponsor, with the record kept
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
- **Model owner, then model sponsor** — approve each model (every tier) and its conditions, after the validator has signed off; the sponsor also decides on tier overrides. A senior executive such as the CRO approves as the sponsor of the models they sponsor
- **Four-eyes** — the sponsor is always a different person from the owner and the developer; the validator is independent of all three
- **Board Risk Committee** — approves the MRM policy and model risk appetite; receives a quarterly model risk report (KMPI position, overdue validations, open high findings)
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
- **Lifecycle gates G1–G5.** Tier confirmed → submitted for validation with the required
  documents → validation signed off → approved by the model owner and then the model sponsor,
  with tracked conditions → implementation verified by a validator (and at least one KMPI
  defined). A model cannot be put into use without passing all five.
- **KMPIs.** Each model has a short list of KMPIs: ID, name, and a description with the
  pass/fail criterion. Each period the owner or developer records Value, Result and Comment
  (typed in or uploaded from the Excel template), explains every fail, and submits; the
  validator reviews, sends back, or raises a finding. The description is copied into each
  return, so later edits do not rewrite history.
- **Annual confirmation and decommissioning.** The owner confirms each model once a year;
  retiring a model needs the sponsor's approval and keeps the record read-only.
- **Validation engagement.** The validator sets the scope and declares independence, raises
  information requests that owners answer with evidence, issues a draft with a proposed
  rating, the owner gives a factual-accuracy review (7 days), and the validator signs off.
- **My Tasks.** Every person sees what is waiting on them, with due dates.
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
                "0 Foundations (weeks 1–4) — built",
                "1 Inventory (weeks 5–8) — built",
                "2 Validation workflow (weeks 9–16) — built",
                "3 Issues and monitoring (weeks 17–22) — partly built",
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
                "KMPIs with pass/fail returns, annual confirmation, decommissioning (built); "
                "remediation plans, extensions and risk acceptance, exceptions register",
                "Model landscape map, health heatmap, quarterly model risk report, "
                "audit dossier",
                "User testing with the pilot models; decision on production",
            ],
        }
    )
    st.dataframe(roadmap, hide_index=True, width="stretch")
    st.markdown(
        """
**Priorities visible in the pilot inventory**

1. Revalidate the **macroeconomic scenario weights (QDB-005)** — version 2.0 is in use before revalidation
2. Commission the overdue validation of the **ECL engine (QDB-006)** and close its high finding on independent recalculation
3. Complete initial validation of the **transaction scoring model (QDB-010)**, including QCB AI Guideline bias and explainability tests, before pilot use
4. Unblock the **LGD model (QDB-002)** by delivering the collateral register
"""
    )
