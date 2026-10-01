from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import streamlit as st
import auth
import data_loader
import data_store
import governance
import repository
import tiering
import utils
from data_loader import (
    documentation_status,
    factsheet_pdf,
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

INTEGRITY_LABEL = {
    "ok": "hash verified",
    "altered": "FILE ALTERED since upload",
    "missing": "file missing from evidence folder",
}


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
        data, state = data_store.read_evidence(ev)
        with c2:
            color = utils.GREEN if state == "ok" else utils.RED
            st.markdown(
                utils.badge(ev["category"], utils.GOLD)
                + f"<span style='font-size:0.8rem; color:#888;'> "
                f"{ev['uploaded_by']} · {utils.fmt_date(ev['uploaded_at'])}</span><br>"
                f"<span style='font-size:0.75rem; color:{color};'>"
                f"{INTEGRITY_LABEL[state]}</span>",
                unsafe_allow_html=True,
            )
        with c3:
            if data is not None:
                st.download_button(
                    "Download",
                    data=data,
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
            try:
                eid = data_store.attach_evidence(
                    model_id, linked_type, linked_id, up, cat, desc.strip(),
                )
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            else:
                flash_and_rerun(f"Evidence {eid} attached to {linked_type} {linked_id}.")


def _tier_signoff(m: dict) -> None:
    """Gate G1: propose -> confirm (MRM) -> CRO approval for overrides."""
    ta = m.get("tier_assessment") or {}
    user = auth.get_current_user()
    status = ta.get("status", governance.TIER_CONFIRMED)
    proposed_tier = tiering.compute_tier(**ta["scores"])["tier"] if ta.get("scores") else m["tier"]

    if status == governance.TIER_CONFIRMED:
        note = f"Tier {m['tier']} confirmed"
        if ta.get("confirmed_by"):
            note += f" by {ta['confirmed_by']} on {utils.fmt_date(ta.get('confirmed_on'))}"
        if m.get("tier_override"):
            note += f" — override of the rule-based Tier {m['computed_tier']}, approved by the CRO"
        st.success(note + ".")
    elif status == governance.TIER_PROPOSED:
        st.warning(
            f"**Tier {proposed_tier} proposed** by {ta['proposed_by']} on "
            f"{utils.fmt_date(ta['proposed_on'])} — awaiting confirmation by the MRM function. "
            f"Scores: materiality {ta['scores']['materiality']}, complexity "
            f"{ta['scores']['complexity']}, regulatory impact {ta['scores']['regulatory_impact']}. "
            f"Rationale: {ta.get('rationale') or '—'}"
        )
    else:
        st.warning(
            f"**Override to Tier {ta['override_tier']} awaiting CRO approval** (rule-based Tier "
            f"{proposed_tier}). Requested by {ta['confirmed_by']}: {ta['override_reason']}"
        )

    # ---- actions
    if status == governance.TIER_PROPOSED and auth.has_permission("confirm_tier"):
        if ta.get("proposed_by") == user["name"]:
            st.caption("You proposed this tier, so someone else must confirm it.")
        else:
            with st.form(f"confirm_tier_{m['model_id']}"):
                st.markdown("**Confirm the tier**")
                ov = st.selectbox(
                    "Final tier", [proposed_tier] + [t for t in (1, 2, 3) if t != proposed_tier],
                    format_func=lambda t: f"Tier {t}" + (" (rule-based)" if t == proposed_tier else " — override"),
                    key=f"ct_tier_{m['model_id']}",
                )
                reason = st.text_input("Override reason (required for an override)",
                                       key=f"ct_reason_{m['model_id']}")
                go_confirm = st.form_submit_button("Confirm tier", type="primary")
            if go_confirm:
                try:
                    res = data_store.confirm_tier(
                        m["model_id"], override_tier=ov if ov != proposed_tier else None,
                        override_reason=reason,
                    )
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    flash_and_rerun("Tier confirmed." if res == governance.TIER_CONFIRMED
                                    else "Override sent to the CRO for approval.")
    elif status == governance.TIER_OVERRIDE_PENDING and auth.has_permission("approve_tier_override"):
        with st.form(f"cro_tier_{m['model_id']}"):
            st.markdown("**CRO decision on the tier override**")
            comment = st.text_input("Comment", key=f"cro_c_{m['model_id']}")
            c_a, c_b = st.columns(2)
            approve = c_a.form_submit_button("Approve override", type="primary")
            reject = c_b.form_submit_button("Reject — keep rule-based tier")
        if approve or reject:
            try:
                data_store.decide_tier_override(m["model_id"], bool(approve), comment)
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            else:
                flash_and_rerun("Tier override approved." if approve else "Tier override rejected.")
    elif status == governance.TIER_CONFIRMED and auth.has_permission("propose_tier") and (
        user["role"] == "ADMIN" or governance.is_owner_or_developer(m, user["name"])
    ):
        with st.popover("Propose a tier reassessment"):
            with st.form(f"propose_tier_{m['model_id']}"):
                cur = m["tier_scores"]
                p1, p2, p3 = st.columns(3)
                pm = p1.selectbox("Materiality", tiering.LEVELS,
                                  index=tiering.LEVELS.index(cur["materiality"]), key=f"pt_m_{m['model_id']}")
                pc = p2.selectbox("Complexity", tiering.LEVELS,
                                  index=tiering.LEVELS.index(cur["complexity"]), key=f"pt_c_{m['model_id']}")
                pr = p3.selectbox("Regulatory impact", tiering.LEVELS,
                                  index=tiering.LEVELS.index(cur["regulatory_impact"]), key=f"pt_r_{m['model_id']}")
                prat = st.text_area("Rationale *", key=f"pt_rat_{m['model_id']}")
                go_prop = st.form_submit_button("Submit for sign-off")
            if go_prop:
                try:
                    data_store.propose_tier(m["model_id"], {
                        "materiality": pm, "complexity": pc, "regulatory_impact": pr,
                    }, prat)
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    flash_and_rerun("Tier reassessment submitted for sign-off.")

    if m.get("tier_history"):
        st.markdown("**Tier history**")
        st.dataframe(pd.DataFrame([{
            "Tier": h.get("tier"),
            "Materiality": h["scores"]["materiality"], "Complexity": h["scores"]["complexity"],
            "Regulatory impact": h["scores"]["regulatory_impact"],
            "Override": h.get("override") or "—", "Rationale": h.get("rationale"),
            "Confirmed by": h.get("confirmed_by"), "Confirmed on": utils.fmt_date(h.get("confirmed_on")),
        } for h in reversed(m["tier_history"])]), hide_index=True, width="stretch")


GATE_ICON = {"done": "✅", "current": "🟡", "pending": "⚪"}


def _act(fn, msg, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
    else:
        flash_and_rerun(msg)


def _lifecycle_panel(m: dict, model_requests: list[dict]) -> None:
    """Gates G1–G5, the action due at the current gate, approvals and conditions."""
    user = auth.get_current_user()
    st.subheader("Lifecycle gates")
    states = governance.gate_states(m)
    cols = st.columns(5)
    for col, g in zip(cols, states):
        col.markdown(
            f"<div style='border:1px solid #e0e0e0; border-radius:8px; padding:8px 10px; "
            f"background:{'#fff8e1' if g['state'] == 'current' else '#fff'};'>"
            f"<div style='font-size:0.78rem; color:#666;'>{g['gate']}</div>"
            f"<div style='font-weight:600;'>{GATE_ICON[g['state']]} {g['name']}</div></div>",
            unsafe_allow_html=True,
        )
    cur = governance.current_gate(m)
    st.markdown("")
    if cur is None:
        st.caption(f"All gates passed — status **{m['status']}**.")
    elif cur == "G1":
        st.info("G1: the tier must be confirmed — see *Tier and sign-off* on the Overview tab.")
    elif cur == "G2":
        missing = data_loader.g2_missing_docs(m)
        st.info(
            "G2: the owner submits the model for validation once the required documents are "
            f"in place ({', '.join(governance.G2_REQUIRED_DOCS[m['tier']])})."
            + (f" **Missing:** {', '.join(missing)} — upload them on the Documentation & Audit tab."
               if missing else "")
        )
        if auth.has_permission("submit_for_validation") and (
                user["role"] == "ADMIN" or governance.is_owner_or_developer(m, user["name"])):
            with st.form(f"g2_{m['model_id']}"):
                note = st.text_area("Note to the validator (optional)")
                go = st.form_submit_button("Submit for validation (G2)", type="primary",
                                           disabled=bool(missing))
            if go:
                _act(data_store.submit_for_validation, "Submitted for validation — a VAL request is open.",
                     m["model_id"], note)
    elif cur == "G3":
        open_v = [r for r in model_requests if r.get("engagement") and r["status"] != "Closed"]
        st.info(
            "G3: validation in progress — "
            + (", ".join(f"{r['request_id']} ({r['engagement']['stage']})" for r in open_v)
               if open_v else "no open validation; ask the validator to open one")
            + ". Work happens on the Validation & Findings tab."
        )
    elif cur == "G4":
        tier = m["tier"]
        st.warning(
            f"G4: awaiting approval by the **{m['approval_body']}** — validation rated "
            f"**{m.get('last_rating')}** on {utils.fmt_date(m.get('last_validation'))}."
        )
        can = auth.has_permission("record_approval") and (
            user["role"] == "CRO" or (user["role"] == "ADMIN" and tier == 1))
        if can:
            with st.form(f"g4_{m['model_id']}"):
                st.markdown("**Record the approval decision**" + (
                    " — Management Risk Committee (record as secretary)" if tier == 1 else " — CRO"))
                decision = st.selectbox("Decision", governance.APPROVAL_DECISIONS)
                minute = st.text_input("Committee minute reference" + (" *" if tier == 1 else ""),
                                       placeholder="e.g. MgmtRC 2026-10 item 4")
                cond_df = st.data_editor(
                    pd.DataFrame([{"condition": "", "due": None}]), num_rows="dynamic",
                    width="stretch", key=f"g4_conds_{m['model_id']}",
                    column_config={"condition": "Condition (for 'Approved with conditions')",
                                   "due": st.column_config.DateColumn("Due")},
                )
                comment = st.text_area("Comment")
                go = st.form_submit_button("Record decision (G4)", type="primary")
            if go:
                conds = [{"condition": r["condition"], "due": r["due"].isoformat() if pd.notna(r["due"]) and r["due"] else None}
                         for r in cond_df.to_dict("records") if str(r.get("condition") or "").strip()]
                _act(data_store.record_approval, f"Decision recorded: {decision}.",
                     m["model_id"], decision, conds, minute, comment)
        elif user["role"] == "ADMIN":
            st.caption("Tier 2 and 3 models are approved by the CRO.")
    elif cur == "G5":
        st.warning(
            "G5: approved — a validator must verify that the deployed version is the validated "
            "and approved one before the model is used."
        )
        if auth.has_permission("verify_implementation") and not governance.independence_conflict(
                m, user["name"], "VAL"):
            with st.form(f"g5_{m['model_id']}"):
                note = st.text_area("What was checked *",
                                    placeholder="Version, configuration, parallel run or reconciliation")
                go = st.form_submit_button("Verify implementation (G5)", type="primary")
            if go:
                _act(data_store.verify_implementation, "Implementation verified — model in use.",
                     m["model_id"], note)

    # ---- approvals and conditions
    approvals = m.get("approvals") or []
    st.subheader("Approvals and conditions")
    if not approvals:
        st.caption("No approval decisions recorded yet.")
    for ap in reversed(approvals):
        color = {"Approved": utils.GREEN, "Approved with conditions": utils.AMBER}.get(ap["decision"], utils.RED)
        st.markdown(
            f"{utils.badge(ap['approval_id'], utils.GREY)}{utils.badge(ap['decision'], color)} "
            f"**{ap['body']}** · {utils.fmt_date(ap['date'])} · v{ap.get('version')} · recorded by "
            f"{ap['recorded_by']}" + (f" · {ap['minute_ref']}" if ap.get("minute_ref") else ""),
            unsafe_allow_html=True,
        )
        if ap.get("comment"):
            st.caption(ap["comment"])
        for c in ap.get("conditions", []):
            cc1, cc2 = st.columns([4, 2])
            cc1.markdown(
                f"- **{c['cond_id']}** {c['condition']} — owner {c['owner']}"
                + (f", due {utils.fmt_date(c['due'])}" if c.get("due") else "")
                + f" · *{c['status']}*" + (f" — {c['note']}" if c.get("note") else "")
            )
            key = f"{ap['approval_id']}_{c['cond_id']}"
            with cc2:
                if c["status"] == governance.CONDITION_OPEN and user["role"] == "LOD1" and (
                        governance.is_owner_or_developer(m, user["name"])
                        or governance.person_name(c.get("owner")) == user["name"]):
                    with st.popover("Mark as met"):
                        note = st.text_input("How was it met?", key=f"cm_{key}")
                        if st.button("Confirm", key=f"cmb_{key}"):
                            _act(data_store.update_condition, "Condition marked as met.",
                                 m["model_id"], ap["approval_id"], c["cond_id"], "met", note)
                if c["status"] == governance.CONDITION_MET and user["role"] in ("LOD2", "CRO") \
                        and not governance.is_owner_or_developer(m, user["name"]):
                    b1, b2 = st.columns(2)
                    if b1.button("Verify", key=f"cv_{key}"):
                        _act(data_store.update_condition, "Condition verified.",
                             m["model_id"], ap["approval_id"], c["cond_id"], "verify")
                    with b2.popover("Reopen"):
                        why = st.text_input("Why?", key=f"cr_{key}")
                        if st.button("Reopen", key=f"crb_{key}"):
                            _act(data_store.update_condition, "Condition reopened.",
                                 m["model_id"], ap["approval_id"], c["cond_id"], "reopen", why)
    if m.get("implementation"):
        st.caption("Implementation verified: " + "; ".join(
            f"v{i['version']} by {i['verified_by']} on {utils.fmt_date(i['verified_on'])}"
            for i in m["implementation"]))


STAGE_ORDER = governance.ENGAGEMENT_STAGES


def _engagement_panel(req: dict, m: dict) -> None:
    """Validation engagement: scope and independence, information requests,
    draft report, owner's factual-accuracy review, sign-off (G3)."""
    eng = req.get("engagement") or {}
    user = auth.get_current_user()
    rid = req["request_id"]
    stage = eng.get("stage", "Scoping")
    is_closed = req["status"] == "Closed"
    is_validator = user["role"] == "LOD2" and governance.person_name(req.get("assigned_to")) == user["name"]
    is_owner = governance.is_owner_or_developer(m, user["name"])

    st.markdown("**Validation engagement**")
    idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 0
    st.markdown(" → ".join(
        f"**{s}**" if i == idx else (f"<span style='color:{utils.GREEN};'>{s}</span>" if i < idx
                                     else f"<span style='color:#999;'>{s}</span>")
        for i, s in enumerate(STAGE_ORDER)), unsafe_allow_html=True)

    if eng.get("scope"):
        st.markdown(f"**Scope.** {eng['scope']}")
    if eng.get("planned_tests"):
        st.caption("Planned tests: " + ", ".join(eng["planned_tests"]))
    if eng.get("independence"):
        st.caption(f"Independence declared by {eng['independence']['declared_by']} on "
                   f"{utils.fmt_date(eng['independence']['on'])}.")

    # ---- scoping
    if not is_closed and stage in ("Scoping",) and user["role"] == "LOD2" and (
            is_validator or not req.get("assigned_to")):
        with st.form(f"eng_scope_{rid}"):
            scope = st.text_area("Scope of the validation *")
            tests = st.multiselect("Planned tests", data_store.COMMON_TESTS)
            st.checkbox("I declare I did not develop, own or use this model and have no conflict of "
                        "interest in validating it.", key=f"eng_ind_{rid}")
            go = st.form_submit_button("Start fieldwork", type="primary")
        if go:
            if not st.session_state.get(f"eng_ind_{rid}"):
                st.error("Tick the independence declaration.")
            else:
                _act(data_store.start_engagement, "Fieldwork started.", rid, scope, tests)
    elif not is_closed and stage == "Scoping":
        st.caption("Waiting for the validator to set the scope and declare independence.")

    # ---- information requests
    irs = eng.get("info_requests") or []
    if irs or stage == "Fieldwork":
        st.markdown("**Information requests**")
    for ir in irs:
        color = {"Open": utils.AMBER, "Answered": utils.NAVY, "Accepted": utils.GREEN}[ir["status"]]
        overdue = ir["status"] == "Open" and ir.get("due") and ir["due"] < date.today().isoformat()
        st.markdown(
            f"{utils.badge(ir['ir_id'], utils.GREY)}{utils.badge(ir['status'], color)}"
            + (utils.badge('Overdue', utils.RED) if overdue else "")
            + f" **{ir['item']}** — {ir['owner']}, due {utils.fmt_date(ir.get('due'))}",
            unsafe_allow_html=True,
        )
        if ir.get("response"):
            st.caption(f"Answer ({ir.get('answered_by')}, {utils.fmt_date(ir.get('answered_on'))}): {ir['response']}")
        if ir.get("review_comment"):
            st.caption(f"Validator: {ir['review_comment']}")
        key = f"{rid}_{ir['ir_id']}"
        if not is_closed and ir["status"] == "Open" and user["role"] == "LOD1" and (
                is_owner or governance.person_name(ir["owner"]) == user["name"]):
            with st.popover(f"Answer {ir['ir_id']}"):
                resp = st.text_area("Answer", key=f"ira_{key}")
                f = st.file_uploader("Attach a file (optional)", type=data_store.ALLOWED_UPLOAD_TYPES,
                                     key=f"iraf_{key}")
                if st.button("Send answer", key=f"irab_{key}"):
                    try:
                        ev = []
                        if f is not None:
                            ev.append(data_store.attach_evidence(
                                m["model_id"], "validation_request", rid, f, "Document",
                                f"{ir['ir_id']}: {ir['item'][:60]}"))
                        data_store.answer_info_request(rid, ir["ir_id"], resp, ev)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        flash_and_rerun(f"{ir['ir_id']} answered.")
        if not is_closed and ir["status"] == "Answered" and is_validator:
            b1, b2 = st.columns([1, 3])
            if b1.button(f"Accept {ir['ir_id']}", key=f"irok_{key}"):
                _act(data_store.review_info_request, f"{ir['ir_id']} accepted.", rid, ir["ir_id"], True)
            with b2.popover(f"Send {ir['ir_id']} back"):
                why = st.text_input("What is still missing?", key=f"irno_{key}")
                if st.button("Send back", key=f"irnob_{key}"):
                    _act(data_store.review_info_request, f"{ir['ir_id']} sent back.", rid, ir["ir_id"], False, why)

    if not is_closed and stage == "Fieldwork" and is_validator:
        with st.popover("Add an information request"):
            item = st.text_input("Item requested", key=f"irnew_{rid}")
            owners = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
            who = st.selectbox("Asked of", owners,
                               index=auth.default_option_index(owners, m.get("developer")), key=f"irwho_{rid}")
            due = st.date_input("Due", value=date.today() + timedelta(days=10), key=f"irdue_{rid}")
            if st.button("Send request", key=f"irnewb_{rid}"):
                _act(data_store.add_info_request, "Information request sent.", rid, item, who, due.isoformat())
        reason = governance.engagement_can_issue_draft(eng)
        with st.form(f"eng_draft_{rid}"):
            st.markdown("**Draft report**")
            if reason:
                st.caption(reason)
            rating = st.selectbox("Proposed rating", governance.RATING_SCALE)
            summary = st.text_area("Summary of conclusions and findings")
            go = st.form_submit_button("Issue draft for owner review", disabled=bool(reason))
        if go:
            _act(data_store.issue_draft, "Draft issued for the owner's review.", rid, rating, summary)

    # ---- draft and owner review
    if eng.get("draft"):
        d = eng["draft"]
        st.markdown(f"**Draft report** — proposed rating {utils.rating_badge(d['rating'])} "
                    f"issued by {d['issued_by']} on {utils.fmt_date(d['issued_on'])}",
                    unsafe_allow_html=True)
        st.caption(d["summary"])
    if eng.get("owner_review"):
        o = eng["owner_review"]
        st.caption(f"Owner's factual-accuracy review ({o['by']}, {utils.fmt_date(o['on'])}): {o['comments']}")
    if not is_closed and stage == "Owner review" and is_owner and user["role"] == "LOD1":
        with st.form(f"eng_review_{rid}"):
            comments = st.text_area("Factual-accuracy comments (leave blank if none)")
            go = st.form_submit_button("Submit review", type="primary")
        if go:
            _act(data_store.submit_owner_review, "Review submitted.", rid, comments)

    # ---- sign-off
    if not is_closed and stage in ("Owner review", "Final sign-off") and is_validator:
        reason = governance.engagement_can_sign_off(eng)
        with st.form(f"eng_sign_{rid}"):
            st.markdown("**Final sign-off (G3)**")
            if reason:
                st.caption(reason)
            rating = st.selectbox("Final rating", governance.RATING_SCALE,
                                  index=governance.RATING_SCALE.index(eng["draft"]["rating"])
                                  if eng.get("draft") else 0,
                                  help=" · ".join(f"{k}: {v}" for k, v in governance.RATING_DESCRIPTIONS.items()))
            comment = st.text_input("Sign-off comment")
            go = st.form_submit_button("Sign off validation", type="primary", disabled=bool(reason))
        if go:
            _act(data_store.sign_off, "Validation signed off.", rid, rating, comment)
    if eng.get("signed_off"):
        so = eng["signed_off"]
        st.success(f"Signed off by {so['by']} on {utils.fmt_date(so['on'])} — rating {so['rating']}.")


# Fresh-session identity: a new tab has no sidebar selector until page_setup
# runs (or never, if this view is executed standalone).
auth.get_current_user()

models = load_models()
model_ids = [m["model_id"] for m in models]
labels = {m["model_id"]: f"{m['model_id']} — {m['name']}" for m in models}

if not model_ids:
    st.error("No models in the inventory.")
    st.stop()

# Deep link support: /model_detail?model=<id>[&request=<rid>]
# (inventory LinkColumn / Findings Tracker). Consume params so the selectbox
# takes over on later interactions — do not clear the whole query string
# (that can break st.navigation page routing in a new tab).
qp_model = utils.read_model_query_param()
qp_request = utils.read_request_query_param()
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

# Keep request selection scoped to the current model (list ↔ detail).
# Only clear when the model *changes*; first paint with a preset selection
# (e.g. deep-link / smoke test) must keep md_selected_request.
_prev_req_model = st.session_state.get("_md_req_model")
if _prev_req_model is None:
    st.session_state["_md_req_model"] = selected
elif _prev_req_model != selected:
    st.session_state["_md_req_model"] = selected
    st.session_state.pop("md_selected_request", None)

# Apply ?request= after model-scope handling so a deep link is not wiped
# when landing from Findings Tracker / inventory.
if qp_request:
    st.session_state["md_selected_request"] = qp_request
    utils.drop_request_query_param()

m = get_model(selected)
if m is None:
    st.error(f"Model **{selected}** was not found in the inventory.")
    st.stop()

vstatus = validation_status(m)
tier_info = tiering.compute_tier(**m["tier_scores"])

if "_flash" in st.session_state:
    st.success(st.session_state.pop("_flash"))

utils.header(f"{m['model_id']} — {m['name']}", m["business_line"])
hb1, hb2 = st.columns([5, 1.2])
hb2.download_button(
    "Factsheet (PDF)", data=factsheet_pdf(selected),
    file_name=f"{selected}_factsheet_{date.today().isoformat()}.pdf",
    mime="application/pdf", key="dl_factsheet", width="stretch",
)
hb1.markdown(
    utils.tier_badge(m["tier"])
    + ("" if m["tier_confirmed"] else utils.badge(
        "Tier reassessment pending" if m.get("tier_history") else "Tier not yet confirmed", utils.AMBER))
    + utils.status_badge(m["status"])
    + utils.validation_badge(f"Validation: {vstatus}")
    + (utils.rating_badge(m["last_rating"]) if m.get("last_rating") else "")
    + utils.badge(m["risk_type"], utils.RISK_TYPE_COLORS.get(m["risk_type"], utils.GREY))
    + utils.badge(m["source"] + (f" · {m['vendor']}" if m.get("vendor") else ""), utils.NAVY)
    + (utils.badge("AI system (QCB AI Guideline)", "#6a1b9a") if m.get("ai_system") else ""),
    unsafe_allow_html=True,
)
if m.get("placeholder"):
    st.caption("Placeholder record — details are illustrative and to be confirmed by the model owner.")
st.markdown("")

validations = load_validations()
model_validations = validations[validations["model_id"] == selected]
model_requests = requests_for_model(selected)
monitoring = load_monitoring()
model_monitoring = monitoring[monitoring["model_id"] == selected]

evidence_all = load_evidence()
model_evidence = [e for e in evidence_all if e["model_id"] == selected]
evidence_by_id = {e["evidence_id"]: e for e in evidence_all}

tab_overview, tab_gov, tab_val, tab_perf, tab_docs, tab_edit = st.tabs([
    "Overview",
    "Governance & Lifecycle",
    "Validation & Findings",
    "Performance Monitoring",
    "Documentation & Audit",
    "Edit Record",
])

# ================================================================ Overview
with tab_overview:
    st.markdown(f"**Purpose.** {m['description']}")

    scores = m["tier_scores"]
    utils.kpi_cards([
        ("Tier", f"Tier {m['tier']}",
         f"override of rule-based Tier {m['computed_tier']}" if m.get("tier_override")
         else f"score {tier_info['composite']} / 9"
         + ("" if m["tier_confirmed"] else
            " · reassessment pending" if m.get("tier_history") else " · not yet confirmed")),
        ("Materiality", scores["materiality"], None),
        ("Complexity", scores["complexity"], None),
        ("Regulatory impact", scores["regulatory_impact"], None),
        ("Last validation", utils.fmt_date(m["last_validation"], "Never"), m.get("last_rating")),
        ("Next validation due", utils.fmt_date(m["next_validation_due"]), m["validation_frequency"]),
    ])

    d1, d2, d3 = st.columns(3)
    d1.caption(
        f"Approved **{utils.fmt_date(m['approval_date'], 'not approved')}** · "
        f"approval body: {m['approval_body']}"
    )
    d2.caption(f"Exposure **QAR {m['exposure_covered_qar_mn']:,} mn**")
    d3.caption(f"Platform **{m['implementation_platform']}** · {m['usage_frequency']}")

    st.markdown("**Uses**")
    if m.get("uses"):
        st.dataframe(
            pd.DataFrame(m["uses"]).rename(columns={
                "use": "Use", "business_area": "Business area",
                "decision": "Decision supported", "status": "Status",
            }),
            hide_index=True, width="stretch",
        )
    else:
        st.caption("No uses recorded yet — add them on the Edit Record tab.")

    with st.expander("Identification & use"):
        ident = pd.DataFrame(
            {
                "Field": ["Model ID", "Version", "Risk Type", "Category", "Business Line",
                          "Methodology", "Source", "Vendor", "Implementation Platform",
                          "Usage Frequency", "Exposure Covered (QAR mn)",
                          "AI system (QCB AI Guideline)", "Last Review Date"],
                "Value": [m["model_id"], m["version"], m["risk_type"], m["category"],
                          m["business_line"], m["methodology"], m["source"],
                          m.get("vendor") or "—",
                          m["implementation_platform"], m["usage_frequency"],
                          f"{m['exposure_covered_qar_mn']:,}",
                          ("Yes — high-risk" if m.get("qcb_ai_high_risk") else "Yes")
                          if m.get("ai_system") else "No",
                          utils.fmt_date(m["last_review_date"])],
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

    with st.expander("Tier and sign-off (gate G1)", expanded=not m["tier_confirmed"]):
        _tier_signoff(m)
        st.divider()
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
    _lifecycle_panel(m, model_requests)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ownership & Accountability")
        own = pd.DataFrame(
            {
                "Role": ["Model Owner", "Developer", "Validator", "Business Sponsor", "Approval Body"],
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
    utils.kpi_cards([
        ("Approval date", utils.fmt_date(m["approval_date"], "Not approved"), m["approval_body"]),
        ("Last validation", utils.fmt_date(m["last_validation"], "Never"), m.get("last_rating")),
        ("Next validation due", utils.fmt_date(m["next_validation_due"]), None),
        ("Frequency", m["validation_frequency"], f"Tier {m['tier']}"),
    ])
    st.caption(
        "Validation dates and the rating are derived from closed validation requests; "
        "frequency and approval body follow from the tier."
    )

    if vstatus == "Pre-implementation":
        st.info("Model not yet in use: an initial validation is required before approval and use.")
    elif vstatus in ("Overdue", "Never Validated"):
        st.error(f"Validation status: **{vstatus}**. This Tier {m['tier']} model requires immediate scheduling of independent validation.")
    elif vstatus == "Due Soon":
        st.warning("Validation due within 90 days — validation should be commissioned now.")
    else:
        st.success("Validation schedule on track.")

    if m["approval_date"] is None and m["status"].startswith("In Production"):
        st.error(
            "This model is in production **without formal approval** — a breach of the "
            f"model governance policy requiring escalation to the {m['approval_body']}."
        )
    if m["status"] == "In Production - Approval Pending":
        st.warning(
            "A new version is in use before its revalidation and approval are complete. "
            f"Escalate to the {m['approval_body']} and record compensating controls."
        )

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

    # ------------------------------------------------ Version history
    st.subheader("Version history")
    if m["change_log"]:
        done_vals = sorted(
            [r for r in model_requests if governance.counts_as_validation(r)],
            key=lambda r: r.get("closed_date") or "",
        )
        entries = sorted(m["change_log"], key=lambda e: e["date"])
        vrows = []
        for i, e in enumerate(entries):
            nxt = entries[i + 1]["date"] if i + 1 < len(entries) else "9999-12-31"
            vals = [r for r in done_vals if e["date"] <= (r.get("closed_date") or "") < nxt]
            if e.get("classification") == "Non-material":
                vstate = "Not required (non-material)"
            elif vals:
                vstate = f"{vals[-1]['outcome']} ({vals[-1]['request_id']}, {utils.fmt_date(vals[-1]['closed_date'])})"
            else:
                vstate = "Not validated"
            vrows.append({
                "Version": e["version"], "Date": utils.fmt_date(e["date"]),
                "Change": e.get("change_id", ""), "Classification": e.get("classification", "—"),
                "Validation of this version": vstate,
                "In use": "Current" if e["version"] == m["version"] else "",
            })
        st.dataframe(pd.DataFrame(list(reversed(vrows))), hide_index=True, width="stretch")
        if vrows and vrows[-1]["Validation of this version"] == "Not validated" and \
                m["status"] not in governance.PRE_IMPLEMENTATION_STATUSES:
            st.warning("The version in use has not been validated since its last material change.")
    else:
        st.caption("No versions recorded yet.")

    # ------------------------------------------------ Record Model Change (LoD 1)
    if auth.has_permission("record_change"):
        with st.expander("Record model change", expanded=False):
            st.info(
                "**Change classification policy.** **Material** changes — methodology, key "
                "assumptions, scope/use extension, or recalibration materially affecting outputs — "
                "require **independent revalidation before deployment** (model moves to "
                "*In Validation*). **Non-material** changes — parameter refresh within approved "
                "ranges, cosmetic/reporting changes — require **notification to the validator only**.",
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
                    change_id = None
                    try:
                        change_id = data_store.add_change_entry(selected, {
                        "date": chg_date.isoformat(),
                        "version": chg_version.strip(),
                        "description": chg_desc.strip(),
                        "author": auth.get_current_user()["name"],
                        "classification": chg_class,
                        "justification": chg_just.strip(),
                        })
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    if change_id and chg_file is not None:
                        data_store.attach_evidence(
                            selected, "change", change_id, chg_file,
                            chg_ev_cat, chg_ev_desc.strip(),
                        )
                    if change_id and chg_class == "Material":
                        flash_and_rerun(
                            f"Material change {change_id} (v{chg_version.strip()}) recorded — "
                            "model is In Validation. An **MC** request was opened on the "
                            "**Validation & Findings** tab for evidence and revalidation."
                        )
                    elif change_id:
                        flash_and_rerun(
                            f"Non-material change {change_id} (v{chg_version.strip()}) recorded. "
                            "An **MC** notification (Non-material) was opened for the validator "
                            "on Validation & Findings."
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
            assignee_opts = [
                auth.user_option_label(u) for u in auth.users_for_roles(*assignee_roles)
                if not governance.independence_conflict(m, u["name"], ir_type)
            ] or [auth.user_option_label(auth.get_current_user())]
            preferred = m.get("validator") if "LOD2" in assignee_roles else m.get("owner")
            a_idx = auth.default_option_index(assignee_opts, preferred)

            with st.form("initiate_request_form", clear_on_submit=True):
                ir_title = st.text_input("Title *", key="ir_title")
                ir_desc = st.text_area("Description *", key="ir_desc")
                ir_assigned = st.selectbox(
                    "Assign to *", assignee_opts, index=a_idx, key="ir_assigned",
                )
                st.caption(
                    "Assigning sets the request **In Progress**. Validators who own or "
                    "developed this model are excluded (independence rule)."
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
                    # Only a validator may record a completed, rated validation
                    if auth.get_current_user()["role"] == "LOD2":
                        close_immediately = st.checkbox(
                            "Record as completed (close with outcome now)",
                            value=True, key="ir_close_now",
                        )
                        if close_immediately:
                            ir_outcome = st.selectbox(
                                "Rating *", data_store.VALIDATION_OUTCOMES, key="ir_outcome",
                                help=" · ".join(
                                    f"{k}: {v}" for k, v in governance.RATING_DESCRIPTIONS.items()
                                ),
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
                    try:
                        new_rid = data_store.create_request(selected, payload)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        flash_and_rerun(f"Request {new_rid} created.")
    else:
        st.caption(
            f"No initiate actions for your role "
            f"({auth.ROLE_LABELS[auth.get_current_user()['role']]})."
        )

    # ------------------------------------------------ Request register (list ↔ detail)
    def _type_cell(r: dict) -> str:
        """Type plus short materiality / nature / severity when present."""
        t = r.get("type") or ""
        if t == "MC" and r.get("materiality"):
            return f"MC · {r['materiality']}"
        if t == "VAL" and r.get("validation_subtype"):
            sub = r["validation_subtype"]
            return f"VAL · {sub[:28] + '…' if len(sub) > 28 else sub}"
        if t == "FND" and r.get("severity"):
            return f"FND · {r['severity']}"
        return t

    selected_rid = st.session_state.get("md_selected_request")
    if selected_rid and not any(r["request_id"] == selected_rid for r in model_requests):
        st.session_state.pop("md_selected_request", None)
        selected_rid = None

    if selected_rid is None:
        # ---- LIST VIEW: clickable Request ID (same-tab detail via session)
        st.subheader("Request register")
        f1, f2 = st.columns(2)
        with f1:
            type_f = st.selectbox(
                "Type",
                ["All", "MC", "VAL", "FND"],
                key="req_type_filter",
            )
        with f2:
            status_f = st.selectbox(
                "Status",
                ["All", *data_store.REQUEST_STATUSES],
                key="req_status_filter",
            )

        filtered = [
            r for r in model_requests
            if (type_f == "All" or r["type"] == type_f)
            and (status_f == "All" or r["status"] == status_f)
        ]
        # Open / In Progress first (newest), then Closed (newest).
        open_part = sorted(
            [r for r in filtered if r.get("status") != "Closed"],
            key=lambda r: (r.get("created_date") or "", r["request_id"]),
            reverse=True,
        )
        closed_part = sorted(
            [r for r in filtered if r.get("status") == "Closed"],
            key=lambda r: (r.get("created_date") or "", r["request_id"]),
            reverse=True,
        )
        filtered = open_part + closed_part

        st.caption(
            f"{len(filtered)} request(s) · click a **Request ID** to open detail "
            "(same page — use ← Back to list to return)."
        )

        if not filtered:
            st.info("No requests match the current filters.")
        else:
            PAGE = 50
            total = len(filtered)
            if total > PAGE:
                n_pages = (total + PAGE - 1) // PAGE
                page_i = st.number_input(
                    "Page",
                    min_value=1,
                    max_value=n_pages,
                    value=1,
                    key="req_register_page",
                )
                start = (int(page_i) - 1) * PAGE
                page_rows = filtered[start:start + PAGE]
                st.caption(f"Showing {start + 1}–{start + len(page_rows)} of {total}")
            else:
                page_rows = filtered

            h1, h2, h3, h4, h5, h6 = st.columns([1.15, 1.35, 2.6, 1.0, 1.4, 1.0])
            h1.caption("Request ID")
            h2.caption("Type")
            h3.caption("Title")
            h4.caption("Status")
            h5.caption("Assigned")
            h6.caption("Created")

            for r in page_rows:
                rid = r["request_id"]
                c1, c2, c3, c4, c5, c6 = st.columns(
                    [1.15, 1.35, 2.6, 1.0, 1.4, 1.0]
                )
                with c1:
                    if st.button(
                        rid,
                        key=f"req_open_{selected}_{rid}",
                        type="tertiary",
                        width="stretch",
                    ):
                        st.session_state["md_selected_request"] = rid
                        st.rerun()
                c2.markdown(f"`{_type_cell(r)}`")
                title = (r.get("title") or "—").strip() or "—"
                if len(title) > 48:
                    title = title[:47] + "…"
                c3.markdown(title)
                c4.caption(r.get("status") or "—")
                assigned = (r.get("assigned_to") or "—").split("(")[0].strip()
                if len(assigned) > 22:
                    assigned = assigned[:21] + "…"
                c5.caption(assigned)
                c6.caption(utils.fmt_date(r.get("created_date")))

        with st.expander("Counts by type", expanded=False):
            counts = []
            for t in auth.REQUEST_TYPE_ORDER:
                n = sum(1 for r in model_requests if r["type"] == t)
                n_open = sum(
                    1 for r in model_requests
                    if r["type"] == t and r["status"] != "Closed"
                )
                counts.append({
                    "Type": t,
                    "Label": auth.REQUEST_TYPES[t]["label"],
                    "Total": n,
                    "Open": n_open,
                })
            st.dataframe(pd.DataFrame(counts), hide_index=True, width="stretch")

    else:
        # ---- DETAIL VIEW
        req = next(r for r in model_requests if r["request_id"] == selected_rid)
        is_closed = req["status"] == "Closed"
        status_color = {
            "Open": utils.AMBER, "In Progress": utils.NAVY, "Closed": utils.GREEN,
        }.get(req["status"], utils.GREY)

        back_col, _ = st.columns([1.4, 4])
        with back_col:
            if st.button("← Back to list", key="req_back_to_list", width="stretch"):
                st.session_state.pop("md_selected_request", None)
                st.rerun()

        st.markdown(
            utils.badge(req["request_id"], utils.GREY)
            + utils.badge(auth.REQUEST_TYPES[req["type"]]["label"], utils.NAVY)
            + utils.badge(req["status"], status_color)
            + (utils.severity_badge(req["severity"]) if req.get("severity") else "")
            + (
                utils.rating_badge(req["outcome"])
                if req.get("outcome") in governance.RATING_SCALE
                else utils.badge(req["outcome"], utils.GREEN) if req.get("outcome") else ""
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f"### {req['title']}")
        st.markdown(req.get("description") or "_No description._")
        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f"**Initiated by:** {req.get('initiated_by', '—')}")
        m2.markdown(f"**Assigned to:** {req.get('assigned_to', '—')}")
        m3.markdown(f"**Created:** {utils.fmt_date(req.get('created_date'))}")
        m4.markdown(
            f"**Closed:** {utils.fmt_date(req['closed_date'])}" if req.get("closed_date")
            else f"**Due:** {utils.fmt_date(req.get('due_date'))}"
        )
        if req.get("remediation"):
            st.markdown(f"**Remediation.** {req['remediation']}")
        if req.get("materiality"):
            st.caption(f"Materiality: {req['materiality']}")
        if req.get("tests"):
            st.markdown("**Tests:** " + ", ".join(req["tests"]))
        if req.get("outcome") in governance.RATING_DESCRIPTIONS:
            st.caption(f"Rating meaning: {governance.RATING_DESCRIPTIONS[req['outcome']]}")
        if req.get("validation_subtype"):
            st.caption(f"Nature: {req['validation_subtype']}")

        if is_closed:
            st.warning(
                "This request is **Closed** — read-only "
                "(no upload, edit, or new comments)."
            )

        if req.get("engagement"):
            _engagement_panel(req, m)

        # ---- Evidence
        st.markdown("**Evidence**")
        req_ev = _evidence_for("validation_request", req["request_id"], evidence_all)
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
            if auth.has_permission("assign_request"):
                with st.form(f"assign_form_{req['request_id']}", clear_on_submit=True):
                    roles = auth.REQUEST_TYPES[req["type"]]["default_assignee_roles"]
                    all_opts = [
                        auth.user_option_label(u) for u in auth.users_for_roles(*roles)
                        if not governance.independence_conflict(m, u["name"], req["type"])
                    ]
                    a_idx = auth.default_option_index(all_opts, req.get("assigned_to"))
                    new_assignee = st.selectbox(
                        "Send / assign to", all_opts, index=a_idx,
                        key=f"assign_to_{req['request_id']}",
                    )
                    st.caption(
                        "Validations and model changes go to validators; findings go to "
                        "model owners. The assignee sees it in the request register."
                    )
                    assign_go = st.form_submit_button("Update assignment")
                if assign_go:
                    try:
                        data_store.assign_request(req["request_id"], new_assignee)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        flash_and_rerun(f"{req['request_id']} assigned to {new_assignee}.")

            if auth.has_permission("respond_request"):
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
                        st.error(
                            "Provide a short evidence description when attaching a file."
                        )
                    else:
                        rid = data_store.peek_next_thread_id(req["request_id"])
                        try:
                            ev_ids = []
                            if resp_file is not None:
                                ev_ids.append(data_store.attach_evidence(
                                    selected, "request_response", rid, resp_file,
                                    resp_cat, resp_desc.strip() or f"Evidence on {rid}",
                                ))
                            data_store.add_request_response(
                                req["request_id"], resp_text.strip(), ev_ids,
                            )
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))
                        else:
                            flash_and_rerun(
                                f"Response {rid} added to {req['request_id']}."
                            )

            if req.get("engagement"):
                pass  # closed by signing off the engagement above
            elif auth.can_close_request(req):
                with st.form(f"close_form_{req['request_id']}", clear_on_submit=True):
                    close_comment = st.text_input(
                        "Closure comment *", key=f"close_txt_{req['request_id']}",
                    )
                    close_outcome = None
                    close_tests: list[str] = []
                    if req["type"] in ("VAL", "MC"):
                        close_outcome = st.selectbox(
                            "Rating *", data_store.VALIDATION_OUTCOMES,
                            key=f"close_out_{req['request_id']}",
                            help=" · ".join(
                                f"{k}: {v}" for k, v in governance.RATING_DESCRIPTIONS.items()
                            ),
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
                        "Evidence description",
                        key=f"close_desc_{req['request_id']}",
                        placeholder="Short note if attaching a file",
                    )
                    close_submit = st.form_submit_button(
                        "Close request", type="primary",
                    )
                if close_submit:
                    if not close_comment.strip():
                        st.error("A closure comment is required.")
                    elif req["type"] in ("VAL", "MC") and not close_outcome:
                        st.error("Outcome is required to close this request.")
                    elif close_file is not None and not close_desc.strip():
                        st.error(
                            "Provide a short evidence description when attaching a file."
                        )
                    else:
                        rid = data_store.peek_next_thread_id(req["request_id"])
                        try:
                            ev_ids = []
                            if close_file is not None:
                                ev_ids.append(data_store.attach_evidence(
                                    selected, "request_response", rid, close_file,
                                    close_cat,
                                    close_desc.strip()
                                    or f"Closure evidence on {req['request_id']}",
                                ))
                            data_store.close_request(
                                req["request_id"],
                                close_comment.strip(),
                                outcome=close_outcome,
                                evidence_ids=ev_ids,
                                tests=close_tests or None,
                            )
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))
                        else:
                            flash_and_rerun(f"Request {req['request_id']} closed.")
            else:
                st.caption(
                    "Closing: findings are closed by the line that raised them; "
                    "validations and model changes by a validator. "
                    "The MRM Administrator cannot close requests (segregation of duties)."
                )

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
        docs = documentation_status(m, evidence_all)
        complete = sum(docs.values())
        st.progress(complete / len(docs), text=f"{complete} of {len(docs)} artefacts in place")
        model_docs = [e for e in model_evidence if e.get("linked_type") == "model"]
        for doc, ok in docs.items():
            icon = "✅" if ok else "❌"
            n_files = sum(1 for e in model_docs if e.get("doc_type") == doc)
            where = f" · {n_files} file(s) uploaded" if n_files else (
                " · recorded as held outside the platform" if ok else ""
            )
            st.markdown(f"{icon} {doc}<span style='color:#888; font-size:0.8rem;'>{where}</span>",
                        unsafe_allow_html=True)
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

    # ------------------------------------------------ Model documents (upload)
    st.subheader("Model documents")
    st.caption(
        "Upload model documentation here (development document, methodology, data quality "
        "assessment, user guide, monitoring plan and any other supporting file). Files go to "
        "the dedicated evidence folder with a SHA-256 fingerprint; choosing a checklist type "
        "ticks that item."
    )
    model_docs = sorted(
        [e for e in model_evidence if e.get("linked_type") == "model"],
        key=lambda e: e.get("uploaded_at", ""), reverse=True,
    )
    _render_evidence_rows(model_docs, "modeldoc")
    if auth.has_permission("upload_evidence"):
        with st.form("model_doc_form", clear_on_submit=True):
            md_file = st.file_uploader(
                "File *", type=data_store.ALLOWED_UPLOAD_TYPES, key="md_doc_file",
            )
            dc1, dc2 = st.columns(2)
            with dc1:
                md_type = st.selectbox(
                    "Document type *",
                    list(m["documentation"].keys()) + [data_store.OTHER_DOC_TYPE],
                    key="md_doc_type",
                )
            with dc2:
                md_desc = st.text_input("Short description *", key="md_doc_desc")
            md_submit = st.form_submit_button("Upload document")
        if md_submit:
            if md_file is None:
                st.error("Choose a file to upload.")
            elif not md_desc.strip():
                st.error("A short description is required.")
            else:
                try:
                    eid = data_store.attach_evidence(
                        selected, "model", selected, md_file, "Document", md_desc.strip(),
                        doc_type=md_type,
                    )
                except (PermissionError, ValueError) as exc:
                    st.error(str(exc))
                else:
                    flash_and_rerun(f"Document {eid} uploaded ({md_type}).")

    # Inventory of every file held for this model, with integrity status
    with st.expander(f"All files for this model ({len(model_evidence)})", expanded=False):
        if model_evidence:
            rows = []
            for e in sorted(model_evidence, key=lambda x: x["uploaded_at"], reverse=True):
                _, state = data_store.read_evidence(e)
                rows.append({
                    "ID": e["evidence_id"],
                    "File": e["filename"],
                    "Linked to": f"{e['linked_type']}: {e['linked_id']}",
                    "Type": e.get("doc_type") or e["category"],
                    "Uploaded": utils.fmt_date(e["uploaded_at"]),
                    "By": e["uploaded_by"],
                    "SHA-256": (e.get("sha256") or "")[:12] + "…",
                    "Integrity": INTEGRITY_LABEL[state],
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.caption("No files registered for this model yet.")

    st.subheader("Audit Trail")
    chain_ok, broken_at = repository.verify_audit_chain()
    if chain_ok:
        st.caption(
            "Workflow actions on this model, most recent first. The log is append-only and "
            "hash-chained: integrity check passed."
        )
    else:
        st.error(
            f"Audit log integrity check FAILED at event #{broken_at}: the log was changed "
            "outside the platform."
        )
    trail = [e for e in load_audit_log() if e["model_id"] == selected]
    if trail:
        tr = pd.DataFrame(sorted(trail, key=lambda e: e["seq"], reverse=True))
        tr["Change recorded"] = tr.apply(
            lambda r: "before and after" if r["before"] and r["after"]
            else "new record" if r["after"] else "—",
            axis=1,
        )
        tr = tr.rename(columns={
            "seq": "#", "timestamp": "Timestamp", "user": "User", "role": "Role",
            "action": "Action", "entity_type": "Entity Type", "entity_id": "Entity",
            "details": "Details",
        })[["#", "Timestamp", "User", "Role", "Action", "Entity", "Details", "Change recorded"]]
        st.dataframe(tr, hide_index=True, width="stretch")
    else:
        st.caption("No audit trail events recorded for this model yet.")

# ================================================================ Edit Record
with tab_edit:
    user = auth.get_current_user()
    is_admin = auth.has_permission("assign_accountability")
    can_edit = auth.has_permission("edit_model") and (
        is_admin or governance.is_owner_or_developer(m, user["name"])
    )
    if not can_edit:
        st.info(
            "Only the model's owner or developer, or the MRM Administrator, can edit this record. "
            "Tier changes go through the sign-off on the Overview tab; status and validation dates "
            "move through the workflows."
        )
    else:
        st.caption(
            "Every saved change is logged with its before and after values. Tier, status and "
            "validation dates are not edited here."
        )
        models_all = load_models()
        other_ids = {x["model_id"]: f"{x['model_id']} — {x['name']}" for x in models_all
                     if x["model_id"] != selected}
        with st.form("edit_record_form"):
            st.markdown("**Description**")
            e1, e2 = st.columns(2)
            with e1:
                f_name = st.text_input("Model name", m["name"])
                f_cat = st.text_input("Category", m["category"])
                f_bl = st.text_input("Business line", m["business_line"])
                f_meth = st.text_input("Methodology", m["methodology"])
                f_src = st.selectbox(
                    "Source", governance.SOURCES + ([m["source"]] if m["source"] not in governance.SOURCES else []),
                    index=(governance.SOURCES + [m["source"]]).index(m["source"]),
                )
                f_vendor = st.text_input("Vendor", m.get("vendor") or "")
            with e2:
                f_plat = st.text_input("Implementation platform", m["implementation_platform"])
                f_usage = st.text_input("Usage frequency", m["usage_frequency"])
                f_exp = st.number_input("Exposure covered (QAR mn)", min_value=0, step=100,
                                        value=int(m["exposure_covered_qar_mn"]))
                f_up = st.multiselect(
                    "Upstream models", list(other_ids),
                    default=[u for u in m["dependencies"]["upstream"] if u in other_ids],
                    format_func=lambda i: other_ids[i],
                )
            f_desc = st.text_area("Purpose / description", m["description"])
            l1, l2 = st.columns(2)
            with l1:
                f_data = st.text_area("Data sources (one per line)", "\n".join(m["data_sources"]))
                f_users = st.text_area("Model users (one per line)", "\n".join(m["model_users"]))
                f_regmap = st.text_area("Regulatory mapping (one per line)", "\n".join(m["regulatory_mapping"]))
            with l2:
                f_ass = st.text_area("Key assumptions (one per line)", "\n".join(m["key_assumptions"]))
                f_lim = st.text_area("Known limitations (one per line)", "\n".join(m["known_limitations"]))

            st.markdown("**Uses**")
            f_uses = st.data_editor(
                pd.DataFrame(m.get("uses") or [], columns=["use", "business_area", "decision", "status"]),
                num_rows="dynamic", width="stretch", key="edit_uses",
                column_config={
                    "use": "Use", "business_area": "Business area", "decision": "Decision supported",
                    "status": st.column_config.SelectboxColumn("Status", options=governance.USE_STATUSES),
                },
            )

            st.markdown("**AI system (QCB AI Guideline)**")
            f_ai = st.checkbox("This model is an AI system", bool(m.get("ai_system")))
            a1, a2 = st.columns(2)
            with a1:
                f_aicat = st.selectbox(
                    "Functional category", governance.AI_FUNCTIONAL_CATEGORIES,
                    index=governance.AI_FUNCTIONAL_CATEGORIES.index(m["ai_functional_category"])
                    if m.get("ai_functional_category") in governance.AI_FUNCTIONAL_CATEGORIES else 0,
                )
                f_airole = st.selectbox(
                    "QDB's role", governance.AI_PROVIDER_ROLES,
                    index=governance.AI_PROVIDER_ROLES.index(m["ai_provider_role"])
                    if m.get("ai_provider_role") in governance.AI_PROVIDER_ROLES else 0,
                )
            with a2:
                f_aiaut = st.selectbox(
                    "Human oversight", governance.AI_AUTONOMY,
                    index=governance.AI_AUTONOMY.index(m["ai_autonomy"])
                    if m.get("ai_autonomy") in governance.AI_AUTONOMY else 0,
                )
                f_aiqcb = st.selectbox(
                    "QCB approval status", governance.QCB_APPROVAL_STATUSES,
                    index=governance.QCB_APPROVAL_STATUSES.index(m["qcb_approval_status"])
                    if m.get("qcb_approval_status") in governance.QCB_APPROVAL_STATUSES else 0,
                )
            f_aihigh = st.checkbox("High-risk AI system (QCB classification)", bool(m.get("qcb_ai_high_risk")))

            assign = {}
            if is_admin:
                st.markdown("**Accountability** (MRM Administrator)")
                lod1 = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
                owners = lod1 + ([m["owner"]] if m["owner"] not in lod1 else [])
                vals = ["Not yet assigned"] + [
                    auth.user_option_label(u) for u in auth.users_for_roles("LOD2")
                    if not governance.independence_conflict(m, u["name"], "VAL")
                ]
                if m["validator"] not in vals:
                    vals.append(m["validator"])
                s1, s2 = st.columns(2)
                with s1:
                    assign["owner"] = st.selectbox("Owner", owners, index=owners.index(m["owner"]))
                    assign["developer"] = st.text_input("Developer", m["developer"])
                    assign["risk_type"] = st.selectbox(
                        "Risk type", governance.RISK_TYPES,
                        index=governance.RISK_TYPES.index(m["risk_type"])
                        if m["risk_type"] in governance.RISK_TYPES else 0,
                    )
                with s2:
                    assign["validator"] = st.selectbox(
                        "Validator", vals, index=vals.index(m["validator"]),
                        help="Validators who own or develop this model are excluded (independence).",
                    )
                    assign["sponsor"] = st.text_input("Business sponsor", m["sponsor"])
            save = st.form_submit_button("Save changes", type="primary")

        if save:
            uses = [
                {k: ("" if pd.isna(v) else str(v).strip()) for k, v in row.items()}
                for row in f_uses.to_dict("records") if str(row.get("use") or "").strip()
                and not pd.isna(row.get("use"))
            ]
            changes = {
                "name": f_name.strip(), "category": f_cat.strip(), "business_line": f_bl.strip(),
                "methodology": f_meth.strip(), "source": f_src, "vendor": f_vendor.strip() or None,
                "implementation_platform": f_plat.strip(), "usage_frequency": f_usage.strip(),
                "exposure_covered_qar_mn": int(f_exp), "upstream": f_up,
                "description": f_desc.strip(), "data_sources": f_data, "model_users": f_users,
                "regulatory_mapping": f_regmap, "key_assumptions": f_ass, "known_limitations": f_lim,
                "uses": uses, "ai_system": f_ai,
            }
            if f_ai:
                changes.update({
                    "ai_functional_category": f_aicat, "ai_provider_role": f_airole,
                    "ai_autonomy": f_aiaut, "qcb_approval_status": f_aiqcb, "qcb_ai_high_risk": f_aihigh,
                })
            changes.update(assign)
            try:
                changed = data_store.update_model(selected, changes)
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            else:
                if changed:
                    flash_and_rerun(f"Saved: {', '.join(changed)}.")
                else:
                    st.info("No changes to save.")
