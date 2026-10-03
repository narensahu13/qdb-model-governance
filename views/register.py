"""Register a model or tool: identification questionnaire, then the record.

Answering five questions decides whether the candidate is a model (model
inventory), an EUC tool, an AI tool that is not a model (AI register), or not
a model at all. Every decision is kept, so the inventory's completeness can be
evidenced to auditors and QCB.
"""

from datetime import date

import pandas as pd
import streamlit as st

import auth
import data_store
import governance
import tiering
import utils
from data_loader import load_models

utils.header(
    "Register a Model or Tool",
    "Identification questionnaire, then the inventory record. Models start with a proposed "
    "tier that the MRM function confirms (gate G1).",
)

if "_reg_flash" in st.session_state:
    kind, rid = st.session_state.pop("_reg_flash")
    st.success(f"{kind} **{rid}** registered.")
    if kind == "Model" and st.button(f"Open {rid}", key="reg_open"):
        utils.go_to_model(rid)

if not (auth.has_permission("register_model") or auth.has_permission("register_tool")):
    auth.permission_denied("register_model")
    st.stop()

user = auth.get_current_user()
models = load_models()
model_labels = {m["model_id"]: f"{m['model_id']} — {m['name']}" for m in models}

# ---------------------------------------------------------------- step 1
st.subheader("1 · Identification")
st.caption(
    "Based on the SR 26-2 model definition (complex quantitative methods are models; simple "
    "arithmetic and deterministic rules are not) and the QCB AI Guideline (every AI system "
    "is registered)."
)
answers = {}
for key, question in governance.IDENTIFICATION_QUESTIONS:
    answers[key] = st.radio(question, ["No", "Yes"], horizontal=True, key=f"idq_{key}") == "Yes"
result = governance.identify(answers)
color = utils.NAVY if result["classification"] == governance.CLASS_MODEL else utils.GOLD
st.markdown(
    f"**Outcome:** {utils.badge(result['classification'], color)}"
    + (utils.badge("AI system — QCB AI register", "#6a1b9a") if result["ai_system"] else "")
    + f"<br><span style='color:#555;'>{result['reason']}</span>",
    unsafe_allow_html=True,
)
st.divider()


def _ai_fields(prefix: str) -> dict:
    st.markdown("**QCB AI Guideline details**")
    a1, a2 = st.columns(2)
    with a1:
        cat = st.selectbox("Functional category", governance.AI_FUNCTIONAL_CATEGORIES, key=f"{prefix}_aicat")
        role = st.selectbox("QDB's role", governance.AI_PROVIDER_ROLES, key=f"{prefix}_airole")
    with a2:
        autonomy = st.selectbox("Human oversight", governance.AI_AUTONOMY, key=f"{prefix}_aiaut")
        high = st.checkbox("High-risk AI system (QCB classification)", key=f"{prefix}_aihigh")
    rec = {"ai_system": True, "qcb_ai_high_risk": high, "ai_functional_category": cat,
           "ai_provider_role": role, "ai_autonomy": autonomy}
    needed = governance.qcb_approval_required(rec)
    rec["qcb_approval_status"] = st.selectbox(
        "QCB approval status", governance.QCB_APPROVAL_STATUSES,
        index=1 if needed else 0, key=f"{prefix}_aiqcb",
        help="High-risk and fully autonomous AI systems need QCB approval before use.",
    )
    if needed:
        st.warning("QCB prior approval is required for this AI system before it is used.")
    return rec


owner_opts = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
own_label = auth.user_option_label(user)

# ---------------------------------------------------------------- step 2 — model
if result["classification"] == governance.CLASS_MODEL:
    if not auth.has_permission("register_model"):
        auth.permission_denied("register_model")
        st.stop()
    st.subheader("2 · Model record")
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Model name *", key="rm_name")
        risk_type = st.selectbox("Risk type *", governance.RISK_TYPES, key="rm_risk")
        category = st.text_input("Category", placeholder="e.g. Scoring, Parameter estimation", key="rm_cat")
        business_line = st.text_input("Business line", key="rm_bl")
        methodology = st.text_input("Methodology *", key="rm_meth")
        source = st.selectbox("Source", governance.SOURCES, key="rm_src")
        vendor = st.text_input("Vendor (if any)", key="rm_vendor")
    with c2:
        owner = st.selectbox("Model owner *", owner_opts,
                             index=auth.default_option_index(owner_opts, own_label), key="rm_owner")
        developer = st.text_input("Developer", value=own_label if user["role"] == "LOD1" else "",
                                  key="rm_dev")
        sponsor_opts = [auth.user_option_label(u) for u in auth.users_for_roles("SPONSOR")]
        sponsor = st.selectbox("Model sponsor *", sponsor_opts, key="rm_sponsor",
                               help="Senior executive who approves the model after its owner.")
        status = st.selectbox(
            "Lifecycle status *", ["In Development", "In Validation", "In Production"], key="rm_status",
            help="Choose In Production when recording a model that is already in use.",
        )
        approval_date = None
        if status == "In Production":
            known = st.checkbox("Formal approval on record", key="rm_appr_known")
            if known:
                approval_date = st.date_input("Approval date", value=date.today(), key="rm_appr").isoformat()
        version = st.text_input("Version", value="1.0", key="rm_ver")
        exposure = st.number_input("Exposure covered (QAR mn)", min_value=0, step=100, key="rm_exp")
    description = st.text_area("Purpose / description *", key="rm_desc")
    c3, c4 = st.columns(2)
    with c3:
        platform = st.text_input("Implementation platform", key="rm_plat")
        usage = st.text_input("Usage frequency", placeholder="e.g. Monthly batch", key="rm_usage")
        data_sources = st.text_area("Data sources (one per line)", key="rm_data")
        users_txt = st.text_area("Model users (one per line)", key="rm_users")
    with c4:
        assumptions = st.text_area("Key assumptions (one per line)", key="rm_ass")
        limitations = st.text_area("Known limitations (one per line)", key="rm_lim")
        regulatory = st.text_area("Regulatory mapping (one per line)", key="rm_reg")
        upstream = st.multiselect("Upstream models (feed this model)", list(model_labels),
                                  format_func=lambda i: model_labels[i], key="rm_up")

    st.markdown("**Uses** — each business use of the model and the decision it supports")
    uses_df = st.data_editor(
        pd.DataFrame([{"use": "", "business_area": "", "decision": "", "status": "Planned"}]),
        num_rows="dynamic", width="stretch", key="rm_uses",
        column_config={
            "use": "Use", "business_area": "Business area", "decision": "Decision supported",
            "status": st.column_config.SelectboxColumn("Status", options=governance.USE_STATUSES),
        },
    )

    ai_rec = _ai_fields("rm") if result["ai_system"] else {}

    st.subheader("3 · Proposed tier")
    t1, t2, t3 = st.columns(3)
    with t1:
        mat = st.selectbox("Materiality", tiering.LEVELS, index=1, key="rm_mat")
    with t2:
        comp = st.selectbox("Complexity", tiering.LEVELS, index=1, key="rm_comp")
    with t3:
        reg = st.selectbox("Regulatory impact", tiering.LEVELS, index=1, key="rm_regimp")
    tier = tiering.compute_tier(mat, comp, reg)
    st.markdown(
        f"{utils.tier_badge(tier['tier'])} <span style='color:#444;'>{tier['explanation']}</span>",
        unsafe_allow_html=True,
    )
    with st.expander("Scoring criteria"):
        st.dataframe(pd.DataFrame(tiering.criteria_rows()), hide_index=True, width="stretch")
    rationale = st.text_area("Tier rationale *", key="rm_rat")
    st.caption(
        f"Validation frequency {governance.validation_frequency(tier['tier'])} · approval by "
        f"{governance.approval_body(tier['tier'])}. The tier stays *proposed* until the MRM "
        "function confirms it."
    )

    if st.button("Register model", type="primary", key="rm_submit"):
        uses = [
            {k: (str(v).strip() if v is not None else "") for k, v in row.items()}
            for row in uses_df.to_dict("records") if str(row.get("use") or "").strip()
        ]
        try:
            new_id = data_store.register_model({
                "name": name, "risk_type": risk_type, "category": category,
                "business_line": business_line, "methodology": methodology, "source": source,
                "vendor": vendor.strip() or None, "owner": owner, "developer": developer,
                "sponsor": sponsor, "status": status, "approval_date": approval_date,
                "version": version, "exposure_covered_qar_mn": exposure,
                "description": description, "implementation_platform": platform,
                "usage_frequency": usage, "data_sources": data_sources, "model_users": users_txt,
                "key_assumptions": assumptions, "known_limitations": limitations,
                "regulatory_mapping": regulatory, "upstream": upstream, "uses": uses,
                "tier_scores": {"materiality": mat, "complexity": comp, "regulatory_impact": reg},
                "tier_rationale": rationale.strip(), **ai_rec,
            }, answers)
        except (PermissionError, ValueError) as exc:
            st.error(str(exc))
        else:
            if not rationale.strip():
                st.warning("Registered without a tier rationale — add one before sign-off.")
            st.session_state["_reg_flash"] = ("Model", new_id)
            st.rerun()

# ---------------------------------------------------------------- step 2 — tool
else:
    if not auth.has_permission("register_tool"):
        auth.permission_denied("register_tool")
        st.stop()
    st.subheader("2 · Register record")
    c1, c2 = st.columns(2)
    with c1:
        t_name = st.text_input("Name *", key="rt_name")
        t_owner = st.selectbox("Owner *", owner_opts,
                               index=auth.default_option_index(owner_opts, own_label), key="rt_owner")
        t_area = st.text_input("Business area", key="rt_area")
        t_platform = st.text_input("Platform", placeholder="e.g. Excel with macros", key="rt_plat")
    with c2:
        t_mat = st.selectbox("Materiality", ["High", "Medium", "Low"], index=2, key="rt_mat")
        t_controls = st.text_area("Controls in place", key="rt_ctrl",
                                  placeholder="e.g. version control, reconciliation, second-person review")
        t_related = st.multiselect("Related models", list(model_labels),
                                   format_func=lambda i: model_labels[i], key="rt_rel")
    t_desc = st.text_area("Description *", key="rt_desc")
    t_ai = _ai_fields("rt") if result["ai_system"] else {}
    if st.button(f"Record as {result['classification']}", type="primary", key="rt_submit"):
        try:
            tid = data_store.register_tool({
                "name": t_name, "owner": t_owner, "business_area": t_area, "platform": t_platform,
                "materiality": t_mat, "controls": t_controls, "related_models": t_related,
                "description": t_desc, **t_ai,
            }, answers)
        except (PermissionError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.session_state["_reg_flash"] = (result["classification"], tid)
            st.rerun()
