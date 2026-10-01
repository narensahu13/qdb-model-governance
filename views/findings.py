"""Findings Tracker — every open finding and open validation work, bank-wide."""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import utils
from data_loader import load_issues, load_models, load_validation_requests

utils.header(
    "Findings Tracker",
    "Open findings across all models, and validation work still in progress. "
    "Select a row to open it on the model's page.",
)

models = {m["model_id"]: m for m in load_models()}
issues = load_issues()
open_issues = issues[issues["status"] != "Closed"]

utils.kpi_cards([
    ("Open findings", str(len(open_issues)), None),
    ("High severity", str(int((open_issues["severity"] == "High").sum())), None),
    ("Past due date", str(int((open_issues["status"] == "Overdue").sum())), None),
    ("Closed", str(int((issues["status"] == "Closed").sum())), None),
])

c1, c2 = st.columns(2)
sev_f = c1.multiselect("Severity", ["High", "Medium", "Low"])
show_closed = c2.toggle("Include closed findings")

table = issues if show_closed else open_issues
if sev_f:
    table = table[table["severity"].isin(sev_f)]
sev_order = {"High": 0, "Medium": 1, "Low": 2}
status_order = {"Overdue": 0, "Open": 1, "Closed": 2}
table = table.assign(_s=table["status"].map(status_order), _v=table["severity"].map(sev_order)) \
    .sort_values(["_s", "_v", "due_date"])

view = pd.DataFrame({
    "ID": table["issue_id"],
    "Model": table["model_id"].map(lambda i: f"{i} — {models[i]['name']}" if i in models else i),
    "Finding": table["title"],
    "Severity": table["severity"],
    "Status": table["status"],
    "Owner": table["owner"].str.replace(r" \(.*\)", "", regex=True),
    "Due": table["due_date"].map(lambda d: utils.fmt_date(d.isoformat()) if pd.notna(d) else "—"),
    "Raised by": table["source"],
})
event = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun",
                     selection_mode="single-row", key="fnd_table")
if event.selection and event.selection.rows:
    row = table.iloc[event.selection.rows[0]]
    utils.go_to_model(row["model_id"], request_id=row["issue_id"])

if not open_issues.empty:
    today = pd.Timestamp(date.today())
    aging = open_issues.assign(age=(today - open_issues["raised_date"]).dt.days)
    labels = ["< 90 days", "90–180 days", "180–365 days", "> 1 year"]
    aging["Age"] = pd.cut(aging["age"], [0, 90, 180, 365, 100_000], labels=labels)
    agg = aging.groupby(["Age", "severity"], observed=True).size().reset_index(name="Findings")
    fig = px.bar(agg, x="Age", y="Findings", color="severity", text="Findings",
                 category_orders={"severity": ["High", "Medium", "Low"], "Age": labels},
                 color_discrete_map=utils.SEVERITY_COLORS, labels={"severity": "Severity"},
                 title="How long open findings have been open")
    fig.update_layout(height=300, margin=dict(l=0, r=10, t=40, b=10), xaxis_title=None)
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- validation work in progress
st.subheader("Validation work in progress")
rows = []
for r in load_validation_requests():
    if r["type"] == "FND" or r["status"] == "Closed":
        continue
    rows.append({
        "ID": r["request_id"], "model_id": r["model_id"],
        "Model": f"{r['model_id']} — {models[r['model_id']]['name']}" if r["model_id"] in models else r["model_id"],
        "What": r["title"], "Step": (r.get("engagement") or {}).get("stage") or r["status"],
        "With": (r.get("assigned_to") or "unassigned").split(" (")[0],
        "Opened": utils.fmt_date(r.get("created_date")),
    })
if not rows:
    st.caption("None.")
else:
    wip = pd.DataFrame(rows)
    ev2 = st.dataframe(wip.drop(columns=["model_id"]), hide_index=True, width="stretch",
                       on_select="rerun", selection_mode="single-row", key="wip_table")
    if ev2.selection and ev2.selection.rows:
        row = wip.iloc[ev2.selection.rows[0]]
        utils.go_to_model(row["model_id"], request_id=row["ID"])
