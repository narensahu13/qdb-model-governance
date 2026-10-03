"""KMPI Monitoring — every model's quarterly KMPI return, bank-wide."""

import pandas as pd
import streamlit as st

import kmpi as kmpi_rules
import utils
from data_loader import kmpi_overview, load_kmpi_returns, load_kmpis, load_models, load_monitoring

RAG_ICON = {"Green": "🟢", "Amber": "🟠", "Red": "🔴", "Not reported": "⚪", None: "—"}

utils.header(
    "KMPI Monitoring",
    "Key model performance indicators: each model's owner or developer reports them every quarter, "
    "the validator reviews them. Select a row to open the model.",
)

periods = list(reversed(kmpi_rules.recent_periods(8)))
c1, c2 = st.columns([1, 3])
period = c1.selectbox("Period", periods, key="km_period")
c2.caption(f"Returns for {period} are due {utils.fmt_date(kmpi_rules.due_date(period).isoformat())} "
           f"({kmpi_rules.DUE_DAYS} days after quarter end).")

rows = kmpi_overview(period)
done = [r for r in rows if r["status"] in kmpi_rules.DONE]
utils.kpi_cards([
    ("Returns due", str(len(rows)), f"{sum(r['kmpis_due'] for r in rows)} KMPIs"),
    ("Submitted", str(len(done)), f"{sum(r['status'] == kmpi_rules.REVIEWED for r in rows)} reviewed"),
    ("Not yet submitted", str(len(rows) - len(done)),
     f"<span style='color:{utils.RED}; font-weight:600;'>{sum(r['overdue'] for r in rows)} overdue</span>"
     if any(r["overdue"] for r in rows) else "none overdue"),
    ("Red KMPIs", str(sum(r["red"] for r in rows)), "in submitted returns"),
    ("Amber KMPIs", str(sum(r["amber"] for r in rows)), "in submitted returns"),
])

if not rows:
    st.info("No returns due for this period.")
else:
    table = pd.DataFrame([{
        "model_id": r["model_id"], "Model": f"{r['model_id']} — {r['name']}", "Tier": r["tier"],
        "Return": r["status"] + (" · overdue" if r["overdue"] else ""),
        "KMPIs": r["kmpis_due"],
        "RAG": (f"🟢 {r['green']}  🟠 {r['amber']}  🔴 {r['red']}" if r["status"] in kmpi_rules.DONE else "—"),
        "Submitted by": (r["submitted_by"] or "—").split(" (")[0],
        "Reviewed by": (r["reviewed_by"] or "—").split(" (")[0],
        "Finding": r["finding_id"] or "",
    } for r in sorted(rows, key=lambda r: (not r["overdue"], r["status"] in kmpi_rules.DONE,
                                           -(r["red"] * 10 + r["amber"]), r["model_id"]))])
    event = st.dataframe(table.drop(columns=["model_id"]), hide_index=True, width="stretch",
                         height=35 * (len(table) + 1) + 3,
                         on_select="rerun", selection_mode="single-row", key="km_table")
    if event.selection and event.selection.rows:
        utils.go_to_model(table.iloc[event.selection.rows[0]]["model_id"])

# ---------------------------------------------------------------- breaches in the period
mon = load_monitoring()
names = {m["model_id"]: m["name"] for m in load_models()}
breach = mon[(mon["period"] == period) & mon["rag"].isin(["Red", "Amber", "Not reported"])]
st.subheader(f"Amber and red KMPIs — {period}")
if breach.empty:
    st.caption("None in the returns submitted so far.")
else:
    comments = {(r["model_id"], kid): v.get("comment") for r in load_kmpi_returns() if r["period"] == period
                for kid, v in r["values"].items()}
    st.dataframe(pd.DataFrame([{
        "Model": f"{b['model_id']} — {names.get(b['model_id'], '')}",
        "KMPI": f"{b['kmpi_id']} {b['metric']}",
        "Value": "—" if b["value"] is None or b["value"] != b["value"] else f"{b['value']:g}",
        "RAG": f"{RAG_ICON[b['rag']]} {b['rag']}",
        "Owner's explanation": comments.get((b["model_id"], b["kmpi_id"])) or "",
    } for _, b in breach.assign(_o=breach["rag"].map({"Red": 0, "Amber": 1, "Not reported": 2}))
                        .sort_values(["_o", "model_id"]).iterrows()]),
        hide_index=True, width="stretch")

# ---------------------------------------------------------------- trend across periods
st.subheader("Worst KMPI by model and period")
if not mon.empty:
    worst = (mon.groupby(["model_id", "period"])["rag"]
             .agg(lambda s: kmpi_rules.worst(list(s))).reset_index())
    grid = worst.pivot(index="model_id", columns="period", values="rag")
    grid = grid[sorted(grid.columns)[-8:]].apply(lambda col: col.map(lambda r: RAG_ICON.get(r, "") if r == r else ""))
    grid.insert(0, "Model", [f"{i} — {names.get(i, '')}" for i in grid.index])
    st.dataframe(grid.reset_index(drop=True), hide_index=True, width="stretch")
    st.caption("🟢 all green · 🟠 at least one amber · 🔴 at least one red · ⚪ a value not reported · "
               "blank: no return submitted.")

# ---------------------------------------------------------------- library export
with st.expander(f"KMPI library — all models ({len(load_kmpis())} KMPIs)"):
    lib = pd.DataFrame([{
        "KMPI ID": k["kmpi_id"], "Model": k["model_id"], "KMPI": k["name"], "Category": k["category"],
        "Description": k["description"], "Calculation": k["definition"], "Data source": k.get("data_source"),
        "Unit": k.get("unit"), "Direction": k["direction"], "Thresholds": kmpi_rules.threshold_text(k),
        "Frequency": k["frequency"], "Active": k.get("active", True),
    } for k in load_kmpis()])
    st.dataframe(lib, hide_index=True, width="stretch", height=320)
    st.download_button("Download the library (CSV)", lib.to_csv(index=False).encode("utf-8"),
                       file_name="qdb_kmpi_library.csv", mime="text/csv", key="km_lib_csv")
