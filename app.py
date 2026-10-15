"""QDB Model Governance — entry point.

The frame matches the IFRS 9 ECL app: the QDB logo and the menu on one bar across
the top, who is acting at its right, and a title row on every page.
"""
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

V = "views/"
# Grouped menu; people only see the pages they can use.
models_pages = [
    st.Page(V + "inventory.py", title="Model inventory", url_path="inventory", icon=":material/inventory_2:"),
    st.Page(V + "model_detail.py", title="Model detail", url_path="model_detail", icon=":material/description:"),
]
if auth.has_permission("register_model") or auth.has_permission("register_tool"):
    models_pages.append(st.Page(V + "register.py", title="Register a model or tool", url_path="register",
                                icon=":material/add_circle:"))
reference_pages = [st.Page(V + "framework.py", title="How it works", url_path="framework", icon=":material/help:")]
if auth.has_permission("administer"):
    reference_pages.append(st.Page(V + "admin.py", title="Administration", url_path="admin",
                                   icon=":material/admin_panel_settings:"))

pages = {
    "Work": [
        st.Page(V + "tasks.py", title="My tasks", url_path="tasks", icon=":material/task_alt:"),
        st.Page(V + "dashboard.py", title="Dashboard", default=True, icon=":material/dashboard:"),
    ],
    "Models": models_pages,
    "Monitoring": [
        st.Page(V + "kmpi_monitoring.py", title="KMPI monitoring", url_path="kmpi", icon=":material/monitoring:"),
        st.Page(V + "findings.py", title="Findings tracker", url_path="findings", icon=":material/flag:"),
        st.Page(V + "registers.py", title="Registers (EUC, AI)", url_path="registers", icon=":material/list_alt:"),
    ],
    "Help": reference_pages,
}

pg = st.navigation(pages, position="top")
utils.mark_section(next((i for i, ps in enumerate(pages.values())
                         if any(p.title == pg.title for p in ps)), None))
if deep_link and deep_link in valid_ids and pg.url_path != "model_detail":
    st.switch_page(V + "model_detail.py")
pg.run()
