import streamlit as st
import utils
from data_loader import models_dataframe

utils.header(
    "Model Inventory",
    "Central register of models in use. Click a Model ID to open the governance record.",
)

df = models_dataframe()

# ---------------------------------------------------------------- filters
f1, f2, f3, f4, f5 = st.columns([1.6, 1, 1.3, 1.3, 1.8])
with f1:
    risk_types = st.multiselect("Risk Type", sorted(df["Risk Type"].unique()))
with f2:
    tiers = st.multiselect("Tier", [1, 2, 3])
with f3:
    statuses = st.multiselect("Model Status", sorted(df["Status"].unique()))
with f4:
    val_statuses = st.multiselect(
        "Validation Status",
        ["On Track", "Due Soon", "Overdue", "Never Validated", "Pre-implementation"],
    )
with f5:
    search = st.text_input("Search", placeholder="Model name, ID, owner, methodology...")

filtered = df.copy()
if risk_types:
    filtered = filtered[filtered["Risk Type"].isin(risk_types)]
if tiers:
    filtered = filtered[filtered["Tier"].isin(tiers)]
if statuses:
    filtered = filtered[filtered["Status"].isin(statuses)]
if val_statuses:
    filtered = filtered[filtered["Validation Status"].isin(val_statuses)]
if search:
    mask = (
        filtered["Model Name"].str.contains(search, case=False)
        | filtered["Model ID"].str.contains(search, case=False)
        | filtered["Owner"].str.contains(search, case=False)
        | filtered["Methodology"].str.contains(search, case=False)
    )
    filtered = filtered[mask]

st.caption(f"{len(filtered)} of {len(df)} models shown")

# ---------------------------------------------------------------- table
display_cols = [
    "Model ID", "Model Name", "Risk Type", "Tier", "Tier Confirmed", "Status", "Last Rating",
    "Validation Status", "Next Validation Due", "Open Issues",
    "High Open Issues", "Doc Completeness (%)", "Owner", "Source", "AI System",
]

# Render Model ID as an in-app link to the Model Detail page (?model=<id> is
# picked up by views/model_detail.py via st.query_params).
table = filtered[display_cols].copy()
table["Model ID"] = "/model_detail?model=" + table["Model ID"]

event = st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    height=560,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Model ID": st.column_config.LinkColumn(
            "Model ID",
            display_text=r"model=(.+)$",
            help="Click to open the model's full governance record",
        ),
        "Tier": st.column_config.NumberColumn(width="small"),
        "Tier Confirmed": st.column_config.CheckboxColumn(
            "Tier signed off", width="small", help="Gate G1: tier confirmed by the MRM function"),
        "Open Issues": st.column_config.NumberColumn(width="small"),
        "High Open Issues": st.column_config.NumberColumn("High Issues", width="small"),
        "AI System": st.column_config.CheckboxColumn(
            "AI", width="small", help="AI system under the QCB AI Guideline",
        ),
        "Doc Completeness (%)": st.column_config.ProgressColumn(
            "Docs", min_value=0, max_value=100, format="%d%%"
        ),
    },
)

# Secondary path: selecting a row (checkbox at the left edge) also navigates.
if event.selection and event.selection.rows:
    selected_row = filtered.iloc[event.selection.rows[0]]
    utils.go_to_model(selected_row["Model ID"])

st.caption("Click a Model ID or select a row to open the governance record.")

# ---------------------------------------------------------------- factsheets
st.divider()
fc1, fc2 = st.columns([3, 1.4])
fc1.markdown(
    "**Model factsheets** — one page per model for owners, sponsors, senior management, "
    "auditors and QCB, generated from the live records."
)
if fc2.button("Prepare factsheets for the models shown", key="prep_factsheets", width="stretch"):
    import io
    import zipfile
    from datetime import date

    from data_loader import factsheet_pdf

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for mid in filtered["Model ID"]:
            zf.writestr(f"{mid}_factsheet.pdf", factsheet_pdf(mid))
    st.session_state["_factsheet_zip"] = buf.getvalue()
    st.session_state["_factsheet_zip_name"] = f"qdb_model_factsheets_{date.today().isoformat()}.zip"
if st.session_state.get("_factsheet_zip"):
    st.download_button(
        "Download factsheets (ZIP)", st.session_state["_factsheet_zip"],
        st.session_state["_factsheet_zip_name"], "application/zip", key="dl_factsheet_zip",
    )
