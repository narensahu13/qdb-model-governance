"""Administration (MRM Administrator): people, accountability, model IDs, database."""

from datetime import datetime

import pandas as pd
import streamlit as st

import auth
import config
import data_store
import governance
import repository
import utils
from data_loader import load_models

utils.header(
    "Administration",
    "People and roles, who is accountable for each model, model numbering and the database. "
    "Every change is in the audit log.",
)

if not auth.has_permission("administer"):
    auth.permission_denied("administer")
    st.stop()

if "_admin_flash" in st.session_state:
    st.success(st.session_state.pop("_admin_flash"))


def done(msg: str):
    st.session_state["_admin_flash"] = msg
    st.rerun()


tab_people, tab_acc, tab_ids, tab_db = st.tabs(
    ["People and roles", "Model accountability", "Model IDs", "Database"])

# ---------------------------------------------------------------- people
with tab_people:
    users = auth.load_users()
    st.caption(
        "Rename the placeholder people (Model Developer 1, Model Validator 1 ...) to real names when ready. "
        "A rename is carried into every model, request and file record; the audit log keeps the "
        "names as they were at the time."
    )
    st.dataframe(pd.DataFrame([{"Name": u["name"], "Title": u["title"],
                                "Role": auth.ROLE_LABELS.get(u["role"], u["role"])} for u in users]),
                 hide_index=True, width="stretch")
    roles = list(auth.ROLE_LABELS)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Edit a person**")
        pick = st.selectbox("Person", [u["name"] for u in users], key="adm_pick")
        cur = next(u for u in users if u["name"] == pick)
        with st.form("adm_edit_user"):
            new_name = st.text_input("Name", cur["name"])
            new_title = st.text_input("Title", cur["title"])
            new_role = st.selectbox("Role", roles, index=roles.index(cur["role"]),
                                    format_func=lambda r: auth.ROLE_LABELS[r])
            go = st.form_submit_button("Save", type="primary")
        if go:
            try:
                n = data_store.save_user(pick, new_name, new_title, new_role)
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            else:
                done(f"Saved {new_name}; {n} record(s) updated.")
    with c2:
        st.markdown("**Add a person**")
        with st.form("adm_add_user", clear_on_submit=True):
            a_name = st.text_input("Name")
            a_title = st.text_input("Title")
            a_role = st.selectbox("Role", roles, format_func=lambda r: auth.ROLE_LABELS[r])
            add = st.form_submit_button("Add")
        if add:
            try:
                data_store.save_user(None, a_name, a_title, a_role)
            except (PermissionError, ValueError) as exc:
                st.error(str(exc))
            else:
                done(f"Added {a_name.strip()}.")

# ---------------------------------------------------------------- accountability
with tab_acc:
    st.caption(
        "Set the owner, developer, validator and sponsor of every model in one place. Validators "
        "cannot be assigned to models they own or develop."
    )
    models = load_models()
    owners = [auth.user_option_label(u) for u in auth.users_for_roles("LOD1")]
    validators = ["Not yet assigned"] + [auth.user_option_label(u) for u in auth.users_for_roles("LOD2")]
    base = pd.DataFrame([{
        "Model ID": m["model_id"], "Model": m["name"], "Owner": m["owner"],
        "Developer": m["developer"], "Validator": m["validator"], "Sponsor": m["sponsor"],
    } for m in models])
    edited = st.data_editor(
        base, hide_index=True, width="stretch", disabled=["Model ID", "Model"], key="adm_acc",
        height=38 * (len(base) + 1) + 4,
        column_config={
            "Owner": st.column_config.SelectboxColumn(options=sorted(set(owners) | set(base["Owner"]))),
            "Validator": st.column_config.SelectboxColumn(options=sorted(set(validators) | set(base["Validator"]))),
        },
    )
    if st.button("Save accountability changes", type="primary", key="adm_acc_save"):
        msgs, errs = [], []
        for (_, old), (_, new) in zip(base.iterrows(), edited.iterrows()):
            changes = {f.lower(): new[f] for f in ("Owner", "Developer", "Validator", "Sponsor")
                       if new[f] != old[f]}
            if not changes:
                continue
            try:
                data_store.update_model(new["Model ID"], changes)
                msgs.append(new["Model ID"])
            except (PermissionError, ValueError) as exc:
                errs.append(f"{new['Model ID']}: {exc}")
        for e in errs:
            st.error(e)
        if msgs and not errs:
            done(f"Updated {', '.join(msgs)}.")
        elif not msgs and not errs:
            st.info("No changes to save.")

# ---------------------------------------------------------------- model IDs
with tab_ids:
    st.caption(
        "Model IDs are numeric (QDB-001, QDB-002 ...). Renumbering updates every reference — "
        "dependencies, requests, evidence and registers. The audit log keeps the old ID."
    )
    models = load_models()
    labels = {m["model_id"]: f"{m['model_id']} — {m['name']}" for m in models}
    with st.form("adm_rename_id"):
        old = st.selectbox("Model", list(labels), format_func=lambda i: labels[i])
        new = st.text_input("New ID", placeholder="QDB-101")
        go = st.form_submit_button("Change ID", type="primary")
    if go:
        try:
            data_store.rename_model_id(old, new)
        except (PermissionError, ValueError) as exc:
            st.error(str(exc))
        else:
            if st.session_state.get("selected_model_id") == old:
                st.session_state["selected_model_id"] = new.strip().upper()
            done(f"{old} is now {new.strip().upper()}.")

# ---------------------------------------------------------------- database
with tab_db:
    ok, broken = repository.verify_audit_chain()
    counts = {
        "Models": len(repository.list_models()), "Requests": len(repository.list_requests()),
        "Evidence files": len(repository.list_evidence()), "Tools": len(repository.list_tools()),
        "Audit events": len(repository.list_audit()),
    }
    utils.kpi_cards([(k, str(v), None) for k, v in counts.items()] + [
        ("Audit chain", "Intact" if ok else f"Broken at #{broken}", None)])
    st.caption(f"Database: `{config.db_path()}` · evidence folder: `{config.evidence_dir()}`")
    st.download_button(
        "Download database backup", repository.db_bytes(),
        f"qdb_mrm_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
        "application/octet-stream", key="adm_backup",
    )
    st.caption("The backup is a complete copy of the database (not the evidence files). "
               f"Statuses in use: {', '.join(governance.MODEL_STATUSES)}.")
