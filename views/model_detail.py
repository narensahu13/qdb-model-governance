"""Model Detail — one model's record, its lifecycle and the work on it.

Design rule: show the record; show a form only when the person viewing can act
and chooses to ("Record a change", "Upload a document" ...). Everything that
needs attention is summarised once, at the top.
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as pgo
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
    requests_for_model,
    validation_status,
)

INTEGRITY_LABEL = {
    "ok": "fingerprint verified",
    "altered": "FILE ALTERED since upload",
    "missing": "file missing from evidence folder",
}
GATE_ICON = {"done": "✅", "current": "🟡", "pending": "⚪"}
STEP_LABEL = {"G1": "Step 1 of 5", "G2": "Step 2 of 5", "G3": "Step 3 of 5", "G4": "Step 4 of 5",
              "G5": "Step 5 of 5"}


# ================================================================ helpers
def flash_and_rerun(msg: str):
    st.session_state["_flash"] = msg
    st.rerun()


def _act(fn, msg, *args, **kwargs):
    """Run a data_store action; show the rule it broke, or refresh with a message."""
    try:
        fn(*args, **kwargs)
    except (PermissionError, ValueError) as exc:
        st.error(str(exc))
    else:
        flash_and_rerun(msg)


def _evidence_for(linked_type, linked_id, evidence_all):
    return [e for e in evidence_all
            if e.get("linked_type") == linked_type and e.get("linked_id") == linked_id]


def _files(items, key_prefix: str) -> None:
    """Compact list of files with download buttons and integrity status."""
    for ev in sorted(items, key=lambda e: e.get("uploaded_at", ""), reverse=True):
        data, state = data_store.read_evidence(ev)
        c1, c2 = st.columns([5, 1.2])
        color = utils.GREEN if state == "ok" else utils.RED
        c1.markdown(
            f"📄 **{ev['filename']}** — {ev.get('description', '')}<br>"
            f"<span style='font-size:0.78rem; color:#888;'>{ev.get('doc_type') or ev['category']} · "
            f"{ev['uploaded_by']} · {utils.fmt_date(ev['uploaded_at'])} · "
            f"<span style='color:{color};'>{INTEGRITY_LABEL[state]}</span></span>",
            unsafe_allow_html=True,
        )
        if data is not None:
            c2.download_button("Download", data=data, file_name=ev["filename"],
                               key=f"dl_{key_prefix}_{ev['evidence_id']}", width="stretch")


def _can_edit(m: dict, user: dict) -> bool:
    return auth.has_permission("edit_model") and (
        user["role"] == "ADMIN" or governance.is_owner_or_developer(m, user["name"]))


def _attention(m: dict, vstatus: str, model_requests: list[dict]) -> tuple[str, list[str]]:
    """(next step, issues) for the single box at the top of the page."""
    cur = governance.current_gate(m)
    who_owner = governance.person_name(m["owner"])
    if cur == "G1":
        nxt = "Step 1 of 5 — the tier must be confirmed by the MRM function (Summary tab)."
    elif cur == "G2":
        missing = data_loader.g2_missing_docs(m)
        nxt = (f"Step 2 of 5 — {who_owner} or the developer submits the model for validation "
               "(Lifecycle tab)" + (f"; first upload: {', '.join(missing)}." if missing else "."))
    elif cur == "G3":
        open_v = [r for r in model_requests if r.get("engagement") and r["status"] != "Closed"]
        nxt = ("Step 3 of 5 — validation in progress"
               + (f": {open_v[0]['request_id']} at *{open_v[0]['engagement']['stage']}*" if open_v else "")
               + " (Validation tab).")
    elif cur == "G4":
        nxt = f"Step 4 of 5 — awaiting approval by the {m['approval_body']} (Lifecycle tab)."
    elif cur == "G5":
        nxt = "Step 5 of 5 — a validator checks the deployed version before use (Lifecycle tab)."
    else:
        nxt = (f"In use. Next validation due {utils.fmt_date(m['next_validation_due'])}."
               if m.get("next_validation_due") else f"Status: {m['status']}.")

    issues = []
    if vstatus == "Overdue":
        issues.append(f"Validation overdue since {utils.fmt_date(m['next_validation_due'])}.")
    if vstatus == "Never Validated":
        issues.append("In use but never validated.")
    if m["status"] == "In Production - Approval Pending":
        issues.append("A new version is in use before revalidation and approval.")
    if m["status"] in governance.IN_USE_STATUSES and not m.get("approval_date"):
        issues.append(f"In use without formal approval — escalate to the {m['approval_body']}.")
    if not m["tier_confirmed"] and cur != "G1":
        issues.append("A tier reassessment is awaiting sign-off (Summary tab).")
    open_f = [r for r in model_requests if r["type"] == "FND" and r["status"] != "Closed"]
    late = [r for r in open_f if r.get("due_date") and r["due_date"] < date.today().isoformat()]
    high = [r for r in open_f if r.get("severity") == "High"]
    if high:
        issues.append(f"{len(high)} open high-severity finding(s).")
    if late:
        issues.append(f"{len(late)} finding(s) past their due date.")
    open_cond = [c for ap in m.get("approvals") or [] for c in ap.get("conditions", [])
                 if c["status"] != governance.CONDITION_VERIFIED]
    if open_cond and m["status"] in governance.IN_USE_STATUSES | {governance.STATUS_AWAITING_IMPLEMENTATION}:
        issues.append(f"{len(open_cond)} condition(s) of approval not yet verified.")
    return nxt, issues


# ================================================================ tier sign-off (G1)
def _tier_panel(m: dict) -> None:
    ta = m.get("tier_assessment") or {}
    user = auth.get_current_user()
    status = ta.get("status", governance.TIER_CONFIRMED)
    tier_info = tiering.compute_tier(**m["tier_scores"])
    proposed_tier = tiering.compute_tier(**ta["scores"])["tier"] if ta.get("scores") else m["tier"]

    st.markdown(
        f"{utils.tier_badge(m['tier'])} <span style='color:#444;'>{tier_info['explanation']}</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Rationale: {m.get('tier_rationale') or '—'} · scores: materiality "
               f"{m['tier_scores']['materiality']}, complexity {m['tier_scores']['complexity']}, "
               f"regulatory impact {m['tier_scores']['regulatory_impact']}")
    if status == governance.TIER_CONFIRMED:
        note = "Confirmed"
        if ta.get("confirmed_by"):
            note += f" by {ta['confirmed_by']} on {utils.fmt_date(ta.get('confirmed_on'))}"
        if m.get("tier_override"):
            note += f" — CRO-approved override of the rule-based Tier {m['computed_tier']}"
        st.caption(note + ".")
    elif status == governance.TIER_PROPOSED:
        st.warning(
            f"Tier {proposed_tier} proposed by {ta['proposed_by']} on {utils.fmt_date(ta['proposed_on'])} "
            f"(materiality {ta['scores']['materiality']}, complexity {ta['scores']['complexity']}, "
            f"regulatory impact {ta['scores']['regulatory_impact']}) — awaiting confirmation. "
            f"Rationale: {ta.get('rationale') or '—'}"
        )
    else:
        st.warning(f"Override to Tier {ta['override_tier']} (rule-based Tier {proposed_tier}) awaiting "
                   f"CRO approval. Reason: {ta['override_reason']}")

    if status == governance.TIER_PROPOSED and auth.has_permission("confirm_tier") \
            and ta.get("proposed_by") != user["name"]:
        with st.form(f"confirm_tier_{m['model_id']}"):
            ov = st.selectbox(
                "Final tier", [proposed_tier] + [t for t in (1, 2, 3) if t != proposed_tier],
                format_func=lambda t: f"Tier {t}" + (" (rule-based)" if t == proposed_tier else " — override"),
                key=f"ct_tier_{m['model_id']}",
            )
            reason = st.text_input("Override reason (only for an override)", key=f"ct_reason_{m['model_id']}")
            go_confirm = st.form_submit_button("Confirm tier", type="primary")
        if go_confirm:
            _act(data_store.confirm_tier, "Tier signed off.", m["model_id"],
                 override_tier=ov if ov != proposed_tier else None, override_reason=reason)
    elif status == governance.TIER_OVERRIDE_PENDING and auth.has_permission("approve_tier_override"):
        with st.form(f"cro_tier_{m['model_id']}"):
            comment = st.text_input("Comment", key=f"cro_c_{m['model_id']}")
            c_a, c_b = st.columns(2)
            approve = c_a.form_submit_button("Approve override", type="primary")
            reject = c_b.form_submit_button("Reject — keep rule-based tier")
        if approve or reject:
            _act(data_store.decide_tier_override,
                 "Tier override approved." if approve else "Tier override rejected.",
                 m["model_id"], bool(approve), comment)
    elif status == governance.TIER_CONFIRMED and auth.has_permission("propose_tier") and (
            user["role"] == "ADMIN" or governance.is_owner_or_developer(m, user["name"])):
        if st.toggle("Propose a tier reassessment", key=f"pt_toggle_{m['model_id']}"):
            with st.form(f"propose_tier_{m['model_id']}"):
                cur = m["tier_scores"]
                p1, p2, p3 = st.columns(3)
                pm = p1.selectbox("Materiality", tiering.LEVELS, index=tiering.LEVELS.index(cur["materiality"]))
                pc = p2.selectbox("Complexity", tiering.LEVELS, index=tiering.LEVELS.index(cur["complexity"]))
                pr = p3.selectbox("Regulatory impact", tiering.LEVELS,
                                  index=tiering.LEVELS.index(cur["regulatory_impact"]))
                prat = st.text_area("Rationale *")
                go_prop = st.form_submit_button("Submit for sign-off")
            if go_prop:
                _act(data_store.propose_tier, "Tier reassessment submitted for sign-off.", m["model_id"],
                     {"materiality": pm, "complexity": pc, "regulatory_impact": pr}, prat)

    if m.get("tier_history"):
        st.dataframe(pd.DataFrame([{
            "Previous tier": h.get("tier"), "Override": h.get("override") or "—",
            "Rationale": h.get("rationale"), "Confirmed by": h.get("confirmed_by"),
            "Confirmed on": utils.fmt_date(h.get("confirmed_on")),
        } for h in reversed(m["tier_history"])]), hide_index=True, width="stretch")


# ================================================================ record editor
def _edit_form(m: dict, user: dict) -> None:
    is_admin = auth.has_permission("assign_accountability")
    others = {x["model_id"]: f"{x['model_id']} — {x['name']}" for x in load_models()
              if x["model_id"] != m["model_id"]}
    with st.form("edit_record_form"):
        e1, e2 = st.columns(2)
        with e1:
            f_name = st.text_input("Model name", m["name"])
            f_meth = st.text_input("Methodology", m["methodology"])
            f_cat = st.text_input("Category", m["category"])
            f_bl = st.text_input("Business line", m["business_line"])
            srcs = governance.SOURCES + ([m["source"]] if m["source"] not in governance.SOURCES else [])
            f_src = st.selectbox("Source", srcs, index=srcs.index(m["source"]))
            f_vendor = st.text_input("Vendor", m.get("vendor") or "")
        with e2:
            f_plat = st.text_input("Implementation platform", m["implementation_platform"])
            f_usage = st.text_input("Usage frequency", m["usage_frequency"])
            f_exp = st.number_input("Exposure covered (QAR mn)", min_value=0, step=100,
                                    value=int(m["exposure_covered_qar_mn"]))
            f_up = st.multiselect("Upstream models (feed this model)", list(others),
                                  default=[u for u in m["dependencies"]["upstream"] if u in others],
                                  format_func=lambda i: others[i])
            f_ai = st.checkbox("AI system (QCB AI Guideline)", bool(m.get("ai_system")))
            f_aihigh = st.checkbox("High-risk AI system", bool(m.get("qcb_ai_high_risk")))
        f_desc = st.text_area("Purpose", m["description"])
        l1, l2 = st.columns(2)
        with l1:
            f_users = st.text_area("Model users (one per line)", "\n".join(m["model_users"]))
            f_data = st.text_area("Data sources (one per line)", "\n".join(m["data_sources"]))
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
        assign = {}
        if is_admin:
            st.markdown("**Accountability** (MRM administrator)")
            lod1 = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
            owners = lod1 + ([m["owner"]] if m["owner"] not in lod1 else [])
            vals = ["Not yet assigned"] + [auth.user_option_label(u) for u in auth.users_for_roles("LOD2")
                                           if not governance.independence_conflict(m, u["name"], "VAL")]
            if m["validator"] not in vals:
                vals.append(m["validator"])
            s1, s2 = st.columns(2)
            assign["owner"] = s1.selectbox("Model owner", owners, index=owners.index(m["owner"]))
            assign["developer"] = s1.text_input("Model developer", m["developer"])
            assign["validator"] = s2.selectbox("Model validator", vals, index=vals.index(m["validator"]))
            assign["sponsor"] = s2.text_input("Model sponsor", m["sponsor"])
        save = st.form_submit_button("Save changes", type="primary")
    if save:
        uses = [{k: ("" if pd.isna(v) else str(v).strip()) for k, v in row.items()}
                for row in f_uses.to_dict("records")
                if not pd.isna(row.get("use")) and str(row.get("use") or "").strip()]
        changes = {
            "name": f_name.strip(), "methodology": f_meth.strip(), "category": f_cat.strip(),
            "business_line": f_bl.strip(), "source": f_src, "vendor": f_vendor.strip() or None,
            "implementation_platform": f_plat.strip(), "usage_frequency": f_usage.strip(),
            "exposure_covered_qar_mn": int(f_exp), "upstream": f_up, "description": f_desc.strip(),
            "model_users": f_users, "data_sources": f_data, "regulatory_mapping": f_regmap,
            "key_assumptions": f_ass, "known_limitations": f_lim, "uses": uses, "ai_system": f_ai,
        }
        if f_ai:
            changes["qcb_ai_high_risk"] = f_aihigh
        changes.update(assign)
        try:
            changed = data_store.update_model(m["model_id"], changes)
        except (PermissionError, ValueError) as exc:
            st.error(str(exc))
        else:
            if changed:
                flash_and_rerun(f"Saved: {', '.join(changed)}.")
            else:
                st.info("No changes to save.")


# ================================================================ lifecycle (G2–G5)
def _lifecycle(m: dict, model_requests: list[dict]) -> None:
    user = auth.get_current_user()
    cols = st.columns(5)
    for col, g in zip(cols, governance.gate_states(m)):
        col.markdown(
            f"<div style='border:1px solid #e0e0e0; border-radius:8px; padding:8px 10px; "
            f"background:{'#fff8e1' if g['state'] == 'current' else '#fff'};'>"
            f"<div style='font-size:0.75rem; color:#666;'>{STEP_LABEL[g['gate']]}</div>"
            f"<div style='font-weight:600;'>{GATE_ICON[g['state']]} {g['name']}</div></div>",
            unsafe_allow_html=True,
        )
    st.markdown("")
    cur = governance.current_gate(m)

    if cur == "G2" and auth.has_permission("submit_for_validation") and (
            user["role"] == "ADMIN" or governance.is_owner_or_developer(m, user["name"])):
        missing = data_loader.g2_missing_docs(m)
        with st.form(f"g2_{m['model_id']}"):
            st.markdown("**Submit for validation**")
            st.caption(f"Required documents: {', '.join(governance.G2_REQUIRED_DOCS[m['tier']])}."
                       + (f" Missing: {', '.join(missing)} — upload them on the Documents tab." if missing else ""))
            note = st.text_input("Note to the validator (optional)")
            go = st.form_submit_button("Submit for validation", type="primary", disabled=bool(missing))
        if go:
            _act(data_store.submit_for_validation, "Submitted — a validation request is open.", m["model_id"], note)

    if cur == "G4" and auth.has_permission("record_approval") and (
            user["role"] == "CRO" or (user["role"] == "ADMIN" and m["tier"] == 1)):
        with st.form(f"g4_{m['model_id']}"):
            st.markdown(f"**Approval decision — {m['approval_body']}**"
                        + (" (recorded by the secretary or the CRO)" if m["tier"] == 1 else ""))
            decision = st.selectbox("Decision", governance.APPROVAL_DECISIONS)
            minute = st.text_input("Committee minute reference" + (" *" if m["tier"] == 1 else " (optional)"))
            cond = st.text_area("Conditions — one per line (for 'Approved with conditions')")
            due = st.date_input("Conditions due by", value=date.today() + timedelta(days=90))
            comment = st.text_input("Comment")
            go = st.form_submit_button("Record decision", type="primary")
        if go:
            conds = [{"condition": c.strip(), "due": due.isoformat()} for c in cond.splitlines() if c.strip()]
            _act(data_store.record_approval, f"Decision recorded: {decision}.",
                 m["model_id"], decision, conds, minute, comment)

    if cur == "G5" and auth.has_permission("verify_implementation") and \
            not governance.independence_conflict(m, user["name"], "VAL"):
        with st.form(f"g5_{m['model_id']}"):
            st.markdown("**Verify implementation**")
            note = st.text_input("What was checked *", placeholder="Version, configuration, parallel run")
            go = st.form_submit_button("Verify implementation", type="primary")
        if go:
            _act(data_store.verify_implementation, "Implementation verified — model in use.", m["model_id"], note)

    # ---- approvals and conditions
    st.markdown("**Approvals**")
    approvals = m.get("approvals") or []
    if not approvals:
        st.caption("No approval decisions yet.")
    for ap in reversed(approvals):
        color = {"Approved": utils.GREEN, "Approved with conditions": utils.AMBER}.get(ap["decision"], utils.RED)
        st.markdown(
            f"{utils.badge(ap['decision'], color)} {ap['body']} · {utils.fmt_date(ap['date'])} · "
            f"v{ap.get('version')} · recorded by {ap['recorded_by']}"
            + (f" · {ap['minute_ref']}" if ap.get("minute_ref") else ""),
            unsafe_allow_html=True,
        )
        for c in ap.get("conditions", []):
            st.markdown(
                f"&nbsp;&nbsp;• {c['condition']} — {governance.person_name(c['owner'])}"
                + (f", due {utils.fmt_date(c['due'])}" if c.get("due") else "")
                + f" · *{c['status']}*" + (f" ({c['note']})" if c.get("note") else ""),
                unsafe_allow_html=True,
            )
            key = f"{ap['approval_id']}_{c['cond_id']}"
            if c["status"] == governance.CONDITION_OPEN and user["role"] == "LOD1" and (
                    governance.is_owner_or_developer(m, user["name"])
                    or governance.person_name(c.get("owner")) == user["name"]):
                with st.form(f"cm_{key}"):
                    note = st.text_input("How was it met?")
                    if st.form_submit_button("Mark as met"):
                        _act(data_store.update_condition, "Condition marked as met.",
                             m["model_id"], ap["approval_id"], c["cond_id"], "met", note)
            if c["status"] == governance.CONDITION_MET and user["role"] in ("LOD2", "CRO") \
                    and not governance.is_owner_or_developer(m, user["name"]):
                with st.form(f"cv_{key}"):
                    why = st.text_input("Comment (required to reopen)")
                    b1, b2 = st.columns(2)
                    verify = b1.form_submit_button("Verify", type="primary")
                    reopen = b2.form_submit_button("Reopen")
                if verify:
                    _act(data_store.update_condition, "Condition verified.",
                         m["model_id"], ap["approval_id"], c["cond_id"], "verify")
                if reopen:
                    _act(data_store.update_condition, "Condition reopened.",
                         m["model_id"], ap["approval_id"], c["cond_id"], "reopen", why)
    if m.get("implementation"):
        st.caption("Implementation checks: " + "; ".join(
            f"v{i['version']} by {governance.person_name(i['verified_by'])} on {utils.fmt_date(i['verified_on'])}"
            for i in m["implementation"]))

    # ---- versions
    st.markdown("**Versions**")
    if m["change_log"]:
        done_vals = sorted([r for r in model_requests if governance.counts_as_validation(r)],
                           key=lambda r: r.get("closed_date") or "")
        entries = sorted(m["change_log"], key=lambda e: e["date"])
        rows = []
        for i, e in enumerate(entries):
            nxt = entries[i + 1]["date"] if i + 1 < len(entries) else "9999-12-31"
            vals = [r for r in done_vals if e["date"] <= (r.get("closed_date") or "") < nxt]
            rows.append({
                "Version": e["version"] + (" (current)" if e["version"] == m["version"] else ""),
                "Date": utils.fmt_date(e["date"]), "Change": e["description"],
                "Materiality": e.get("classification", "—"),
                "Validated": (f"{vals[-1]['outcome']} ({utils.fmt_date(vals[-1]['closed_date'])})" if vals
                              else "not required" if e.get("classification") == "Non-material" else "no"),
            })
        st.dataframe(pd.DataFrame(list(reversed(rows))), hide_index=True, width="stretch")
    else:
        st.caption("No versions recorded yet.")

    if auth.has_permission("record_change") and governance.is_owner_or_developer(m, user["name"]):
        if st.toggle("Record a model change", key="chg_toggle"):
            st.caption("Material = methodology, key assumptions, scope of use, or a recalibration that "
                       "changes outputs materially — needs revalidation and approval before use. "
                       "Non-material = parameter refresh within approved ranges, cosmetic changes.")
            with st.form("change_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                chg_version = c1.text_input("New version *", placeholder=f"current: {m['version']}",
                                            key="chg_version")
                chg_class = c2.selectbox("Materiality *", ["Material", "Non-material"], key="chg_class")
                chg_desc = st.text_area("What changed *", key="chg_desc")
                chg_just = st.text_area("Why this materiality *", key="chg_just")
                chg_submit = st.form_submit_button("Record change", key="chg_submit")
            if chg_submit:
                if not (chg_version.strip() and chg_desc.strip() and chg_just.strip()):
                    st.error("Version, description and justification are required.")
                else:
                    _act(data_store.add_change_entry,
                         "Change recorded — a model change request is open on the Validation tab.",
                         m["model_id"], {
                             "date": date.today().isoformat(), "version": chg_version.strip(),
                             "description": chg_desc.strip(), "author": user["name"],
                             "classification": chg_class, "justification": chg_just.strip(),
                         })


# ================================================================ validation engagement
def _engagement(req: dict, m: dict) -> None:
    eng = req.get("engagement") or {}
    user = auth.get_current_user()
    rid = req["request_id"]
    stage = eng.get("stage", "Scoping")
    closed = req["status"] == "Closed"
    is_validator = user["role"] == "LOD2" and governance.person_name(req.get("assigned_to")) == user["name"]
    is_owner = governance.is_owner_or_developer(m, user["name"]) and user["role"] == "LOD1"

    steps = governance.ENGAGEMENT_STAGES
    idx = steps.index(stage) if stage in steps else 0
    st.markdown("Validation steps: " + " → ".join(
        f"**{s}**" if i == idx else (f"<span style='color:{utils.GREEN};'>{s} ✓</span>" if i < idx
                                     else f"<span style='color:#999;'>{s}</span>")
        for i, s in enumerate(steps)), unsafe_allow_html=True)
    if eng.get("scope"):
        st.markdown(f"**Scope.** {eng['scope']}")
    if eng.get("independence"):
        st.caption(f"Independence declared by {eng['independence']['declared_by']} on "
                   f"{utils.fmt_date(eng['independence']['on'])}.")

    # 1 · scoping
    if not closed and stage == "Scoping":
        if user["role"] == "LOD2" and (is_validator or not req.get("assigned_to")):
            with st.form(f"eng_scope_{rid}"):
                scope = st.text_area("Scope of the validation *")
                tests = st.multiselect("Planned tests", data_store.COMMON_TESTS)
                ind = st.checkbox("I did not develop, own or use this model and have no conflict of interest.",
                                  key=f"eng_ind_{rid}")
                go = st.form_submit_button("Start fieldwork", type="primary")
            if go:
                if not ind:
                    st.error("Tick the independence declaration.")
                else:
                    _act(data_store.start_engagement, "Fieldwork started.", rid, scope, tests)
        else:
            st.caption("Waiting for the validator to set the scope.")

    # 2 · fieldwork: information requests
    irs = eng.get("info_requests") or []
    if irs:
        st.markdown("**Information requests**")
    for ir in irs:
        late = ir["status"] == "Open" and ir.get("due") and ir["due"] < date.today().isoformat()
        st.markdown(
            f"{utils.badge(ir['status'], utils.AMBER if ir['status'] == 'Open' else utils.GREEN)}"
            + (utils.badge("Overdue", utils.RED) if late else "")
            + f" **{ir['ir_id']}** {ir['item']} — {governance.person_name(ir['owner'])}, "
              f"due {utils.fmt_date(ir.get('due'))}",
            unsafe_allow_html=True,
        )
        if ir.get("response"):
            st.caption(f"Answer from {ir.get('answered_by')} ({utils.fmt_date(ir.get('answered_on'))}): "
                       f"{ir['response']}")
        if ir.get("review_comment") and ir["status"] == "Open":
            st.caption(f"Sent back by the validator: {ir['review_comment']}")
        key = f"{rid}_{ir['ir_id']}"
        if not closed and ir["status"] == "Open" and user["role"] == "LOD1" and (
                is_owner or governance.person_name(ir["owner"]) == user["name"]):
            with st.form(f"ira_{key}", clear_on_submit=True):
                resp = st.text_input(f"Answer {ir['ir_id']}")
                f = st.file_uploader("File (optional)", type=data_store.ALLOWED_UPLOAD_TYPES, key=f"iraf_{key}")
                if st.form_submit_button("Send answer"):
                    try:
                        ev = [data_store.attach_evidence(m["model_id"], "validation_request", rid, f,
                                                         "Document", f"{ir['ir_id']}: {ir['item'][:60]}")] if f else []
                        data_store.answer_info_request(rid, ir["ir_id"], resp, ev)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        flash_and_rerun(f"{ir['ir_id']} answered.")
        if not closed and ir["status"] == "Answered" and is_validator and stage == "Fieldwork":
            with st.popover(f"Send {ir['ir_id']} back"):
                why = st.text_input("What is still missing?", key=f"irno_{key}")
                if st.button("Send back", key=f"irnob_{key}"):
                    _act(data_store.send_back_info_request, f"{ir['ir_id']} sent back.", rid, ir["ir_id"], why)

    if not closed and stage == "Fieldwork" and is_validator:
        with st.form(f"irnew_{rid}", clear_on_submit=True):
            st.markdown("**Ask for something**")
            c1, c2, c3 = st.columns([3, 2, 1.3])
            item = c1.text_input("Item")
            owners = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
            who = c2.selectbox("From", owners, index=auth.default_option_index(owners, m.get("developer")))
            due = c3.date_input("Due", value=date.today() + timedelta(days=10))
            if st.form_submit_button("Send request"):
                _act(data_store.add_info_request, "Information request sent.", rid, item, who, due.isoformat())
        reason = governance.engagement_can_issue_draft(eng)
        with st.form(f"eng_draft_{rid}"):
            st.markdown("**Draft report → owner review**")
            if reason:
                st.caption(reason)
            rating = st.selectbox("Proposed rating", governance.RATING_SCALE)
            summary = st.text_area("Conclusions")
            go = st.form_submit_button("Send draft to the owner", disabled=bool(reason))
        if go:
            _act(data_store.issue_draft, "Draft sent to the owner.", rid, rating, summary)

    # 3 · owner review
    if eng.get("draft"):
        d = eng["draft"]
        st.markdown(f"**Draft** — proposed rating {utils.rating_badge(d['rating'])} · "
                    f"{utils.fmt_date(d['issued_on'])}: {d['summary']}", unsafe_allow_html=True)
    if eng.get("owner_review"):
        o = eng["owner_review"]
        st.caption(f"Owner review by {o['by']} ({utils.fmt_date(o['on'])}): {o['comments']}")
    if not closed and stage == "Owner review" and is_owner and not eng.get("owner_review"):
        with st.form(f"eng_review_{rid}"):
            comments = st.text_area("Factual-accuracy comments (leave blank if none)")
            if st.form_submit_button("Submit review", type="primary"):
                _act(data_store.submit_owner_review, "Review submitted.", rid, comments)

    # 4 · sign-off
    if not closed and stage == "Owner review" and is_validator:
        reason = governance.engagement_can_sign_off(eng)
        with st.form(f"eng_sign_{rid}"):
            st.markdown("**Sign off**")
            if reason:
                st.caption(reason)
            rating = st.selectbox("Final rating", governance.RATING_SCALE,
                                  index=governance.RATING_SCALE.index(eng["draft"]["rating"]),
                                  help=" · ".join(f"{k}: {v}" for k, v in governance.RATING_DESCRIPTIONS.items()))
            comment = st.text_input("Comment")
            go = st.form_submit_button("Sign off validation", type="primary", disabled=bool(reason))
        if go:
            _act(data_store.sign_off, "Validation signed off.", rid, rating, comment)
    if eng.get("signed_off"):
        so = eng["signed_off"]
        st.success(f"Signed off by {so['by']} on {utils.fmt_date(so['on'])} — {so['rating']}.")


# ================================================================ page
user = auth.get_current_user()

models = load_models()
model_ids = [x["model_id"] for x in models]
labels = {x["model_id"]: f"{x['model_id']} — {x['name']}" for x in models}
if not model_ids:
    st.error("No models in the inventory.")
    st.stop()

# Deep links: /model_detail?model=<id>[&request=<rid>]
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

default_id = st.session_state.get("selected_model_id", model_ids[0])
if default_id not in model_ids:
    default_id = model_ids[0]
opts = [labels[i] for i in model_ids]
selected = model_ids[opts.index(st.selectbox("Select model", opts, index=model_ids.index(default_id)))]
st.session_state["selected_model_id"] = selected

prev = st.session_state.get("_md_req_model")
if prev is None:
    st.session_state["_md_req_model"] = selected
elif prev != selected:
    st.session_state["_md_req_model"] = selected
    st.session_state.pop("md_selected_request", None)
if qp_request:
    st.session_state["md_selected_request"] = qp_request
    utils.drop_request_query_param()

m = get_model(selected)
if m is None:
    st.error(f"Model **{selected}** was not found.")
    st.stop()

vstatus = validation_status(m)
model_requests = requests_for_model(selected)
evidence_all = load_evidence()
model_evidence = [e for e in evidence_all if e["model_id"] == selected]

if "_flash" in st.session_state:
    st.success(st.session_state.pop("_flash"))

# ---------------------------------------------------------------- header
utils.header(f"{m['model_id']} — {m['name']}", m["business_line"])
hb1, hb2 = st.columns([5, 1.2])
hb1.markdown(
    utils.tier_badge(m["tier"])
    + utils.status_badge(m["status"])
    + utils.validation_badge(f"Validation: {vstatus}")
    + (utils.rating_badge(m["last_rating"]) if m.get("last_rating") else "")
    + (utils.badge("AI system", "#6a1b9a") if m.get("ai_system") else ""),
    unsafe_allow_html=True,
)
hb2.download_button("Factsheet (PDF)", data=factsheet_pdf(selected),
                    file_name=f"{selected}_factsheet_{date.today().isoformat()}.pdf",
                    mime="application/pdf", key="dl_factsheet", width="stretch")

nxt, issues = _attention(m, vstatus, model_requests)
with st.container(border=True):
    st.markdown(f"**Next step:** {nxt}")
    for i in issues:
        st.markdown(f"<span style='color:{utils.RED};'>⚠ {i}</span>", unsafe_allow_html=True)
    if m.get("placeholder"):
        st.caption("Placeholder record — details to be confirmed by the model owner.")

tab_sum, tab_life, tab_val, tab_docs, tab_mon = st.tabs([
    "Summary", "Lifecycle & approvals", "Validation & findings", "Documents & audit", "Monitoring",
])

# ================================================================ Summary
with tab_sum:
    if _can_edit(m, user) and st.toggle("Edit this record", key="edit_toggle"):
        _edit_form(m, user)
    else:
        st.markdown(f"**Purpose.** {m['description']}")
        utils.kpi_cards([
            ("Tier", f"Tier {m['tier']}", "confirmed" if m["tier_confirmed"] else "awaiting sign-off"),
            ("Approval body", m["approval_body"], f"approved {utils.fmt_date(m.get('approval_date'), 'not yet')}"),
            ("Last validation", utils.fmt_date(m["last_validation"], "Never"), m.get("last_rating")),
            ("Next validation", utils.fmt_date(m["next_validation_due"]), m["validation_frequency"]),
            ("Exposure", f"QAR {m['exposure_covered_qar_mn']:,} mn", None),
        ])
        st.markdown(
            f"**Model owner** {m['owner']} · **Model developer** {m['developer']} · "
            f"**Model validator** {m['validator']} · **Model sponsor** {m['sponsor']} · "
            f"**Model users** {', '.join(m['model_users']) or '—'}"
        )
        if m.get("uses"):
            st.dataframe(pd.DataFrame(m["uses"]).rename(columns={
                "use": "Use", "business_area": "Business area", "decision": "Decision supported",
                "status": "Status"}), hide_index=True, width="stretch")
        with st.expander("Tier and sign-off", expanded=not m["tier_confirmed"]):
            _tier_panel(m)
        with st.expander("More details"):
            st.markdown(
                f"**Methodology** {m['methodology']}  \n"
                f"**Source** {m['source']}{' — ' + m['vendor'] if m.get('vendor') else ''} · "
                f"**Platform** {m['implementation_platform']} · **Frequency** {m['usage_frequency']} · "
                f"**Version** {m['version']} · **Category** {m['category']}  \n"
                f"**Data sources** {', '.join(m['data_sources']) or '—'}  \n"
                f"**Regulatory mapping** {', '.join(m['regulatory_mapping']) or '—'}  \n"
                f"**AI system** " + (("yes — high-risk" if m.get("qcb_ai_high_risk") else "yes")
                                     if m.get("ai_system") else "no")
            )
            a1, a2 = st.columns(2)
            a1.markdown("**Key assumptions**\n" + "\n".join(f"- {x}" for x in m["key_assumptions"]))
            a2.markdown("**Known limitations**\n" + "\n".join(f"- {x}" for x in m["known_limitations"]))
            dep = m["dependencies"]
            st.markdown(
                "**Feeds from** " + (", ".join(labels.get(d, d) for d in dep["upstream"]) or "—") + "  \n"
                "**Feeds into** " + (", ".join(labels.get(d, d) for d in dep["downstream"]) or "—")
            )

# ================================================================ Lifecycle
with tab_life:
    _lifecycle(m, model_requests)

# ================================================================ Validation & findings
with tab_val:
    open_reqs = [r for r in model_requests if r["status"] != "Closed"]
    sel = st.session_state.get("md_selected_request")
    if sel and not any(r["request_id"] == sel for r in model_requests):
        st.session_state.pop("md_selected_request", None)
        sel = None

    if sel is None:
        n_fnd = sum(1 for r in open_reqs if r["type"] == "FND")
        st.caption(f"{len(open_reqs)} open request(s), {n_fnd} open finding(s). "
                   "MC = model change · VAL = validation · FND = finding.")
        can_types = auth.initiable_types()
        if can_types and st.toggle("Start a request", key="ir_toggle"):
            labels_t = {t: f"{t} — {auth.REQUEST_TYPES[t]['label']}" for t in can_types}
            chosen = st.selectbox("Type *", list(labels_t.values()), key="ir_type")
            ir_type = next(t for t, lab in labels_t.items() if lab == chosen)
            meta = auth.REQUEST_TYPES[ir_type]
            st.caption(meta["description"])
            assignees = [auth.user_option_label(u) for u in auth.users_for_roles(*meta["default_assignee_roles"])
                         if not governance.independence_conflict(m, u["name"], ir_type)] \
                or [auth.user_option_label(user)]
            preferred = m.get("validator") if "LOD2" in meta["default_assignee_roles"] else m.get("owner")
            with st.form("initiate_request_form", clear_on_submit=True):
                ir_title = st.text_input("Title *", key="ir_title")
                ir_desc = st.text_area("Description *", key="ir_desc")
                ir_assigned = st.selectbox("Assign to *", assignees,
                                           index=auth.default_option_index(assignees, preferred), key="ir_assigned")
                ir_sub = ir_mat = ir_out = ir_sev = ir_rem = ir_due = None
                ir_tests, done_now = [], False
                if ir_type == "MC":
                    ir_mat = st.selectbox("Materiality *", data_store.MATERIALITY_OPTIONS, key="ir_materiality")
                elif ir_type == "VAL":
                    ir_sub = st.selectbox("Nature *", data_store.VAL_SUBTYPES, key="ir_subtype")
                    if user["role"] == "LOD2":
                        done_now = st.checkbox("Record a validation already completed (historic)", key="ir_close_now")
                        ir_out = st.selectbox("Rating (if completed)", data_store.VALIDATION_OUTCOMES, key="ir_outcome")
                        ir_tests = st.multiselect("Tests performed", data_store.COMMON_TESTS, key="val_tests")
                elif ir_type == "FND":
                    c_a, c_b = st.columns(2)
                    ir_sev = c_a.selectbox("Severity *", ["High", "Medium", "Low"], key="ir_sev")
                    ir_due = c_b.date_input("Fix by", value=date.today() + timedelta(days=90), key="ir_due")
                    ir_rem = st.text_area("Remediation required *", key="ir_rem")
                submit = st.form_submit_button("Create request", key="ir_submit")
            if submit:
                if not ir_title.strip() or not ir_desc.strip():
                    st.error("Title and description are required.")
                elif ir_type == "FND" and not (ir_rem or "").strip():
                    st.error("Say what remediation is required.")
                elif done_now and not ir_tests:
                    st.error("Record at least one test for a completed validation.")
                else:
                    payload = {
                        "type": ir_type, "title": ir_title.strip(), "description": ir_desc.strip(),
                        "assigned_to": ir_assigned, "status": "Closed" if done_now else "In Progress",
                        "materiality": ir_mat, "validation_subtype": ir_sub,
                        "outcome": ir_out if done_now else None,
                        "closed_date": date.today().isoformat() if done_now else None, "tests": ir_tests,
                        "severity": ir_sev, "remediation": (ir_rem or "").strip() or None,
                        "due_date": ir_due.isoformat() if ir_due else None,
                        "source": ("Validation" if user["role"] == "LOD2" and ir_type != "MC"
                                   else "Internal Audit" if user["role"] == "LOD3"
                                   else "Model Change" if ir_type == "MC" else "LoD1 Request"),
                    }
                    if done_now:
                        payload["thread"] = [{"date": date.today().isoformat(), "author": user["name"],
                                              "role": user["role"], "text": ir_desc.strip(), "evidence_ids": []}]
                    try:
                        rid_new = data_store.create_request(selected, payload)
                    except (PermissionError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        flash_and_rerun(f"Request {rid_new} created.")

        def _type_cell(r):
            t = r["type"]
            extra = r.get("materiality") if t == "MC" else r.get("validation_subtype") if t == "VAL" \
                else r.get("severity") if t == "FND" else None
            return f"{t} · {extra}" if extra else t

        reqs_sorted = sorted([r for r in model_requests if r["status"] != "Closed"],
                             key=lambda r: r.get("created_date") or "", reverse=True) + \
            sorted([r for r in model_requests if r["status"] == "Closed"],
                   key=lambda r: r.get("created_date") or "", reverse=True)
        if not reqs_sorted:
            st.info("No requests for this model yet.")
        for r in reqs_sorted:
            c1, c2, c3, c4 = st.columns([1.1, 1.5, 4, 1.4])
            if c1.button(r["request_id"], key=f"req_open_{selected}_{r['request_id']}", type="tertiary"):
                st.session_state["md_selected_request"] = r["request_id"]
                st.rerun()
            c2.markdown(f"`{_type_cell(r)}`")
            stage = (r.get("engagement") or {}).get("stage")
            c3.markdown(f"{r['title']}" + (f" <span style='color:#888;'>· {stage}</span>" if stage and
                                          r["status"] != "Closed" else ""), unsafe_allow_html=True)
            c4.caption(f"{r['status']} · {utils.fmt_date(r.get('created_date'))}")
    else:
        req = next(r for r in model_requests if r["request_id"] == sel)
        closed = req["status"] == "Closed"
        if st.button("← Back to list", key="req_back_to_list"):
            st.session_state.pop("md_selected_request", None)
            st.rerun()
        st.markdown(
            utils.badge(req["request_id"], utils.GREY)
            + utils.badge(auth.REQUEST_TYPES[req["type"]]["label"], utils.NAVY)
            + utils.badge(req["status"], {"Open": utils.AMBER, "In Progress": utils.NAVY}.get(req["status"], utils.GREEN))
            + (utils.severity_badge(req["severity"]) if req.get("severity") else "")
            + (utils.rating_badge(req["outcome"]) if req.get("outcome") in governance.RATING_SCALE else ""),
            unsafe_allow_html=True,
        )
        st.markdown(f"### {req['title']}")
        st.markdown(req.get("description") or "")
        st.caption(
            f"From {req.get('initiated_by')} · assigned to {req.get('assigned_to') or 'nobody yet'} · "
            f"opened {utils.fmt_date(req.get('created_date'))}"
            + (f" · closed {utils.fmt_date(req['closed_date'])}" if req.get("closed_date")
               else f" · due {utils.fmt_date(req['due_date'])}" if req.get("due_date") else "")
            + (f" · {req['materiality']}" if req.get("materiality") else "")
        )
        if req.get("remediation"):
            st.markdown(f"**Remediation required.** {req['remediation']}")
        if req.get("engagement"):
            with st.container(border=True):
                _engagement(req, m)

        files = _evidence_for("validation_request", req["request_id"], evidence_all)
        if files:
            st.markdown("**Files**")
            _files(files, f"req_{req['request_id']}")

        st.markdown("**Messages**")
        ev_by_id = {e["evidence_id"]: e for e in evidence_all}
        for msg in req.get("thread") or []:
            st.markdown(
                f"<div style='border-left:3px solid {utils.GOLD}; padding:6px 12px; margin:6px 0; "
                f"background:#fafafa;'><b>{msg['author']}</b> "
                f"<span style='color:#888; font-size:0.8rem;'>{utils.fmt_date(msg.get('date'))}</span>"
                f"<br>{msg.get('text', '')}</div>", unsafe_allow_html=True)
            att = [ev_by_id[e] for e in msg.get("evidence_ids") or [] if e in ev_by_id] + \
                _evidence_for("request_response", msg.get("response_id"), evidence_all)
            if att:
                _files(list({e["evidence_id"]: e for e in att}.values()), f"thr_{msg.get('response_id')}")

        if closed:
            st.caption("Closed — read-only.")
        else:
            if auth.has_permission("respond_request"):
                with st.form(f"resp_form_{req['request_id']}", clear_on_submit=True):
                    text = st.text_area("Write a message", key=f"resp_txt_{req['request_id']}")
                    f = st.file_uploader("Attach a file (optional)", type=data_store.ALLOWED_UPLOAD_TYPES,
                                         key=f"resp_ev_{req['request_id']}")
                    send = st.form_submit_button("Send")
                if send:
                    if not text.strip():
                        st.error("Write a message.")
                    else:
                        rid = data_store.peek_next_thread_id(req["request_id"])
                        try:
                            ev = [data_store.attach_evidence(selected, "request_response", rid, f, "Document",
                                                             f.name)] if f else []
                            data_store.add_request_response(req["request_id"], text.strip(), ev)
                        except (PermissionError, ValueError) as exc:
                            st.error(str(exc))
                        else:
                            flash_and_rerun("Message sent.")
            if auth.has_permission("assign_request") and st.toggle("Reassign", key=f"ra_{req['request_id']}"):
                roles = auth.REQUEST_TYPES[req["type"]]["default_assignee_roles"]
                opts_a = [auth.user_option_label(u) for u in auth.users_for_roles(*roles)
                          if not governance.independence_conflict(m, u["name"], req["type"])]
                with st.form(f"assign_form_{req['request_id']}"):
                    who = st.selectbox("Assign to", opts_a,
                                       index=auth.default_option_index(opts_a, req.get("assigned_to")))
                    if st.form_submit_button("Reassign"):
                        _act(data_store.assign_request, f"Assigned to {who}.", req["request_id"], who)
            if not req.get("engagement") and auth.can_close_request(req):
                with st.form(f"close_form_{req['request_id']}"):
                    comment = st.text_input("Closure comment *", key=f"close_txt_{req['request_id']}")
                    go = st.form_submit_button("Close request", type="primary")
                if go:
                    if not comment.strip():
                        st.error("A closure comment is required.")
                    else:
                        _act(data_store.close_request, f"{req['request_id']} closed.", req["request_id"],
                             comment.strip())

# ================================================================ Documents & audit
with tab_docs:
    docs = documentation_status(m, evidence_all)
    done = sum(docs.values())
    st.progress(done / len(docs), text=f"Documentation: {done} of {len(docs)} required documents in place")
    st.markdown(" · ".join(f"{'✅' if ok else '❌'} {d}" for d, ok in docs.items()))
    if auth.has_permission("upload_evidence") and st.toggle("Upload a document", key="md_doc_toggle"):
        with st.form("model_doc_form", clear_on_submit=True):
            up = st.file_uploader("File *", type=data_store.ALLOWED_UPLOAD_TYPES, key="md_doc_file")
            c1, c2 = st.columns(2)
            dtype = c1.selectbox("Document type *", list(m["documentation"]) + [data_store.OTHER_DOC_TYPE],
                                 key="md_doc_type")
            desc = c2.text_input("Short description *", key="md_doc_desc")
            go = st.form_submit_button("Upload")
        if go:
            if up is None or not desc.strip():
                st.error("Choose a file and describe it.")
            else:
                _act(data_store.attach_evidence, "Document uploaded.", selected, "model", selected, up,
                     "Document", desc.strip(), doc_type=dtype)
    model_docs = [e for e in model_evidence if e.get("linked_type") == "model"]
    if model_docs:
        _files(model_docs, "modeldoc")
    with st.expander(f"All files for this model ({len(model_evidence)}) — with fingerprint check"):
        if model_evidence:
            st.dataframe(pd.DataFrame([{
                "File": e["filename"], "Linked to": f"{e['linked_type']} {e['linked_id']}",
                "Type": e.get("doc_type") or e["category"], "Uploaded": utils.fmt_date(e["uploaded_at"]),
                "By": e["uploaded_by"], "Check": INTEGRITY_LABEL[data_store.read_evidence(e)[1]],
            } for e in sorted(model_evidence, key=lambda x: x["uploaded_at"], reverse=True)]),
                hide_index=True, width="stretch")
        else:
            st.caption("No files yet.")

    st.markdown("**Internal audit reviews**")
    if m["audit_reviews"]:
        for a in sorted(m["audit_reviews"], key=lambda r: r["date"], reverse=True):
            st.markdown(f"- {utils.fmt_date(a['date'])} — **{a['rating']}** — {a['scope']} "
                        f"<span style='color:#888;'>({a['auditor']})</span>", unsafe_allow_html=True)
    else:
        st.caption("None recorded.")
    if auth.has_permission("record_audit") and st.toggle("Record an internal audit review", key="aud_toggle"):
        with st.form("audit_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            aud_date = c1.date_input("Review date", value=date.today(), key="aud_date")
            aud_rating = c2.selectbox("Rating *", ["Satisfactory", "Needs Improvement", "Unsatisfactory"])
            aud_scope = st.text_area("Scope *", key="aud_scope")
            go = st.form_submit_button("Record review", key="aud_submit")
        if go:
            if not aud_scope.strip():
                st.error("Describe the scope.")
            else:
                _act(data_store.add_audit_review, "Audit review recorded.", selected, {
                    "date": aud_date.isoformat(), "auditor": auth.user_option_label(user),
                    "rating": aud_rating, "scope": aud_scope.strip()})

    st.markdown("**Audit trail**")
    chain_ok, broken_at = repository.verify_audit_chain()
    st.caption("Append-only and tamper-evident: integrity check passed." if chain_ok
               else f"Integrity check FAILED at event #{broken_at} — the log was changed outside the platform.")
    trail = [e for e in load_audit_log() if e["model_id"] == selected]
    if trail:
        tr = pd.DataFrame(sorted(trail, key=lambda e: e["seq"], reverse=True))
        tr = tr.rename(columns={"timestamp": "When", "user": "Who", "action": "Action",
                                "entity_id": "Record", "details": "Details"})
        st.dataframe(tr[["When", "Who", "Action", "Record", "Details"]], hide_index=True, width="stretch",
                     height=280)

# ================================================================ Monitoring
with tab_mon:
    mon = load_monitoring()
    mon = mon[mon["model_id"] == selected]
    if mon.empty:
        st.info("No quantitative monitoring for this model (in development, or qualitative).")
    else:
        latest = mon[mon["period"] == mon["period"].max()]
        st.markdown(" · ".join(
            f"**{r['metric']}** {r['value']:g} "
            + utils.badge(r["rag"], {"Green": utils.GREEN, "Amber": utils.AMBER, "Red": utils.RED}[r["rag"]])
            for _, r in latest.iterrows()), unsafe_allow_html=True)
        for metric, series in mon.groupby("metric"):
            series = series.sort_values("period")
            fig = pgo.Figure(pgo.Scatter(x=series["period"], y=series["value"], mode="lines+markers",
                                       line=dict(color=utils.NAVY, width=3), name=metric))
            fig.add_hline(y=series["amber_threshold"].iloc[0], line_dash="dash", line_color=utils.AMBER,
                          annotation_text="Amber")
            fig.add_hline(y=series["red_threshold"].iloc[0], line_dash="dash", line_color=utils.RED,
                          annotation_text="Red")
            fig.update_layout(title=metric, height=260, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, width="stretch")
