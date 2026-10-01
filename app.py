import streamlit as st
import utils
from data_loader import load_models

utils.page_setup("QDB Model Governance")

# Deep link: /model_detail?model=<id> (and any page ?model=<id>) must work in a
# brand-new tab / empty session. Apply the param before the selected page runs.
valid_ids = [m["model_id"] for m in load_models()]
deep_link = utils.read_model_query_param()
if deep_link and deep_link in valid_ids:
    st.session_state["selected_model_id"] = deep_link
elif deep_link:
    st.session_state["_invalid_model_qp"] = deep_link

pages = [
    st.Page("views/dashboard.py", title="Executive Dashboard", default=True),
    st.Page("views/tasks.py", title="My Tasks", url_path="tasks"),
    st.Page("views/inventory.py", title="Model Inventory", url_path="inventory"),
    st.Page("views/model_detail.py", title="Model Detail", url_path="model_detail"),
    st.Page("views/findings.py", title="Findings Tracker", url_path="findings"),
    st.Page("views/registers.py", title="Registers", url_path="registers"),
    st.Page("views/register.py", title="Register Model / Tool", url_path="register"),
    st.Page("views/framework.py", title="Governance Framework", url_path="framework"),
    st.Page("views/admin.py", title="Administration", url_path="admin"),
]

pg = st.navigation(pages)
if deep_link and deep_link in valid_ids and pg.url_path != "model_detail":
    st.switch_page("views/model_detail.py")
pg.run()
