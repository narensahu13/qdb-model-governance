from datetime import date

import pandas as pd
import plotly.express as px

import streamlit as st
import governance
import utils
import kmpi as kmpi_rules
from data_loader import kmpi_overview, load_issues, models_dataframe

utils.header(
    "Dashboard",
    f"Model risk profile at a glance — as of {date.today().strftime('%d %B %Y')}",
)

import auth  # noqa: E402
from data_loader import tasks_for  # noqa: E402

_my_tasks = tasks_for(auth.get_current_user())
if _my_tasks:
    _late = sum(t["overdue"] for t in _my_tasks)
    c_t1, c_t2 = st.columns([5, 1.2])
    c_t1.info(f"You have **{len(_my_tasks)} task(s)** waiting"
              + (f", **{_late} overdue**" if _late else "") + ".")
    if c_t2.button("Open My Tasks", key="dash_tasks", width="stretch"):
        st.switch_page("views/tasks.py")

df = models_dataframe()
issues = load_issues()
open_issues = issues[issues["status"] != "Closed"]

# ---------------------------------------------------------------- KPI row
IN_USE = sorted(governance.IN_USE_STATUSES)
total = len(df)
in_use = df["Status"].isin(IN_USE).sum()
in_scope = df[df["Validation Status"] != "Pre-implementation"]
overdue_val = (in_scope["Validation Status"].isin(["Overdue", "Never Validated"])).sum()
on_track_share = (len(in_scope) - overdue_val) / len(in_scope) if len(in_scope) else 1.0
high_open = int((open_issues["severity"] == "High").sum())
overdue_findings = int((open_issues["status"] == "Overdue").sum())

_period = kmpi_rules.reporting_period()
_k_rows = kmpi_overview(_period)
_k_done = sum(r["status"] in kmpi_rules.DONE for r in _k_rows)
_k_late = sum(r["overdue"] for r in _k_rows)
_k_red = sum(r["red"] for r in _k_rows)


def _alert(n: int, text: str) -> str | None:
    return f"<span style='color:{utils.RED}; font-weight:600;'>{text}</span>" if n else "none"


utils.kpi_cards([
    ("Models in inventory", str(total),
     f"{int(in_use)} in use · {int((df['AI System']).sum())} AI system(s)"),
    (f"KMPI returns {_period}", f"{_k_done} of {len(_k_rows)}",
     _alert(_k_late, f"{_k_late} overdue") if _k_late else f"submitted · {_k_red} red KMPI(s)"),
    ("Validations on schedule", f"{on_track_share:.0%}", "of models in use"),
    ("Overdue validations", str(int(overdue_val)), _alert(overdue_val, "requires action")),
    ("Open high findings", str(high_open), _alert(high_open, "requires action")),
    ("Overdue findings", str(overdue_findings), _alert(overdue_findings, "past due date")),
])

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
    order = ["On Track", "Due Soon", "Overdue", "Never Validated", "Pre-implementation"]
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
st.caption("Models with overdue or missing validations, high-severity open findings, a red KMPI, "
           "or a status needing escalation.")

attention = df[
    df["Validation Status"].isin(["Overdue", "Never Validated"])
    | (df["High Open Issues"] > 0)
    | df["Status"].isin(["Under Remediation", "Restricted Use", "In Production - Approval Pending"])
    | ~df["Tier Confirmed"]
    | df["Status"].isin([governance.STATUS_AWAITING_APPROVAL, governance.STATUS_AWAITING_IMPLEMENTATION])
    | (df["Latest KMPI"] == "Red")
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
        if row["Status"] in ("Under Remediation", "Restricted Use", "In Production - Approval Pending"):
            reasons.append(row["Status"].lower())
        if not row["Tier Confirmed"]:
            reasons.append("tier awaiting sign-off")
        if row["Status"] == governance.STATUS_AWAITING_APPROVAL:
            reasons.append("awaiting approval (G4)")
        if row["Status"] == governance.STATUS_AWAITING_IMPLEMENTATION:
            reasons.append("awaiting implementation check (G5)")
        if row["Latest KMPI"] == "Red":
            reasons.append("red KMPI in the latest return")

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
        ["Model ID", "Model Name", "Tier", "Last Rating", "Next Validation Due", "Validation Status"]
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
