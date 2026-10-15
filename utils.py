"""Shared frame and small HTML helpers, in the IFRS 9 ECL app's look (see theme.py):
logo and menu on one top bar, a title row per page, white cards on a tinted page."""

import html
from pathlib import Path

import streamlit as st

import auth
import theme

ASSETS = Path(__file__).parent / "assets"

# QDB plum, as in the IFRS 9 app; status tones are its err / warn / ok / muted text colours.
PLUM = "#5b1f6e"
PLUM_LIGHT = "#8e5aa3"
TEAL = "#0d9488"
NAVY = PLUM            # older name, kept for existing calls
GOLD = PLUM_LIGHT      # older name, kept for existing calls
GREEN = "#067647"
AMBER = "#b54708"
RED = "#b42318"
GREY = "#475467"
BLUE = "#175cd3"

RISK_TYPE_COLORS = {
    "IFRS 9 / Provisioning": PLUM,
    "Credit Rating & Scoring": PLUM_LIGHT,
    "Pricing": "#d97706",
    "Market & Liquidity Risk": TEAL,
    "Operational & Non-Financial Risk": "#8a94a6",
}

STATUS_COLORS = {
    "In Production": GREEN,
    "Approved with Conditions": AMBER,
    "Restricted Use": RED,
    "Under Remediation": RED,
    "In Production - Approval Pending": RED,
    "In Validation": "#0288d1",
    "Awaiting Approval": "#6a1b9a",
    "Approved — Awaiting Implementation": "#6a1b9a",
    "In Development": GREY,
    "Retired": "#9e9e9e",
}

VALIDATION_STATUS_COLORS = {
    "On Track": GREEN,
    "Due Soon": AMBER,
    "Overdue": RED,
    "Never Validated": RED,
    "Pre-implementation": GREY,
    "Retired": "#9e9e9e",
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
    """Once per run, from app.py: page config, logo, stylesheet, who is acting."""
    st.set_page_config(
        page_title=title,
        page_icon=str(ASSETS / "favicon.png"),
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.logo(str(ASSETS / "logo.png"), size="large")
    st.html(theme.CSS + theme.EXTRA_CSS)
    user = auth.get_current_user()  # self-init default user on a fresh session
    ini = (user["name"].strip()[:1] or "?").upper()
    st.markdown(
        f'<div class="hdr-user"><span class="av">{esc(ini)}</span><span><b>{esc(user["name"])}</b>'
        f'<small>{esc(auth.ROLE_LABELS[user["role"]])} · Model Risk Management</small></span></div>',
        unsafe_allow_html=True,
    )


def mark_section(i: int | None) -> None:
    """Highlight the top menu holding the page on screen (as in the IFRS 9 app)."""
    if i is None:
        return
    st.html(f"""<style>
  [data-testid="stToolbar"] div:nth-child({i + 1}) >
      button[data-testid="stTopNavSection"] {{
      background: rgba(165, 142, 210, .25); color: var(--plum);}}
</style>""")


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def header(title: str, subtitle: str = "", right=None):
    """The page's title row: title and subtitle on the left; on the right an optional
    picker (``right`` draws it, e.g. the model picker) and the "Switch user" control."""
    sub = f'<div class="pg-sub">{subtitle}</div>' if subtitle else ""
    head = f'<div class="pg-head"><div class="pg-title">{esc(title)}</div>{sub}</div>'
    cols = st.columns([8, 4.2, 1.7] if right else [12, 1.7], vertical_alignment="center", gap="small")
    cols[0].markdown(head, unsafe_allow_html=True)
    if right:
        with cols[1]:
            right()
    with cols[-1]:
        auth.user_selector()


def fmt_date(iso: str | None, empty: str = "—") -> str:
    """'2025-11-20' -> '20 Nov 2025'."""
    if not iso:
        return empty
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(iso)


def kpi_cards(items) -> None:
    """KPI tiles (the IFRS 9 app's): items are (label, value, note) or (label, value,
    note, tone) with tone err / warn / ok / info / plum. Values wrap rather than truncate."""
    cells = []
    for it in items:
        label, value, note = it[0], it[1], it[2] if len(it) > 2 else None
        tone = it[3] if len(it) > 3 and it[3] else ("err" if note and RED in str(note) else "plum")
        cells.append(f'<div class="kpi {tone}"><div class="l">{esc(label)}</div>'
                     f'<div class="v">{esc(value)}</div>'
                     + (f'<div class="n">{note}</div>' if note else "") + "</div>")
    st.markdown('<div class="kpis">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def callout(tone: str, text: str, title: str | None = None) -> None:
    """A one-line verdict, coloured by tone: err, warn, info, ok, muted, plum."""
    icon = {"err": "!", "warn": "!", "info": "i", "ok": "✓", "muted": "•", "plum": "›"}.get(tone, "•")
    head = f"<b>{esc(title)}</b> " if title else ""
    st.markdown(f'<div class="callout {tone}"><span class="ic {tone}">{icon}</span>'
                f'<div>{head}{text}</div></div>', unsafe_allow_html=True)


def card_header(title: str, num=None, state: str = "", right: str = "") -> None:
    """A card's title row: an optional numbered dot (green when done), title, right pill."""
    n = (f'<span class="num {esc(state)}">{"✓" if state == "done" else esc(num)}</span>'
         if num is not None else "")
    r = f'<span class="r">{right}</span>' if right else ""
    st.markdown(f'<div class="card-h">{n}<span class="t">{esc(title)}</span>{r}</div>',
                unsafe_allow_html=True)


def badge(text: str, color: str) -> str:
    """A pill tinted with ``color`` (text in the colour, a faint fill and border)."""
    return (f'<span class="qdb-badge" style="color:{color}; background:{color}14; '
            f'border-color:{color}40;">{esc(text)}</span>')


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
