from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import streamlit as st
import auth
import data_store
import tiering
import utils
from data_loader import (
    get_model,
    load_audit_log,
    load_evidence,
    load_models,
    load_monitoring,
    load_validations,
    requests_for_model,
    validation_status,
)

ROOT = Path(__file__).resolve().parent.parent


def flash_and_rerun(msg: str):
    """Persist a success message across the rerun triggered after a write."""
    st.session_state["_flash"] = msg
    st.rerun()


def _evidence_for(linked_type: str, linked_id: str, evidence_all: list[dict]) -> list[dict]:
    return [
        e for e in evidence_all
        if e.get("linked_type") == linked_type and e.get("linked_id") == linked_id
    ]


def _render_evidence_rows(items: list[dict], key_prefix: str) -> None:
    """Compact list with download buttons for linked evidence."""
    if not items:
        st.caption("No evidence attached yet.")
        return
    for ev in sorted(items, key=lambda e: e.get("uploaded_at", ""), reverse=True):
        c1, c2, c3 = st.columns([3.5, 2.5, 1.2])
        with c1:
            st.markdown(
                f"**{ev['filename']}** · "
                f"<span style='color:#666; font-size:0.84rem;'>{ev.get('description', '')}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                utils.badge(ev["category"], utils.GOLD)
                + f"<span style='font-size:0.8rem; color:#888;'> "
                f"{ev['uploaded_by']} · {ev['uploaded_at'][:10]}</span>",
                unsafe_allow_html=True,
            )
        with c3:
            fpath = ROOT / ev["stored_path"]
            if fpath.exists():
                st.download_button(
                    "Download",
                    data=fpath.read_bytes(),
                    file_name=ev["filename"],
                    key=f"dl_{key_prefix}_{ev['evidence_id']}",
                    width="stretch",
                )
            else:
                st.caption("Missing")


def _render_attach_form(
    model_id: str,
    linked_type: str,
    linked_id: str,
    form_key: str,
    caption: str | None = None,
) -> None:
    """File + category + short description — in-context attach for any role with upload_evidence."""
    if not auth.has_permission("upload_evidence"):
        return
    if caption:
        st.caption(caption)
    with st.form(form_key, clear_on_submit=True):
        up = st.file_uploader(
            "File *", type=data_store.ALLOWED_UPLOAD_TYPES, key=f"{form_key}_file",
        )
        a1, a2 = st.columns(2)
        with a1:
            cat = st.selectbox("Category *", data_store.EVIDENCE_CATEGORIES, key=f"{form_key}_cat")
        with a2:
            desc = st.text_input("Short description *", key=f"{form_key}_desc")
        submitted = st.form_submit_button("Attach evidence")
    if submitted:
        if up is None:
            st.error("Choose a file to upload.")
        elif not desc.strip():
            st.error("A short description is required.")
        else:
            eid = data_store.attach_evidence(
                model_id, linked_type, linked_id, up, cat, desc.strip(),
            )
            flash_and_rerun(f"Evidence {eid} attached to {linked_type} {linked_id}.")


# Fresh-session identity: a new tab has no sidebar selector until page_setup
# runs (or never, if this view is executed standalone).
auth.get_current_user()

models = load_models()
model_ids = [m["model_id"] for m in models]
labels = {m["model_id"]: f"{m['model_id']} — {m['name']}" for m in models}

if not model_ids:
    st.error("No models in the inventory.")
    st.stop()

# Deep link support: /model_detail?model=<id> (inventory LinkColumn). Must run
# before any use of selected_model_id. Consume only the model param so the
# selectbox takes over on later interactions — do not clear the whole query
# string (that can break st.navigation page routing in a new tab).
qp_model = utils.read_model_query_param()
if qp_model:
    if qp_model in model_ids:
        st.session_state["selected_model_id"] = qp_model
    else:
        st.session_state["_invalid_model_qp"] = qp_model
    utils.drop_model_query_param()

if "_invalid_model_qp" in st.session_state:
    bad = st.session_state.pop("_invalid_model_qp")
    st.warning(f"Unknown model ID in the link: **{bad}**. Showing the first model instead.")

default_id = st.session_state["selected_model_id"] if "selected_model_id" in st.session_state else model_ids[0]
if default_id not in model_ids:
    default_id = model_ids[0]

model_label_opts = [labels[mid] for mid in model_ids]
selected_label = st.selectbox(
    "Select model",
    model_label_opts,
    index=model_ids.index(default_id),
)
selected = model_ids[model_label_opts.index(selected_label)]
st.session_state["selected_model_id"] = selected

# Keep request selection scoped to the current model.
if st.session_state.get("_md_req_model") != selected:
    st.session_state["_md_req_model"] = selected
    st.session_state.pop("md_selected_request", None)

m = get_model(selected)
if m is None:
    st.error(f"Model **{selected}** was not found in the inventory.")
    st.stop()

vstatus = validation_status(m)
tier_info = tiering.compute_tier(**m["tier_scores"])

if "_flash" in st.session_state:
    st.success(st.session_state.pop("_flash"))

utils.header(f"{m['model_id']} — {m['name']}", m["business_line"])
st.markdown(
    utils.tier_badge(tier_info["tier"])
    + utils.status_badge(m["status"])
    + utils.validation_badge(f"Validation: {vstatus}")
    + utils.badge(m["risk_type"], utils.RISK_TYPE_COLORS.get(m["risk_type"], utils.GREY))
    + utils.badge(m["source"], utils.NAVY),
    unsafe_allow_html=True,
)
st.markdown("")

validations = load_validations()
model_validations = validations[validations["model_id"] == selected]
model_requests = requests_for_model(selected)
monitoring = load_monitoring()
model_monitoring = monitoring[monitoring["model_id"] == selected]

evidence_all = load_evidence()
model_evidence = [e for e in evidence_all if e["model_id"] == selected]
evidence_by_id = {e["evidence_id"]: e for e in evidence_all}

tab_overview, tab_gov, tab_val, tab_perf, tab_docs = st.tabs([
    "Overview",
    "Governance & Lifecycle",
    "Validation & Findings",
    "Performance Monitoring",
    "Documentation & Audit",
])

# ================================================================ Overview
with tab_overview:
    st.markdown(f"**Purpose.** {m['description']}")

    scores = m["tier_scores"]
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Tier", f"T{tier_info['tier']}", f"{tier_info['composite']}/9")
    k2.metric("Materiality", scores["materiality"])
    k3.metric("Complexity", scores["complexity"])
    k4.metric("Reg. Impact", scores["regulatory_impact"])
    k5.metric("Last validation", m["last_validation"] or "Never")
    k6.metric("Next due", m["next_validation_due"] or "—")

    d1, d2, d3 = st.columns(3)
    d1.caption(f"Approved **{m['approval_date'] or 'not approved'}** · {m['validation_frequency']}")
    d2.caption(f"Exposure **QAR {m['exposure_covered_qar_mn']:,} mn**")
    d3.caption(f"Platform **{m['implementation_platform']}** · {m['usage_frequency']}")

    with st.expander("Identification & use"):
        ident = pd.DataFrame(
            {
                "Field": ["Model ID", "Version", "Risk Type", "Category", "Business Line",
                          "Methodology", "Source", "Implementation Platform", "Usage Frequency",
                          "Exposure Covered (QAR mn)", "Last Review Date"],
                "Value": [m["model_id"], m["version"], m["risk_type"], m["category"],
                          m["business_line"], m["methodology"], m["source"],
                          m["implementation_platform"], m["usage_frequency"],
                          f"{m['exposure_covered_qar_mn']:,}", m["last_review_date"] or "-"],
            }
        )
        st.dataframe(ident, hide_index=True, width="stretch")
        st.markdown("**Data sources**")
        st.markdown(
            " ".join(utils.badge(s, utils.GREY) for s in m["data_sources"]),
            unsafe_allow_html=True,
        )
        st.markdown("**Model users**")
        st.markdown(
            " ".join(utils.badge(u, "#1d3a6b") for u in m["model_users"]),
            unsafe_allow_html=True,
        )

    with st.expander("Tiering detail"):
        st.markdown(
            f"{utils.tier_badge(tier_info['tier'])} <span style='color:#444;'>{tier_info['explanation']}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"Rationale: {m['tier_rationale']}")
        st.caption(
            f"Exposure covered by this model: **QAR {m['exposure_covered_qar_mn']:,} mn** — "
            "a key driver of the materiality rating above."
        )
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Materiality", scores["materiality"], f"{tier_info['points']['materiality']} pts", delta_color="off")
        sc2.metric("Complexity", scores["complexity"], f"{tier_info['points']['complexity']} pts", delta_color="off")
        sc3.metric("Regulatory Impact", scores["regulatory_impact"], f"{tier_info['points']['regulatory_impact']} pts", delta_color="off")
        sc4.metric("Composite Score", f"{tier_info['composite']} / 9")
        st.markdown(
            "Each dimension is rated High (3 pts) / Medium (2 pts) / Low (1 pt); "
            "the composite score is their sum (3–9). The tier is then assigned automatically by rule:"
        )
        st.dataframe(
            pd.DataFrame(tiering.TIER_RULES, columns=["Tier", "Rule"]),
            hide_index=True, width="stretch",
        )
        st.markdown("**Scoring criteria per dimension**")
        st.dataframe(
            pd.DataFrame(tiering.criteria_rows()),
            hide_index=True, width="stretch",
        )

    with st.expander("Assumptions & limitations"):
        a1, a2 = st.columns(2)
        with a1:
            st.markdown("**Key assumptions**")
            for ka in m["key_assumptions"]:
                st.markdown(f"- {ka}")
        with a2:
            st.markdown("**Known limitations**")
            for kl in m["known_limitations"]:
                st.markdown(f"- {kl}")

    with st.expander("Regulatory mapping"):
        st.markdown(
            " ".join(utils.badge(r, utils.NAVY) for r in m["regulatory_mapping"]),
            unsafe_allow_html=True,
        )

    with st.expander("Model dependencies"):
        dep_up, dep_down = st.columns(2)
        with dep_up:
            st.markdown("**Upstream (feeds this model)**")
            if m["dependencies"]["upstream"]:
                for dep in m["dependencies"]["upstream"]:
                    dep_m = get_model(dep)
                    dep_label = f"{dep} — {dep_m['name']}" if dep_m else dep
                    if st.button(dep_label, key=f"up_{dep}"):
                        utils.go_to_model(dep)
            else:
                st.caption("None")
        with dep_down:
            st.markdown("**Downstream (consumes this model's output)**")
            if m["dependencies"]["downstream"]:
                for dep in m["dependencies"]["downstream"]:
                    dep_m = get_model(dep)
                    dep_label = f"{dep} — {dep_m['name']}" if dep_m else dep
                    if st.button(dep_label, key=f"down_{dep}"):
                        utils.go_to_model(dep)
            else:
                st.caption("None")

# ================================================================ Governance
with tab_gov:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ownership & Accountability")
        own = pd.DataFrame(
            {
                "Role": ["Model Owner", "Developer", "Independent Validator", "Business Sponsor", "Approval Body"],
                "Assigned": [m["owner"], m["developer"], m["validator"], m["sponsor"], m["approval_body"]],
            }
        )
        st.dataframe(own, hide_index=True, width="stretch")

    with c2:
        st.subheader("Three Lines of Defence")
        lod = m["lod_mapping"]
        lod_df = pd.DataFrame(
            {
                "Line": ["1st Line", "2nd Line", "3rd Line"],
                "Responsibility": [lod["first_line"], lod["second_line"], lod["third_line"]],
            }
        )
        st.dataframe(lod_df, hide_index=True, width="stretch")

    st.subheader("Lifecycle & Validation Schedule")
    l1, l2, l3, l4 = st.columns(4)
    l1.metric("Approval Date", m["approval_date"] or "Not approved")
    l2.metric("Last Validation", m["last_validation"] or "Never")
    l3.metric("Next Validation Due", m["next_validation_due"] or "-")
    l4.metric("Frequency", m["validation_frequency"])

    if vstatus in ("Overdue", "Never Validated"):
        st.error(f"Validation status: **{vstatus}**. This Tier {tier_info['tier']} model requires immediate scheduling of independent validation.")
    elif vstatus == "Due Soon":
        st.warning("Validation due within 90 days — validation should be commissioned now.")
    else:
        st.success("Validation schedule on track.")

    if m["approval_date"] is None and m["status"].startswith("In Production"):
        st.error("This model is in production **without formal approval** — a breach of the model governance policy requiring escalation to the Model Risk Committee.")

    if m.get("pending_revalidation"):
        st.warning(
            "**Material change recorded — independent revalidation pending.** "
            "Open the **Validation & Findings** tab to attach your development pack to the "
            "Model Change (MC) request (or to the change entry below).",
            icon="⚠️",
        )

    # Timeline of key lifecycle events
    events = []
    for entry in m["change_log"]:
        events.append({"date": entry["date"], "event": f"v{entry['version']}: {entry['description'][:60]}", "type": "Change"})
    if m["approval_date"]:
        events.append({"date": m["approval_date"], "event": "Formal approval", "type": "Approval"})
    for _, v in model_validations.iterrows():
        events.append({"date": v["date"].strftime("%Y-%m-%d"), "event": f"Validation: {v['outcome']}", "type": "Validation"})
    for _, a in pd.DataFrame(m["audit_reviews"]).iterrows() if m["audit_reviews"] else []:
        events.append({"date": a["date"], "event": f"Internal audit: {a['rating']}", "type": "Audit"})

    if events:
        st.subheader("Lifecycle Timeline")
        ev = pd.DataFrame(events)
        ev["date"] = pd.to_datetime(ev["date"])
        ev = ev.sort_values("date")
        type_colors = {"Change": utils.GREY, "Approval": utils.GREEN, "Validation": utils.NAVY, "Audit": utils.GOLD}
        fig = go.Figure()
        for etype, group in ev.groupby("type"):
            fig.add_trace(go.Scatter(
                x=group["date"], y=[etype] * len(group),
                mode="markers+text",
                marker=dict(size=14, color=type_colors.get(etype, utils.GREY)),
                text=group["event"], textposition="top center", textfont=dict(size=10),
                name=etype, hovertext=group["event"],
            ))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                          yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

    # ------------------------------------------------ Record Model Change (LoD 1)
    if auth.has_permission("record_change"):
        with st.expander("Record model change", expanded=False):
            st.info(
                "**Change classification policy.** **Material** changes — methodology, key "
                "assumptions, scope/use extension, or recalibration materially affecting outputs — "
                "require **independent revalidation before deployment** (model moves to "
                "*In Validation*). **Non-material** changes — parameter refresh within approved "
                "ranges, cosmetic/reporting changes — require **MVU notification only**.",
                icon="📋",
            )
            with st.form("change_form", clear_on_submit=True):
                cg1, cg2, cg3 = st.columns(3)
                with cg1:
                    chg_date = st.date_input("Change date", value=date.today(), key="chg_date")
                with cg2:
                    chg_version = st.text_input(
                        "New version *", placeholder=f"current: {m['version']}", key="chg_version",
                    )
                with cg3:
                    chg_class = st.selectbox(
                        "Change classification *", ["Material", "Non-material"], key="chg_class",
                    )
                chg_desc = st.text_area("Description of change *", key="chg_desc")
                chg_just = st.text_area("Justification for classification *", key="chg_just")
                chg_file = st.file_uploader(
                    "Evidence (optional) — change memo, code, approval email",
                    type=data_store.ALLOWED_UPLOAD_TYPES, key="chg_evidence",
                )
                chg_ev_cat = st.selectbox(
                    "Evidence category", data_store.EVIDENCE_CATEGORIES, key="chg_ev_cat",
                )
                chg_ev_desc = st.text_input(
                    "Evidence description", key="chg_ev_desc",
                    placeholder="Short note if attaching a file",
                )
                chg_submit = st.form_submit_button("Record change", key="chg_submit")
            if chg_submit:
                if not chg_version.strip() or not chg_desc.strip() or not chg_just.strip():
                    st.error("New version, description and justification are required.")
                elif chg_file is not None and not chg_ev_desc.strip():
                    st.error("Provide a short evidence description when attaching a file.")
                else:
                    change_id = data_store.add_change_entry(selected, {
                        "date": chg_date.isoformat(),
                        "version": chg_version.strip(),
                        "description": chg_desc.strip(),
                        "author": auth.get_current_user()["name"],
                        "classification": chg_class,
                        "justification": chg_just.strip(),
                    })
                    if chg_file is not None:
                        data_store.attach_evidence(
                            selected, "change", change_id, chg_file,
                            chg_ev_cat, chg_ev_desc.strip(),
                        )
                    if chg_class == "Material":
                        flash_and_rerun(
                            f"Material change {change_id} (v{chg_version.strip()}) recorded — "
                            "model is In Validation. An **MC** request was opened on the "
                            "**Validation & Findings** tab for evidence and revalidation."
                        )
                    else:
                        flash_and_rerun(
                            f"Non-material change {change_id} (v{chg_version.strip()}) recorded. "
                            "An **MC** notification (Non-material) was opened for MVU on "
                            "Validation & Findings."
                        )
    else:
        auth.permission_denied("record_change")

    # Recent changes with in-context evidence
    st.subheader("Change history")
    if not m["change_log"]:
        st.caption("No change-log entries yet.")
    else:
        for entry in sorted(m["change_log"], key=lambda e: e["date"], reverse=True):
            cid = entry.get("change_id", f"{entry['date']}-{entry['version']}")
            klass = entry.get("classification", "—")
            with st.expander(
                f"{entry['date']} — v{entry['version']} ({klass}) — {entry['description'][:50]}",
                expanded=False,
            ):
                st.markdown(f"**Author:** {entry['author']}")
                st.markdown(f"**Description.** {entry['description']}")
                if entry.get("justification"):
                    st.caption(f"Classification justification: {entry['justification']}")
                st.markdown("**Attached evidence**")
                _render_evidence_rows(
                    _evidence_for("change", cid, evidence_all), f"chg_{cid}",
                )
                if auth.has_permission("upload_evidence"):
                    _render_attach_form(
                        selected, "change", cid, f"attach_chg_{cid}",
                        caption="Attach change memo, code diff, or approval email.",
                    )

# ================================================================ Validation & Findings
with tab_val:
    st.caption(
        "Three request types: **MC** (Model Change — materiality is a field) · "
        "**VAL** (Validation — Initial / Periodic / Targeted / Ad-hoc) · "
        "**FND** (Finding). Closed requests are read-only."
    )
    if m.get("pending_revalidation"):
        st.info(
            "**Revalidation pending after a material change.** "
            "Open the related **MC** request below to attach your development pack "
            "(or attach on the change entry under Governance & Lifecycle). "
            "LoD 2 closes the MC with an outcome when validation is complete.",
            icon="📎",
        )

    open_reqs = [r for r in model_requests if r["status"] != "Closed"]
    closed_reqs = [r for r in model_requests if r["status"] == "Closed"]
    fnd_open = [r for r in open_reqs if r["type"] == "FND"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Open / In Progress", len(open_reqs))
    k2.metric("Closed", len(closed_reqs))
    k3.metric("Open findings (FND)", len(fnd_open))
    k4.metric("High FND open", sum(1 for r in fnd_open if r.get("severity") == "High"))

    # ------------------------------------------------ Initiate request
    can_types = auth.initiable_types()
    if can_types:
        with st.expander("Initiate request", expanded=False):
            type_labels = {
                t: f"{t} — {auth.REQUEST_TYPES[t]['label']}" for t in can_types
            }
            # Type selector outside the form so conditional fields update immediately.
            ir_type_label = st.selectbox(
                "Request type *",
                [type_labels[t] for t in can_types],
                key="ir_type",
            )
            ir_type = next(t for t, lab in type_labels.items() if lab == ir_type_label)
            meta = auth.REQUEST_TYPES[ir_type]
            st.caption(meta["description"])

            assignee_roles = meta["default_assignee_roles"]
            assignee_opts = auth.user_option_labels(*assignee_roles) or [
                auth.user_option_label(auth.get_current_user())
            ]
            preferred = m.get("validator") if "LOD2" in assignee_roles else m.get("owner")
            a_idx = auth.default_option_index(assignee_opts, preferred)

            with st.form("initiate_request_form", clear_on_submit=True):
                ir_title = st.text_input("Title *", key="ir_title")
                ir_desc = st.text_area("Description *", key="ir_desc")
                ir_assigned = st.selectbox(
                    "Assign to *", assignee_opts, index=a_idx, key="ir_assigned",
                )
                st.caption(
                    "Assigning sets the request **In Progress**. "
                    "Production would also notify the assignee by email."
                )

                ir_subtype = None
                ir_materiality = None
                ir_outcome = None
                ir_tests: list[str] = []
                ir_severity = None
                ir_rem = None
                ir_due = None
                close_immediately = False

                if ir_type == "MC":
                    ir_materiality = st.selectbox(
                        "Materiality *",
                        data_store.MATERIALITY_OPTIONS,
                        key="ir_materiality",
                    )
                elif ir_type == "VAL":
                    ir_subtype = st.selectbox(
                        "Nature *", data_store.VAL_SUBTYPES, key="ir_subtype",
                    )
                    # LoD2/ADMIN may record a completed validation immediately
                    if auth.get_current_user()["role"] in ("LOD2", "ADMIN"):
                        close_immediately = st.checkbox(
                            "Record as completed (close with outcome now)",
                            value=True, key="ir_close_now",
                        )
                        if close_immediately:
                            ir_outcome = st.selectbox(
                                "Outcome *", data_store.VALIDATION_OUTCOMES, key="ir_outcome",
                            )
                            ir_tests = st.multiselect(
                                "Tests performed", data_store.COMMON_TESTS, key="val_tests",
                            )
                elif ir_type == "FND":
                    c_a, c_b = st.columns(2)
                    with c_a:
                        ir_severity = st.selectbox(
                            "Severity *", ["High", "Medium", "Low"], key="ir_sev",
                        )
                    with c_b:
                        ir_due = st.date_input(
                            "Remediation due",
                            value=date.today() + timedelta(days=90), key="ir_due",
                        )
                    ir_rem = st.text_area("Remediation required *", key="ir_rem")

                ir_submit = st.form_submit_button("Create request", key="ir_submit")
            if ir_submit:
                if not ir_title.strip() or not ir_desc.strip():
                    st.error("Title and description are required.")
                elif ir_type == "FND" and not (ir_rem or "").strip():
                    st.error("Remediation is required for a finding (FND).")
                elif ir_type == "VAL" and close_immediately and not ir_tests:
                    st.error("Record at least one test for a completed validation.")
                else:
                    role = auth.get_current_user()["role"]
                    payload = {
                        "type": ir_type,
                        "title": ir_title.strip(),
                        "description": ir_desc.strip(),
                        "assigned_to": ir_assigned,
                        "status": "Closed" if (ir_type == "VAL" and close_immediately) else "In Progress",
                        "materiality": ir_materiality,
                        "validation_subtype": ir_subtype,
                        "outcome": ir_outcome if close_immediately else None,
                        "closed_date": date.today().isoformat() if close_immediately else None,
                        "tests": ir_tests,
                        "severity": ir_severity,
                        "remediation": (ir_rem or "").strip() if ir_rem else None,
                        "due_date": ir_due.isoformat() if ir_due else None,
                        "source": (
                            "Validation" if ir_type in ("VAL", "FND") and role == "LOD2"
                            else "Internal Audit" if role == "LOD3"
                            else "Model Change" if ir_type == "MC"
                            else "LoD1 Request"
                        ),
                    }
                    if close_immediately and ir_desc.strip():
                        payload["thread"] = [{
                            "response_id": "TEMP-R1",
                            "date": date.today().isoformat(),
                            "author": auth.get_current_user()["name"],
                            "role": auth.get_current_user()["role"],
                            "text": ir_desc.strip(),
                            "evidence_ids": [],
                        }]
                    new_rid = data_store.create_request(selected, payload)
                    flash_and_rerun(f"Request {new_rid} created.")
    else:
        st.caption(
            f"No initiate actions for your role "
            f"({auth.ROLE_LABELS[auth.get_current_user()['role']]})."
        )

    # ------------------------------------------------ Filters + list + detail
    st.subheader("Requests for this model")
    type_chip_labels = {
        t: f"{t} — {auth.REQUEST_TYPES[t]['label']}" for t in auth.REQUEST_TYPE_ORDER
    }
    f1, f2 = st.columns(2)
    with f1:
        type_f_labels = st.multiselect(
            "Type",
            [type_chip_labels[t] for t in auth.REQUEST_TYPE_ORDER],
            default=[type_chip_labels[t] for t in auth.REQUEST_TYPE_ORDER],
            key="req_type_filter",
        )
        type_f = [
            t for t, lab in type_chip_labels.items() if lab in type_f_labels
        ]
    with f2:
        status_f = st.multiselect(
            "Status",
            data_store.REQUEST_STATUSES,
            default=data_store.REQUEST_STATUSES,
            key="req_status_filter",
        )

    filtered = [
        r for r in model_requests
        if r["type"] in type_f and r["status"] in status_f
    ]
    filtered = sorted(
        filtered,
        key=lambda r: (
            0 if r["status"] != "Closed" else 1,
            auth.REQUEST_TYPE_ORDER.index(r["type"]) if r["type"] in auth.REQUEST_TYPE_ORDER else 9,
            r["request_id"],
        ),
    )

    if not filtered:
        st.info("No requests match the current filters.")
    else:
        labels = {
            r["request_id"]: (
                f"{r['request_id']} · {r['status']} · {r['title'][:60]}"
            )
            for r in filtered
        }
        ids = [r["request_id"] for r in filtered]
        # Keep selection per model; drop stale ids after filters change.
        state_key = "md_selected_request"
        label_opts = [labels[i] for i in ids]
        if (
            state_key not in st.session_state
            or st.session_state[state_key] not in label_opts
        ):
            st.session_state[state_key] = label_opts[0]
        chosen_label = st.selectbox(
            "Select request ID",
            label_opts,
            key=state_key,
        )
        chosen = ids[label_opts.index(chosen_label)]
        req = next(r for r in filtered if r["request_id"] == chosen)
        is_closed = req["status"] == "Closed"
        status_color = {
            "Open": utils.AMBER, "In Progress": utils.NAVY, "Closed": utils.GREEN,
        }.get(req["status"], utils.GREY)

        st.markdown("---")
        st.markdown(
            utils.badge(req["request_id"], utils.GREY)
            + utils.badge(auth.REQUEST_TYPES[req["type"]]["label"], utils.NAVY)
            + utils.badge(req["status"], status_color)
            + (utils.severity_badge(req["severity"]) if req.get("severity") else "")
            + (utils.badge(req["outcome"], utils.GREEN) if req.get("outcome") else ""),
            unsafe_allow_html=True,
        )
        st.markdown(f"### {req['title']}")
        st.markdown(req.get("description") or "_No description._")
        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f"**Initiated by:** {req.get('initiated_by', '—')}")
        m2.markdown(f"**Assigned to:** {req.get('assigned_to', '—')}")
        m3.markdown(f"**Created:** {req.get('created_date', '—')}")
        m4.markdown(
            f"**Closed:** {req['closed_date']}" if req.get("closed_date")
            else f"**Due:** {req.get('due_date') or '—'}"
        )
        if req.get("remediation"):
            st.markdown(f"**Remediation.** {req['remediation']}")
        if req.get("materiality"):
            st.caption(f"Materiality: {req['materiality']}")
        if req.get("tests"):
            st.markdown("**Tests:** " + ", ".join(req["tests"]))
        if req.get("validation_subtype"):
            st.caption(f"Nature: {req['validation_subtype']}")

        if is_closed:
            st.warning("This request is **Closed** — read-only (no upload, edit, or new comments).")

        # ---- Evidence
        st.markdown("**Evidence**")
        req_ev = _evidence_for("validation_request", req["request_id"], evidence_all)
        # Also show legacy validation link if legacy_id present
        if req.get("legacy_id"):
            req_ev = req_ev + [
                e for e in _evidence_for("validation", req["legacy_id"], evidence_all)
                if e not in req_ev
            ]
        _render_evidence_rows(req_ev, f"req_{req['request_id']}")
        if not is_closed and auth.has_permission("upload_evidence"):
            _render_attach_form(
                selected, "validation_request", req["request_id"],
                f"attach_req_{req['request_id']}",
                caption="Attach supporting files to this open request.",
            )

        # ---- Thread
        st.markdown("**Thread**")
        thread = req.get("thread") or []
        if not thread:
            st.caption("No comments yet.")
        for resp in thread:
            rid = resp.get("response_id") or "?"
            st.markdown(
                f"<div style='border-left:3px solid {utils.GOLD}; padding:6px 12px; "
                f"margin:6px 0; background:#fafafa;'>"
                f"<b>{resp['author']}</b> {auth.role_badge_html(resp.get('role', ''))} "
                f"<span style='color:#888; font-size:0.8rem;'>{resp.get('date', '')}</span>"
                f" · <code>{rid}</code><br>{resp.get('text', '')}</div>",
                unsafe_allow_html=True,
            )
            resp_ev = []
            seen = set()
            for eid in resp.get("evidence_ids") or []:
                ev = evidence_by_id.get(eid)
                if ev and eid not in seen:
                    resp_ev.append(ev)
                    seen.add(eid)
            for ev in _evidence_for("request_response", rid, evidence_all):
                if ev["evidence_id"] not in seen:
                    resp_ev.append(ev)
                    seen.add(ev["evidence_id"])
            if resp_ev:
                _render_evidence_rows(resp_ev, f"thr_{rid}")

        if not is_closed:
            # Assign / send
            if auth.has_permission("assign_request"):
                with st.form(f"assign_form_{req['request_id']}", clear_on_submit=True):
                    all_opts = auth.user_option_labels("LOD1", "LOD2", "LOD3", "ADMIN")
                    a_idx = auth.default_option_index(all_opts, req.get("assigned_to"))
                    new_assignee = st.selectbox(
                        "Send / assign to", all_opts, index=a_idx,
                        key=f"assign_to_{req['request_id']}",
                    )
                    st.caption("Production would notify the assignee by email.")
                    assign_go = st.form_submit_button("Update assignment")
                if assign_go:
                    data_store.assign_request(req["request_id"], new_assignee)
                    flash_and_rerun(f"{req['request_id']} assigned to {new_assignee}.")

            # Respond (LoD1 on FND; LOD2/ADMIN may comment on MC/VAL via respond path)
            can_respond = auth.has_permission("respond_request") or (
                req["type"] != "FND" and auth.get_current_user()["role"] in ("LOD2", "ADMIN")
            )
            if can_respond and auth.has_permission("respond_request"):
                with st.form(f"resp_form_{req['request_id']}", clear_on_submit=True):
                    resp_text = st.text_area(
                        "Add response *", key=f"resp_txt_{req['request_id']}",
                    )
                    resp_file = st.file_uploader(
                        "Attach evidence (optional)",
                        type=data_store.ALLOWED_UPLOAD_TYPES,
                        key=f"resp_ev_{req['request_id']}",
                    )
                    resp_cat = st.selectbox(
                        "Evidence category", data_store.EVIDENCE_CATEGORIES,
                        key=f"resp_cat_{req['request_id']}",
                    )
                    resp_desc = st.text_input(
                        "Evidence description", key=f"resp_desc_{req['request_id']}",
                        placeholder="Short note if attaching a file",
                    )
                    resp_submit = st.form_submit_button("Add response")
                if resp_submit:
                    if not resp_text.strip():
                        st.error("Response text is required.")
                    elif resp_file is not None and not resp_desc.strip():
                        st.error("Provide a short evidence description when attaching a file.")
                    else:
                        rid = data_store.peek_next_thread_id(req["request_id"])
                        ev_ids = []
                        if resp_file is not None:
                            ev_ids.append(data_store.attach_evidence(
                                selected, "request_response", rid, resp_file,
                                resp_cat, resp_desc.strip() or f"Evidence on {rid}",
                            ))
                        data_store.add_request_response(
                            req["request_id"], resp_text.strip(), ev_ids,
                        )
                        flash_and_rerun(f"Response {rid} added to {req['request_id']}.")
            elif req["type"] == "FND" and not auth.has_permission("respond_request"):
                st.caption(
                    f"Findings are answered by the first line "
                    f"({auth.who_can('respond_request')})."
                )

            # Close
            if auth.can_close_request(req):
                with st.form(f"close_form_{req['request_id']}", clear_on_submit=True):
                    close_comment = st.text_input(
                        "Closure comment *", key=f"close_txt_{req['request_id']}",
                    )
                    close_outcome = None
                    close_tests: list[str] = []
                    if req["type"] in ("VAL", "MC"):
                        close_outcome = st.selectbox(
                            "Outcome *", data_store.VALIDATION_OUTCOMES,
                            key=f"close_out_{req['request_id']}",
                        )
                        if req["type"] == "VAL" or req.get("materiality") == "Material":
                            close_tests = st.multiselect(
                                "Tests performed (optional)", data_store.COMMON_TESTS,
                                key=f"close_tests_{req['request_id']}",
                            )
                    close_file = st.file_uploader(
                        "Closure evidence (optional)",
                        type=data_store.ALLOWED_UPLOAD_TYPES,
                        key=f"close_ev_{req['request_id']}",
                    )
                    close_cat = st.selectbox(
                        "Evidence category", data_store.EVIDENCE_CATEGORIES,
                        key=f"close_cat_{req['request_id']}",
                    )
                    close_desc = st.text_input(
                        "Evidence description", key=f"close_desc_{req['request_id']}",
                        placeholder="Short note if attaching a file",
                    )
                    close_submit = st.form_submit_button("Close request", type="primary")
                if close_submit:
                    if not close_comment.strip():
                        st.error("A closure comment is required.")
                    elif req["type"] in ("VAL", "MC") and not close_outcome:
                        st.error("Outcome is required to close this request.")
                    elif close_file is not None and not close_desc.strip():
                        st.error("Provide a short evidence description when attaching a file.")
                    else:
                        rid = data_store.peek_next_thread_id(req["request_id"])
                        ev_ids = []
                        if close_file is not None:
                            ev_ids.append(data_store.attach_evidence(
                                selected, "request_response", rid, close_file,
                                close_cat,
                                close_desc.strip() or f"Closure evidence on {req['request_id']}",
                            ))
                        data_store.close_request(
                            req["request_id"],
                            close_comment.strip(),
                            outcome=close_outcome,
                            evidence_ids=ev_ids,
                            tests=close_tests or None,
                        )
                        flash_and_rerun(f"Request {req['request_id']} closed.")
            else:
                st.caption("You cannot close this request under the current role rules.")

    # Compact counts by type
    with st.expander("Counts by type", expanded=False):
        counts = []
        for t in auth.REQUEST_TYPE_ORDER:
            n = sum(1 for r in model_requests if r["type"] == t)
            n_open = sum(1 for r in model_requests if r["type"] == t and r["status"] != "Closed")
            counts.append({
                "Type": t,
                "Label": auth.REQUEST_TYPES[t]["label"],
                "Total": n,
                "Open": n_open,
            })
        st.dataframe(pd.DataFrame(counts), hide_index=True, width="stretch")

# ================================================================ Monitoring
with tab_perf:
    if model_monitoring.empty:
        st.info("No quantitative performance monitoring is configured for this model "
                "(e.g. models in development, in validation, or qualitative/expert-judgement models).")
    else:
        latest = model_monitoring[model_monitoring["period"] == model_monitoring["period"].max()]
        st.subheader("Latest Position")
        cols = st.columns(max(len(latest), 2))
        for col, (_, row) in zip(cols, latest.iterrows()):
            rag_color = {"Green": utils.GREEN, "Amber": utils.AMBER, "Red": utils.RED}.get(
                row["rag"], utils.GREY
            )
            col.markdown(
                f"**{row['metric']}**<br>"
                f"<span style='font-size:1.6rem; font-weight:700;'>{row['value']}</span> "
                f"{utils.badge(row['rag'], rag_color)}",
                unsafe_allow_html=True,
            )

        st.subheader("Trend vs Thresholds")
        for metric, series in model_monitoring.groupby("metric"):
            series = series.sort_values("period")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=series["period"], y=series["value"], mode="lines+markers",
                name=metric, line=dict(color=utils.NAVY, width=3),
            ))
            fig.add_hline(y=series["amber_threshold"].iloc[0], line_dash="dash",
                          line_color=utils.AMBER, annotation_text="Amber threshold")
            fig.add_hline(y=series["red_threshold"].iloc[0], line_dash="dash",
                          line_color=utils.RED, annotation_text="Red threshold")
            fig.update_layout(title=metric, height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")

# ================================================================ Docs & Audit
with tab_docs:
    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.subheader("Documentation Checklist")
        docs = m["documentation"]
        complete = sum(docs.values())
        st.progress(complete / len(docs), text=f"{complete} of {len(docs)} artefacts in place")
        for doc, ok in docs.items():
            icon = "✅" if ok else "❌"
            st.markdown(f"{icon} {doc}")
        if complete < len(docs):
            st.warning("Documentation gaps must be closed to meet the standard for this model's tier.")

    with c2:
        st.subheader("Change Log (summary)")
        cl = pd.DataFrame(m["change_log"])
        if not cl.empty:
            show_cols = [c for c in [
                "change_id", "date", "version", "classification", "description", "author",
            ] if c in cl.columns]
            st.dataframe(
                cl[show_cols].rename(columns={
                    "change_id": "ID", "date": "Date", "version": "Version",
                    "description": "Change", "author": "Author",
                    "classification": "Classification",
                }),
                hide_index=True, width="stretch",
            )
            st.caption("Attach evidence on change entries under **Governance & Lifecycle**.")
        else:
            st.caption("No change-log entries.")

        st.subheader("Internal Audit Reviews")
        if m["audit_reviews"]:
            for review in sorted(m["audit_reviews"], key=lambda r: r["date"], reverse=True):
                aid = review.get("audit_id", f"AUD-{review['date']}")
                with st.expander(
                    f"{review['date']} — {review['rating']} — {review['auditor']}",
                    expanded=False,
                ):
                    st.markdown(f"**Scope.** {review['scope']}")
                    st.markdown("**Attached evidence**")
                    _render_evidence_rows(
                        _evidence_for("audit", aid, evidence_all), f"aud_{aid}",
                    )
                    if auth.has_permission("upload_evidence"):
                        _render_attach_form(
                            selected, "audit", aid, f"attach_aud_{aid}",
                            caption="Attach audit memo or workpapers.",
                        )
        else:
            st.caption("No internal audit reviews recorded for this model.")

        # -------------------------------------------- Record Audit Review (LoD 3)
        if auth.has_permission("record_audit"):
            with st.expander("Record Internal Audit Review", expanded=False):
                with st.form("audit_form", clear_on_submit=True):
                    au1, au2 = st.columns(2)
                    with au1:
                        aud_date = st.date_input("Review date", value=date.today(), key="aud_date")
                    with au2:
                        aud_rating = st.selectbox(
                            "Rating *", ["Satisfactory", "Needs Improvement", "Unsatisfactory"]
                        )
                    aud_options = auth.user_option_labels("LOD3", "ADMIN") or [
                        auth.user_option_label(auth.get_current_user())
                    ]
                    aud_idx = auth.default_option_index(
                        aud_options, auth.get_current_user()["name"]
                    )
                    aud_auditor = st.selectbox(
                        "Auditor *", aud_options, index=aud_idx, key="aud_auditor",
                    )
                    aud_scope = st.text_area("Scope of review *", key="aud_scope")
                    aud_file = st.file_uploader(
                        "Evidence (optional) — audit memo / workpapers",
                        type=data_store.ALLOWED_UPLOAD_TYPES, key="aud_evidence",
                    )
                    aud_ev_cat = st.selectbox(
                        "Evidence category", data_store.EVIDENCE_CATEGORIES, key="aud_ev_cat",
                    )
                    aud_ev_desc = st.text_input(
                        "Evidence description", key="aud_ev_desc",
                        placeholder="Short note if attaching a file",
                    )
                    aud_submit = st.form_submit_button("Record audit review", key="aud_submit")
                if aud_submit:
                    if not aud_auditor.strip() or not aud_scope.strip():
                        st.error("Auditor and scope are required.")
                    elif aud_file is not None and not aud_ev_desc.strip():
                        st.error("Provide a short evidence description when attaching a file.")
                    else:
                        aid = data_store.add_audit_review(selected, {
                            "date": aud_date.isoformat(),
                            "auditor": aud_auditor.strip(),
                            "rating": aud_rating,
                            "scope": aud_scope.strip(),
                        })
                        if aud_file is not None:
                            data_store.attach_evidence(
                                selected, "audit", aid, aud_file,
                                aud_ev_cat, aud_ev_desc.strip(),
                            )
                        flash_and_rerun(f"Internal audit review {aid} recorded ({aud_rating}).")
        else:
            auth.permission_denied("record_audit")

    # Read-only inventory of all files for this model (no dedicated Evidence tab)
    with st.expander("Attached files (this model)", expanded=False):
        st.caption(
            "Read-only inventory. Attach new files on open Validation & Findings "
            "requests, or on Governance / Audit workflows where they belong."
        )
        if model_evidence:
            inv = pd.DataFrame([
                {
                    "ID": e["evidence_id"],
                    "File": e["filename"],
                    "Linked to": f"{e['linked_type']}: {e['linked_id']}",
                    "Category": e["category"],
                    "Uploaded": e["uploaded_at"][:10],
                    "By": e["uploaded_by"],
                }
                for e in sorted(model_evidence, key=lambda x: x["uploaded_at"], reverse=True)
            ])
            st.dataframe(inv, hide_index=True, width="stretch")
        else:
            st.caption("No evidence registered for this model yet.")

    st.subheader("Audit Trail")
    st.caption("Workflow actions on this model, most recent first.")
    trail = [e for e in load_audit_log() if e["model_id"] == selected]
    if trail:
        tr = pd.DataFrame(sorted(trail, key=lambda e: e["timestamp"], reverse=True))
        tr = tr.rename(columns={
            "timestamp": "Timestamp", "user": "User", "role": "Role", "action": "Action",
            "entity_type": "Entity Type", "entity_id": "Entity", "details": "Details",
        })[["Timestamp", "User", "Role", "Action", "Entity Type", "Entity", "Details"]]
        st.dataframe(tr, hide_index=True, width="stretch")
    else:
        st.caption("No audit trail events recorded for this model yet.")
