from datetime import date

import pandas as pd
import plotly.express as px

import streamlit as st
import utils
from data_loader import load_issues, load_models, load_validation_requests


utils.header(
    "Findings & Remediation Tracker",
    "Bank-wide view of open findings (FND) and related open Model Change / Validation "
    "requests. Detail and actions live on each model's Validation & Findings tab.",
)

models = load_models()
model_names = {m["model_id"]: m["name"] for m in models}
model_tiers = {m["model_id"]: m["tier"] for m in models}

# Primary register: FND
issues = load_issues()
issues["Model"] = issues["model_id"].map(lambda x: f"{x} — {model_names.get(x, x)}")
issues["Tier"] = issues["model_id"].map(lambda x: model_tiers.get(x, "—"))

# Also surface other open workflow requests (MC, VAL)
other_open = []
for r in load_validation_requests():
    if r["type"] == "FND":
        continue
    if r["status"] == "Closed":
        continue
    other_open.append({
        "request_id": r["request_id"],
        "type": r["type"],
        "model_id": r["model_id"],
        "Model": f"{r['model_id']} — {model_names.get(r['model_id'], r['model_id'])}",
        "title": r["title"],
        "status": r["status"],
        "assigned_to": r.get("assigned_to") or "",
        "initiated_by": r.get("initiated_by") or "",
        "created_date": r.get("created_date"),
        "materiality": r.get("materiality") or "",
    })

open_issues = issues[issues["status"] != "Closed"]

# ---------------------------------------------------------------- KPIs
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Findings (FND)", len(issues))
c2.metric("Open FND", len(open_issues))
c3.metric("High Severity Open", int((open_issues["severity"] == "High").sum()))
c4.metric("Overdue FND", int((open_issues["status"] == "Overdue").sum()))
c5.metric("Other open requests", len(other_open))

st.markdown("")

# ---------------------------------------------------------------- filters
f1, f2, f3, f4 = st.columns(4)
with f1:
    sev_f = st.multiselect("Severity", ["High", "Medium", "Low"])
with f2:
    status_f = st.multiselect("Status", ["Open", "Overdue", "Closed"])
with f3:
    source_f = st.multiselect("Source", sorted(issues["source"].dropna().unique()) if not issues.empty else [])
with f4:
    model_f = st.multiselect("Model", sorted(issues["Model"].unique()) if not issues.empty else [])

filtered = issues.copy()
if sev_f:
    filtered = filtered[filtered["severity"].isin(sev_f)]
if status_f:
    filtered = filtered[filtered["status"].isin(status_f)]
if source_f:
    filtered = filtered[filtered["source"].isin(source_f)]
if model_f:
    filtered = filtered[filtered["Model"].isin(model_f)]

# ---------------------------------------------------------------- aging chart
col_l, col_r = st.columns([1.3, 1])

with col_l:
    st.subheader("Open Findings Aging")
    today = pd.Timestamp(date.today())
    aging = open_issues.copy()
    if aging.empty:
        st.caption("No open findings.")
    else:
        aging["Age (days)"] = (today - aging["raised_date"]).dt.days
        bins = [0, 90, 180, 365, 10_000]
        labels = ["< 90 days", "90-180 days", "180-365 days", "> 1 year"]
        aging["Age Bucket"] = pd.cut(aging["Age (days)"], bins=bins, labels=labels)
        agg = aging.groupby(["Age Bucket", "severity"], observed=True).size().reset_index(name="Findings")
        fig = px.bar(
            agg, x="Age Bucket", y="Findings", color="severity", text="Findings",
            category_orders={"severity": ["High", "Medium", "Low"], "Age Bucket": labels},
            color_discrete_map=utils.SEVERITY_COLORS, labels={"severity": "Severity"},
        )
        fig.update_layout(height=320, margin=dict(l=0, r=10, t=10, b=10), xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

with col_r:
    st.subheader("Open Findings by Owner")
    if open_issues.empty:
        st.caption("No open findings.")
    else:
        by_owner = open_issues.groupby("owner").size().reset_index(name="Findings")
        by_owner["owner"] = by_owner["owner"].str.replace(r" \(.*\)", "", regex=True)
        fig = px.bar(
            by_owner.sort_values("Findings"), x="Findings", y="owner", orientation="h", text="Findings",
        )
        fig.update_traces(marker_color=utils.NAVY)
        fig.update_layout(height=320, margin=dict(l=0, r=10, t=10, b=10), yaxis_title=None)
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- FND table
st.subheader(f"Findings Register — FND ({len(filtered)} shown)")

severity_order = {"High": 0, "Medium": 1, "Low": 2}
status_order = {"Overdue": 0, "Open": 1, "Closed": 2}
if not filtered.empty:
    filtered = filtered.sort_values(
        by=["status", "severity", "due_date"],
        key=lambda s: s.map(status_order) if s.name == "status" else (
            s.map(severity_order) if s.name == "severity" else s
        ),
    )

for _, iss in filtered.iterrows():
    status_color = {"Open": utils.AMBER, "Overdue": utils.RED, "Closed": utils.GREEN}.get(
        iss["status"], utils.GREY
    )
    rid = iss["issue_id"]
    left, mid, right = st.columns([4.2, 4, 1])
    with left:
        id_col, title_col = st.columns([1.15, 3.2])
        with id_col:
            if st.button(rid, key=f"fnd_id_{rid}", type="tertiary", width="stretch"):
                utils.go_to_model(iss["model_id"], request_id=rid)
        with title_col:
            st.markdown(
                f"**{iss['title']}**<br>"
                + utils.severity_badge(iss["severity"])
                + utils.badge(iss["status"], status_color)
                + utils.badge(iss["source"], utils.GREY),
                unsafe_allow_html=True,
            )
    with mid:
        due = iss["due_date"].strftime("%d %b %Y") if pd.notna(iss["due_date"]) else "-"
        st.markdown(
            f"<span style='font-size:0.88rem;'>{iss['Model']}</span><br>"
            f"<span style='color:#666; font-size:0.82rem;'>Owner: {iss['owner']} · Due: {due}</span>",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("Open", key=f"goto_{rid}", width="stretch"):
            utils.go_to_model(iss["model_id"], request_id=rid)
    with st.expander("Details"):
        st.markdown(f"**Finding.** {iss['description']}")
        st.markdown(f"**Remediation.** {iss['remediation']}")
        n_resp = len(iss["responses"]) if isinstance(iss.get("responses"), list) else 0
        st.caption(
            f"Raised by {iss.get('raised_by', '-')} ({iss.get('raised_by_role', '-')}) · "
            f"{n_resp} response(s) — full thread on the model's **Validation & Findings** tab."
        )
    st.divider()

# ---------------------------------------------------------------- other open requests
st.subheader(f"Other open requests — MC / VAL ({len(other_open)})")
st.caption("Model Change and Validation requests that are still Open or In Progress.")
if not other_open:
    st.success("No other open validation requests.")
else:
    for row in other_open:
        rid = row["request_id"]
        left, mid, right = st.columns([4.2, 4, 1])
        with left:
            id_col, title_col = st.columns([1.15, 3.2])
            with id_col:
                if st.button(rid, key=f"req_id_{rid}", type="tertiary", width="stretch"):
                    utils.go_to_model(row["model_id"], request_id=rid)
            with title_col:
                badges = utils.badge(row["type"], utils.NAVY) + utils.badge(
                    row["status"], utils.AMBER
                )
                if row.get("materiality"):
                    badges += utils.badge(row["materiality"], utils.GREY)
                st.markdown(
                    f"**{row['title']}**<br>" + badges,
                    unsafe_allow_html=True,
                )
        with mid:
            st.markdown(
                f"<span style='font-size:0.88rem;'>{row['Model']}</span><br>"
                f"<span style='color:#666; font-size:0.82rem;'>"
                f"Assigned: {row['assigned_to']} · From: {row['initiated_by']}</span>",
                unsafe_allow_html=True,
            )
        with right:
            if st.button("Open", key=f"goto_req_{rid}", width="stretch"):
                utils.go_to_model(row["model_id"], request_id=rid)
        st.divider()
