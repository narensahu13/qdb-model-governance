"""My Tasks: everything waiting on the acting user, across all models."""

import pandas as pd
import streamlit as st

import auth
import utils
from data_loader import tasks_for

user = auth.get_current_user()
utils.header(
    "My Tasks",
    f"What is waiting on {user['name']} ({auth.ROLE_LABELS[user['role']]}) — "
    "information requests, reviews, sign-offs, approvals, conditions and KMPI returns.",
)

tasks = tasks_for(user)
overdue = sum(t["overdue"] for t in tasks)
kinds = pd.Series([t["kind"] for t in tasks]).value_counts() if tasks else pd.Series(dtype=int)
utils.kpi_cards([
    ("Open tasks", str(len(tasks)), None),
    ("Overdue", str(overdue),
     f"<span style='color:{utils.RED}; font-weight:600;'>past due date</span>" if overdue else "none"),
    ("Most common", kinds.index[0] if len(kinds) else "—", f"{int(kinds.iloc[0])} task(s)" if len(kinds) else None),
])

if not tasks:
    st.success("Nothing is waiting on you.")
    st.stop()

kind_f = st.multiselect("Show", sorted(kinds.index))
for i, t in enumerate(tasks):
    if kind_f and t["kind"] not in kind_f:
        continue
    left, mid, right = st.columns([3.4, 4.4, 1.1])
    with left:
        st.markdown(
            f"**{t['title']}**<br>"
            + utils.badge(t["kind"], utils.NAVY)
            + (utils.badge("Overdue", utils.RED) if t["overdue"] else ""),
            unsafe_allow_html=True,
        )
    with mid:
        info = " · ".join(x for x in (t["detail"], f"due {utils.fmt_date(t['due'])}" if t["due"] else "") if x)
        st.markdown(
            f"<span style='font-size:0.88rem;'>{t['model_id']} — {t['model_name']}</span><br>"
            f"<span style='color:#666; font-size:0.82rem;'>{info}</span>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("Open", key=f"task_{i}_{t['model_id']}", width="stretch"):
            utils.go_to_model(t["model_id"], request_id=t.get("request_id"))
    st.divider()
