from datetime import date

import pandas as pd
import plotly.express as px

import streamlit as st
import utils
from data_loader import load_issues, models_dataframe

utils.header(
    "Executive Dashboard",
    f"Model risk profile at a glance — as of {date.today().strftime('%d %B %Y')}",
)

df = models_dataframe()
issues = load_issues()
open_issues = issues[issues["status"] != "Closed"]

# ---------------------------------------------------------------- KPI row
total = len(df)
in_prod = df["Status"].str.startswith("In Production").sum()
overdue_val = (df["Validation Status"].isin(["Overdue", "Never Validated"])).sum()
validated_on_time = total - overdue_val
high_open = int((open_issues["severity"] == "High").sum())
overdue_findings = int((open_issues["status"] == "Overdue").sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Models in Inventory", total)
c2.metric("In Production", int(in_prod))
c3.metric("Validation On Track", f"{validated_on_time / total:.0%}")
c4.metric("Overdue / Never Validated", int(overdue_val), delta="requires action" if overdue_val else None, delta_color="inverse")
c5.metric("Open High Findings", high_open, delta="requires action" if high_open else None, delta_color="inverse")
c6.metric("Overdue Findings", overdue_findings, delta="past due date" if overdue_findings else None, delta_color="inverse")

st.markdown("")

# ---------------------------------------------------------------- charts row
col_a, col_b, col_c = st.columns([1.2, 1, 1.2])

with col_a:
    st.subheader("Models by Risk Type")
    by_type = df.groupby("Risk Type").size().reset_index(name="Models")
    fig = px.bar(
        by_type.sort_values("Models"),
        x="Models", y="Risk Type", orientation="h", text="Models",
        color="Risk Type", color_discrete_map=utils.RISK_TYPE_COLORS,
    )
    fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=10, t=10, b=10), yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

with col_b:
    st.subheader("Models by Tier")
    by_tier = df.groupby("Tier").size().reset_index(name="Models")
    by_tier["Tier"] = "Tier " + by_tier["Tier"].astype(str)
    fig = px.pie(
        by_tier, values="Models", names="Tier", hole=0.55,
        color="Tier",
        color_discrete_map={"Tier 1": utils.RED, "Tier 2": utils.AMBER, "Tier 3": utils.GREEN},
    )
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")

with col_c:
    st.subheader("Validation Status by Tier")
    order = ["On Track", "Due Soon", "Overdue", "Never Validated"]
    heat = df.groupby(["Tier", "Validation Status"]).size().reset_index(name="Models")
    heat["Tier"] = "Tier " + heat["Tier"].astype(str)
    fig = px.bar(
        heat, x="Tier", y="Models", color="Validation Status", text="Models",
        category_orders={"Validation Status": order, "Tier": ["Tier 1", "Tier 2", "Tier 3"]},
        color_discrete_map=utils.VALIDATION_STATUS_COLORS,
    )
    fig.update_layout(height=300, margin=dict(l=0, r=10, t=10, b=10), xaxis_title=None,
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- attention required
st.subheader("Attention Required")
st.caption("Models with overdue or missing validations, high-severity open findings, or non-standard status.")

attention = df[
    df["Validation Status"].isin(["Overdue", "Never Validated"])
    | (df["High Open Issues"] > 0)
    | df["Status"].isin(["Under Remediation", "In Production - Approval Pending"])
].copy()
attention = attention.sort_values(["High Open Issues", "Overdue Issues"], ascending=False)

if attention.empty:
    st.success("No models currently require escalation.")
else:
    for _, row in attention.iterrows():
        reasons = []
        if row["Validation Status"] in ("Overdue", "Never Validated"):
            reasons.append(f"validation {row['Validation Status'].lower()}")
        if row["High Open Issues"]:
            reasons.append(f"{row['High Open Issues']} high-severity open finding(s)")
        if row["Overdue Issues"]:
            reasons.append(f"{row['Overdue Issues']} overdue finding(s)")
        if row["Status"] in ("Under Remediation", "In Production - Approval Pending"):
            reasons.append(row["Status"].lower())

        left, mid, right = st.columns([3.2, 4.5, 1.1])
        with left:
            st.markdown(
                f"**{row['Model ID']} — {row['Model Name']}**<br>"
                + utils.tier_badge(row["Tier"]) + utils.status_badge(row["Status"]),
                unsafe_allow_html=True,
            )
        with mid:
            st.markdown(
                f"<span style='color:{utils.RED}; font-weight:600;'>⚠ {'; '.join(reasons)}</span><br>"
                f"<span style='color:#666; font-size:0.85rem;'>Owner: {row['Owner']}</span>",
                unsafe_allow_html=True,
            )
        with right:
            if st.button("Open", key=f"open_{row['Model ID']}", width="stretch"):
                utils.go_to_model(row["Model ID"])
        st.divider()

# ---------------------------------------------------------------- bottom row
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("Upcoming Validation Calendar")
    cal = df[df["Next Validation Due"] != "-"][
        ["Model ID", "Model Name", "Tier", "Next Validation Due", "Validation Status"]
    ].copy()
    cal["Next Validation Due"] = pd.to_datetime(cal["Next Validation Due"])
    cal = cal.sort_values("Next Validation Due").head(10)
    cal["Next Validation Due"] = cal["Next Validation Due"].dt.strftime("%d %b %Y")
    st.dataframe(
        cal,
        hide_index=True,
        width="stretch",
        column_config={"Tier": st.column_config.NumberColumn(width="small")},
    )

with col_r:
    st.subheader("Open Findings by Severity & Source")
    sev_src = (
        open_issues.groupby(["source", "severity"]).size().reset_index(name="Findings")
    )
    fig = px.bar(
        sev_src, x="source", y="Findings", color="severity", text="Findings",
        category_orders={"severity": ["High", "Medium", "Low"]},
        color_discrete_map=utils.SEVERITY_COLORS,
        labels={"source": "Finding Source", "severity": "Severity"},
    )
    fig.update_layout(height=330, margin=dict(l=0, r=10, t=10, b=10), xaxis_title=None,
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, width="stretch")
