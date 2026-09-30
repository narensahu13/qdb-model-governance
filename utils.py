"""Shared branding, styling and small HTML badge helpers."""

import streamlit as st

import auth

NAVY = "#14284b"
GOLD = "#b8933d"
GREEN = "#2e7d32"
AMBER = "#ed6c02"
RED = "#c62828"
GREY = "#607d8b"

RISK_TYPE_COLORS = {
    "IFRS 9 / Provisioning": "#9467bd",
    "Credit Rating & Scoring": "#1f77b4",
    "Pricing": "#8c564b",
    "Market & Liquidity Risk": "#2ca02c",
    "Operational & Non-Financial Risk": "#d62728",
}

STATUS_COLORS = {
    "In Production": GREEN,
    "Approved with Conditions": AMBER,
    "Restricted Use": RED,
    "Under Remediation": RED,
    "In Production - Approval Pending": RED,
    "In Validation": "#0288d1",
    "In Development": GREY,
    "Retired": "#9e9e9e",
}

VALIDATION_STATUS_COLORS = {
    "On Track": GREEN,
    "Due Soon": AMBER,
    "Overdue": RED,
    "Never Validated": RED,
    "Pre-implementation": GREY,
}

RATING_COLORS = {
    "Fit for Purpose": GREEN,
    "Fit with Conditions": AMBER,
    "Restricted Use": RED,
    "Not Fit for Purpose": "#7f0000",
}

SEVERITY_COLORS = {"High": RED, "Medium": AMBER, "Low": GREY}

TIER_COLORS = {1: RED, 2: AMBER, 3: GREEN}


def read_model_query_param() -> str | None:
    """Return `?model=` from the URL, or None. Accepts str or list values."""
    try:
        raw = st.query_params.get("model")
    except Exception:
        return None
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    mid = str(raw).strip()
    return mid or None


def drop_model_query_param() -> None:
    """Remove only `model` from the query string so the selectbox can take over."""
    try:
        if "model" in st.query_params:
            del st.query_params["model"]
    except Exception:
        pass


def read_request_query_param() -> str | None:
    """Return `?request=` from the URL, or None. Accepts str or list values."""
    try:
        raw = st.query_params.get("request")
    except Exception:
        return None
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    rid = str(raw).strip()
    return rid or None


def drop_request_query_param() -> None:
    """Remove only `request` from the query string after it is consumed."""
    try:
        if "request" in st.query_params:
            del st.query_params["request"]
    except Exception:
        pass


def page_setup(title: str):
    st.set_page_config(
        page_title=f"{title} | QDB Model Governance",
        page_icon="🏛️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        f"""
        <style>
        .block-container {{ padding-top: 2.2rem; }}
        h1, h2, h3 {{ color: {NAVY}; }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {NAVY} 0%, #1d3a6b 100%);
        }}
        [data-testid="stSidebar"] * {{ color: #f5f5f5 !important; }}
        [data-testid="stSidebar"] a:hover {{ color: {GOLD} !important; }}
        [data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid #e0e0e0;
            border-left: 4px solid {GOLD};
            border-radius: 8px;
            padding: 12px 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        .qdb-badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            color: white;
            font-size: 0.78rem;
            font-weight: 600;
            margin-right: 6px;
            white-space: nowrap;
        }}
        .qdb-header {{
            border-bottom: 3px solid {GOLD};
            padding-bottom: 8px;
            margin-bottom: 16px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding: 4px 0 12px 0;">
              <div style="font-size: 1.25rem; font-weight: 700;">Qatar Development Bank</div>
              <div style="font-size: 0.9rem; color: {GOLD} !important; font-weight: 600;">
                Model Risk Management
              </div>
              <div style="font-size: 0.75rem; opacity: 0.7; margin-top: 4px;">
                Proof of concept — pilot models, mock details
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        auth.get_current_user()  # self-init default user on a fresh session
        auth.user_selector()
        st.divider()


def header(title: str, subtitle: str = ""):
    sub = f'<div style="color:#666; font-size:0.95rem; margin-top:2px;">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="qdb-header"><h1 style="margin-bottom:0;">{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def fmt_date(iso: str | None, empty: str = "—") -> str:
    """'2025-11-20' -> '20 Nov 2025'."""
    if not iso:
        return empty
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(iso)


def kpi_cards(items: list[tuple[str, str, str | None]]) -> None:
    """A row of small cards that wrap instead of truncating (st.metric cuts
    long values such as dates). items: (label, value, optional note)."""
    cells = []
    for label, value, note in items:
        note_html = (
            f'<div style="font-size:0.78rem; color:#666; margin-top:2px;">{note}</div>'
            if note else ""
        )
        cells.append(
            f'<div style="flex:1 1 130px; min-width:120px; background:#fff; '
            f'border:1px solid #e0e0e0; border-left:4px solid {GOLD}; border-radius:8px; '
            f'padding:10px 14px;">'
            f'<div style="font-size:0.8rem; color:#555;">{label}</div>'
            f'<div style="font-size:1.3rem; font-weight:600; color:#1a1a2e; '
            f'line-height:1.3; overflow-wrap:anywhere;">{value}</div>{note_html}</div>'
        )
    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; gap:12px; margin:4px 0 12px 0;">'
        + "".join(cells) + "</div>",
        unsafe_allow_html=True,
    )


def badge(text: str, color: str) -> str:
    return f'<span class="qdb-badge" style="background:{color};">{text}</span>'


def tier_badge(tier: int) -> str:
    return badge(f"Tier {tier}", TIER_COLORS.get(tier, GREY))


def status_badge(status: str) -> str:
    return badge(status, STATUS_COLORS.get(status, GREY))


def validation_badge(vstatus: str) -> str:
    return badge(vstatus, VALIDATION_STATUS_COLORS.get(vstatus, GREY))


def rating_badge(rating: str | None) -> str:
    if not rating:
        return ""
    return badge(rating, RATING_COLORS.get(rating, GREY))


def severity_badge(sev: str) -> str:
    return badge(sev, SEVERITY_COLORS.get(sev, GREY))


def go_to_model(model_id: str, request_id: str | None = None):
    """Navigate to Model Detail for a model (optional request opens detail).

    Same-tab via `st.switch_page`. Sets session state so Validation & Findings
    opens the request when `request_id` is provided. Paths are tried against
    both `app.py` and standalone view entrypoints.
    """
    from streamlit.errors import StreamlitAPIException

    st.session_state["selected_model_id"] = model_id
    if request_id:
        st.session_state["md_selected_request"] = request_id
        st.session_state["_md_req_model"] = model_id
    qp = {"model": model_id}
    if request_id:
        qp["request"] = request_id
    for target in ("views/model_detail.py", "model_detail.py"):
        try:
            st.switch_page(target, query_params=qp)
            return
        except TypeError:
            try:
                st.switch_page(target)
                return
            except StreamlitAPIException:
                continue
        except StreamlitAPIException:
            continue
