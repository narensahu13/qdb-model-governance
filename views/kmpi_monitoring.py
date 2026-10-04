"""KMPI Monitoring — every model's current KMPI return, bank-wide."""

import pandas as pd
import streamlit as st

import kmpi as kmpi_rules
import utils
from data_loader import kmpi_overview, load_kmpi_returns, load_kmpis, load_models

utils.header(
    "KMPI Monitoring",
    "Each model reports its KMPIs at its own frequency; the owner or developer submits, the validator "
    "reviews. Select a row to open the model.",
)

rows = kmpi_overview()
due = [r for r in rows if r["kmpis_due"]]
done = [r for r in due if r["status"] in kmpi_rules.DONE]
late = [r for r in due if r["overdue"]]
utils.kpi_cards([
    ("Returns due now", str(len(due)), f"{sum(r['kmpis_due'] for r in due)} KMPIs"),
    ("Submitted", str(len(done)), f"{sum(r['status'] == kmpi_rules.REVIEWED for r in due)} reviewed"),
    ("Not yet submitted", str(len(due) - len(done)),
     f"<span style='color:{utils.RED}; font-weight:600;'>{len(late)} overdue</span>" if late else "none overdue"),
    ("KMPIs failed", str(sum(r["fail"] for r in rows)), "in submitted returns"),
])

st.subheader("Current returns")
if not rows:
    st.info("No model in use has KMPIs yet.")
else:
    order = {True: 0, False: 1}
    rows = sorted(rows, key=lambda r: (order[r["overdue"]], r["status"] in kmpi_rules.DONE, -r["fail"], r["model_id"]))
    table = pd.DataFrame([{
        "model_id": r["model_id"], "Model": f"{r['model_id']} — {r['name']}", "Frequency": r["frequency"],
        "Period": r["period"], "Status": r["status"] + (" · overdue" if r["overdue"] else ""),
        "Due": utils.fmt_date(r["due"]) if r["due"] else "—",
        "Results": (f"✅ {r['pass']}  ❌ {r['fail']}  ⚪ {r['na']}" if r["status"] in kmpi_rules.DONE else "—"),
        "Last 8 returns": r["trend"] or "—",
        "Submitted by": (r["submitted_by"] or "—").split(" (")[0],
        "Finding": r["finding_id"] or "",
    } for r in rows])
    event = st.dataframe(table.drop(columns=["model_id"]), hide_index=True, width="stretch",
                         height=35 * (len(table) + 1) + 3, on_select="rerun", selection_mode="single-row",
                         key="km_table")
    st.caption("Last 8 returns: ✅ all passed · ❌ at least one fail · ⚪ a KMPI not available.")
    if event.selection and event.selection.rows:
        utils.go_to_model(table.iloc[event.selection.rows[0]]["model_id"])

# ---------------------------------------------------------------- KMPIs not passed in the latest returns
names = {m["model_id"]: m["name"] for m in load_models()}
latest = {}
for r in load_kmpi_returns():
    if r["status"] in kmpi_rules.DONE:
        cur = latest.get(r["model_id"])
        if cur is None or kmpi_rules.period_end(r["period"]) > kmpi_rules.period_end(cur["period"]):
            latest[r["model_id"]] = r
not_passed = [{
    "Model": f"{mid} — {names.get(mid, '')}", "Period": r["period"], "KMPI": f"{kid} {v['name']}",
    "Value": v.get("value") or "—", "Result": f"{kmpi_rules.RESULT_ICON[v['result']]} {v['result']}",
    "Owner's comment": v.get("comment") or "",
} for mid, r in sorted(latest.items()) for kid, v in r["values"].items() if v.get("result") != kmpi_rules.PASS]
st.subheader("KMPIs not passed in each model's latest return")
if not_passed:
    st.dataframe(pd.DataFrame(not_passed), hide_index=True, width="stretch")
else:
    st.caption("None — every KMPI passed in the latest returns.")

# ---------------------------------------------------------------- library export
kmpis = load_kmpis()
with st.expander(f"All KMPIs ({len(kmpis)})"):
    lib = pd.DataFrame([{
        "KMPI ID": k["kmpi_id"], "Model": k["model_id"], "KMPI": k["name"],
        "Description (pass/fail criteria)": k["description"],
        "Frequency": k.get("frequency") or kmpi_rules.AS_MODEL, "Active": k.get("active", True),
    } for k in kmpis])
    st.dataframe(lib, hide_index=True, width="stretch", height=320)
    st.download_button("Download (CSV)", lib.to_csv(index=False).encode("utf-8"),
                       file_name="qdb_kmpis.csv", mime="text/csv", key="km_lib_csv")
