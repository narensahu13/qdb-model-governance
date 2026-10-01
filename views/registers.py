"""Registers: tier sign-off queue, EUC / identification register, QCB AI register."""

import pandas as pd
import streamlit as st

import auth
import governance
import utils
from data_loader import ai_register, load_models, load_tools

utils.header(
    "Registers",
    "Tier sign-offs awaiting action, tools that are not models, and the AI register "
    "for the QCB Artificial Intelligence Guideline.",
)

models = load_models()
tools = load_tools()
pending = [m for m in models if not m["tier_confirmed"]]
ai_rows = ai_register()

utils.kpi_cards([
    ("Tier sign-offs pending", str(len(pending)),
     f"{sum(1 for m in pending if m['tier_assessment']['status'] == governance.TIER_OVERRIDE_PENDING)} with the CRO"),
    ("EUC tools", str(sum(1 for t in tools if t["classification"] == governance.CLASS_EUC)), None),
    ("AI systems", str(len(ai_rows)),
     f"{sum(1 for r in ai_rows if r['qcb_approval_required'])} need QCB approval"),
    ("Identification decisions", str(len(models) + len(tools)), "models and tools"),
])

tab_tier, tab_euc, tab_ai = st.tabs(["Tier sign-off queue", "EUC and identification register",
                                     "AI register (QCB)"])

with tab_tier:
    st.caption(
        "Gate G1: a tier is proposed by the owner (or at registration), confirmed by the MRM "
        "function, and — if overridden — approved by the CRO. Act on each model's Overview tab."
    )
    if not pending:
        st.success("No tier assessments awaiting sign-off.")
    for m in pending:
        ta = m["tier_assessment"]
        from tiering import compute_tier
        proposed = compute_tier(**ta["scores"])["tier"]
        left, mid, right = st.columns([3.2, 4.5, 1.1])
        with left:
            st.markdown(
                f"**{m['model_id']} — {m['name']}**<br>"
                + utils.badge(ta["status"], utils.AMBER) + utils.tier_badge(proposed),
                unsafe_allow_html=True,
            )
        with mid:
            who = (f"Override to Tier {ta['override_tier']} requested by {ta['confirmed_by']}: "
                   f"{ta['override_reason']}") if ta["status"] == governance.TIER_OVERRIDE_PENDING else (
                   f"Proposed by {ta['proposed_by']} on {utils.fmt_date(ta['proposed_on'])}")
            st.markdown(f"<span style='font-size:0.88rem;'>{who}</span><br>"
                        f"<span style='color:#666; font-size:0.82rem;'>{ta.get('rationale') or ''}</span>",
                        unsafe_allow_html=True)
        with right:
            if st.button("Open", key=f"tier_open_{m['model_id']}", width="stretch"):
                utils.go_to_model(m["model_id"])
        st.divider()

with tab_euc:
    st.caption(
        "Everything assessed with the identification questionnaire that is not a model: "
        "end-user computing tools that need basic controls, AI tools, and 'not a model' "
        "decisions kept for traceability."
    )
    if tools:
        df = pd.DataFrame([{
            "ID": t["tool_id"], "Name": t["name"], "Classification": t["classification"],
            "Owner": t["owner"], "Business area": t.get("business_area"),
            "Platform": t.get("platform"), "Materiality": t.get("materiality"),
            "Controls": t.get("controls"), "Related models": ", ".join(t.get("related_models") or []),
            "AI": bool(t.get("ai_system")), "Registered": utils.fmt_date(t.get("registered_on")),
        } for t in tools])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"AI": st.column_config.CheckboxColumn(width="small")})
        st.download_button("Download register (CSV)", df.to_csv(index=False).encode("utf-8"),
                           "qdb_euc_register.csv", "text/csv", key="dl_euc")
    else:
        st.info("No tools registered yet.")
    if auth.has_permission("register_tool"):
        if st.button("Register a model or tool", key="go_register"):
            st.switch_page("views/register.py")

with tab_ai:
    st.caption(
        "QCB Artificial Intelligence Guideline: QDB keeps a register of all AI systems and files "
        "it with QCB annually. High-risk and fully autonomous systems need QCB approval before use."
    )
    if ai_rows:
        df = pd.DataFrame([{
            "ID": r["id"], "Name": r["name"], "Kind": r["kind"], "Owner": r["owner"],
            "Functional category": r.get("ai_functional_category"),
            "QDB role": r.get("ai_provider_role"), "Human oversight": r.get("ai_autonomy"),
            "High-risk": bool(r.get("qcb_ai_high_risk")),
            "QCB approval needed": r["qcb_approval_required"],
            "QCB approval status": r.get("qcb_approval_status"), "Status": r["status"],
        } for r in ai_rows])
        st.dataframe(df, hide_index=True, width="stretch", column_config={
            "High-risk": st.column_config.CheckboxColumn(width="small"),
            "QCB approval needed": st.column_config.CheckboxColumn(width="small"),
        })
        gaps = df[df["QCB approval needed"] & (df["QCB approval status"] != "Approved by QCB")]
        if not gaps.empty:
            st.warning(
                f"{len(gaps)} AI system(s) need QCB approval that has not been granted: "
                + ", ".join(gaps["ID"]) + "."
            )
        st.download_button("Download AI register (CSV) for the QCB filing",
                           df.to_csv(index=False).encode("utf-8"), "qdb_ai_register.csv",
                           "text/csv", key="dl_ai")
    else:
        st.info("No AI systems registered.")
