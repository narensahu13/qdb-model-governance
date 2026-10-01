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

import auth  # noqa: E402

# Grouped menu; people only see the pages they can use.
models_pages = [
    st.Page("views/inventory.py", title="Model Inventory", url_path="inventory"),
    st.Page("views/model_detail.py", title="Model Detail", url_path="model_detail"),
]
if auth.has_permission("register_model") or auth.has_permission("register_tool"):
    models_pages.append(st.Page("views/register.py", title="Register a Model or Tool", url_path="register"))
reference_pages = [st.Page("views/framework.py", title="How It Works", url_path="framework")]
if auth.has_permission("administer"):
    reference_pages.append(st.Page("views/admin.py", title="Administration", url_path="admin"))

pages = {
    "Work": [
        st.Page("views/tasks.py", title="My Tasks", url_path="tasks"),
        st.Page("views/dashboard.py", title="Dashboard", default=True),
    ],
    "Models": models_pages,
    "Oversight": [
        st.Page("views/findings.py", title="Findings Tracker", url_path="findings"),
        st.Page("views/registers.py", title="Registers (EUC, AI)", url_path="registers"),
    ],
    "Reference": reference_pages,
}

pg = st.navigation(pages)
if deep_link and deep_link in valid_ids and pg.url_path != "model_detail":
    st.switch_page("views/model_detail.py")
pg.run()
