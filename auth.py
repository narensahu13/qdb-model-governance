"""Identity & permissions layer.

ALL identity and permission checks in the app go through this module only.
In this PoC the "logged-in" user is simulated with a sidebar selector backed
by a mock user directory (data/users.json). In production this module is the
single place to swap in real authentication (SSO / AD groups): replace
`get_current_user` with the SSO principal lookup and every page keeps working
unchanged.
"""

import json
from pathlib import Path

import streamlit as st

USERS_FILE = Path(__file__).resolve().parent / "data" / "users.json"

ROLE_LABELS = {
    "LOD1": "1st Line — Model Owner / Developer",
    "LOD2": "2nd Line — Model Validation Unit",
    "LOD3": "3rd Line — Internal Audit",
    "ADMIN": "MRM Administrator",
}

ROLE_COLORS = {
    "LOD1": "#1f77b4",
    "LOD2": "#14284b",
    "LOD3": "#b8933d",
    "ADMIN": "#607d8b",
}

# Request types and who may initiate them.
REQUEST_TYPES = {
    "MMC": {
        "label": "Material Model Change",
        "short": "MMC",
        "initiate_roles": ["LOD1", "ADMIN"],
        "default_assignee_roles": ["LOD2"],
        "description": "LoD1 records a material change for independent revalidation by MVU.",
    },
    "NMMC": {
        "label": "Non-material Model Change",
        "short": "NMMC",
        "initiate_roles": ["LOD1", "ADMIN"],
        "default_assignee_roles": ["LOD2"],
        "description": "LoD1 notifies MVU of a non-material change (notification / light review).",
    },
    "VAL": {
        "label": "Independent Validation",
        "short": "VAL",
        "initiate_roles": ["LOD2", "ADMIN"],
        "default_assignee_roles": ["LOD2"],
        "description": "MVU records periodic, initial, or targeted independent validation.",
    },
    "VRQ": {
        "label": "Validation Request",
        "short": "VRQ",
        "initiate_roles": ["LOD1", "ADMIN"],
        "default_assignee_roles": ["LOD2"],
        "description": "LoD1 asks MVU to validate (or revalidate) a model.",
    },
    "VFI": {
        "label": "Validation Finding",
        "short": "VFI",
        "initiate_roles": ["LOD2", "LOD3", "ADMIN"],
        "default_assignee_roles": ["LOD1"],
        "description": "LoD2/LoD3 raises a finding; LoD1 must respond; raiser closes.",
    },
}

REQUEST_TYPE_ORDER = ["MMC", "NMMC", "VAL", "VRQ", "VFI"]

# Permission matrix as data: action -> roles allowed to perform it.
PERMISSIONS = {
    "initiate_mmc": ["LOD1", "ADMIN"],
    "initiate_nmmc": ["LOD1", "ADMIN"],
    "initiate_val": ["LOD2", "ADMIN"],
    "initiate_vrq": ["LOD1", "ADMIN"],
    "initiate_vfi": ["LOD2", "LOD3", "ADMIN"],
    "respond_request": ["LOD1", "ADMIN"],
    "close_request": ["LOD2", "LOD3", "ADMIN"],  # further restricted to raiser's role
    "assign_request": ["LOD1", "LOD2", "LOD3", "ADMIN"],
    "upload_evidence": ["LOD1", "LOD2", "LOD3", "ADMIN"],
    "record_change": ["LOD1", "ADMIN"],
    "record_audit": ["LOD3", "ADMIN"],
    # Aliases kept for gradual migration / smoke tests
    "add_validation": ["LOD2", "ADMIN"],
    "raise_issue": ["LOD2", "LOD3", "ADMIN"],
    "respond_issue": ["LOD1", "ADMIN"],
    "close_issue": ["LOD2", "LOD3", "ADMIN"],
}

ACTION_LABELS = {
    "initiate_mmc": "Initiate a Material Model Change (MMC)",
    "initiate_nmmc": "Initiate a Non-material Model Change (NMMC)",
    "initiate_val": "Record an independent validation (VAL)",
    "initiate_vrq": "Request validation from MVU (VRQ)",
    "initiate_vfi": "Raise a validation finding (VFI)",
    "respond_request": "Respond on an open request",
    "close_request": "Close a request (raiser's line only)",
    "assign_request": "Assign / send a request to a validator or owner",
    "upload_evidence": "Attach evidence (open requests only)",
    "record_change": "Record a model change",
    "record_audit": "Record an internal audit review",
    "add_validation": "Record a validation (VAL)",
    "raise_issue": "Raise a validation finding (VFI)",
    "respond_issue": "Respond to a finding",
    "close_issue": "Close a finding (raiser's line only)",
}

_INITIATE_ACTION = {
    "MMC": "initiate_mmc",
    "NMMC": "initiate_nmmc",
    "VAL": "initiate_val",
    "VRQ": "initiate_vrq",
    "VFI": "initiate_vfi",
}

_SESSION_KEY = "current_user_name"
_DEFAULT_USER = "Maryam Al-Kaabi"  # MRM Administrator


def load_users() -> list[dict]:
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_user(name: str) -> dict | None:
    for u in load_users():
        if u["name"] == name:
            return u
    return None


_FALLBACK_USER = {
    "name": _DEFAULT_USER,
    "title": "MRM Administrator",
    "role": "ADMIN",
}


def get_current_user() -> dict:
    """The acting user (dict with name, title, role). Single source of identity.

    Safe on a brand-new session (e.g. a deep link opened in a new tab): if no
    user has been selected yet, a default user is written into session state
    so later permission checks never see a missing key or a None user.
    """
    name = st.session_state[_SESSION_KEY] if _SESSION_KEY in st.session_state else None
    user = get_user(name) if name else None
    if user is None:
        user = get_user(_DEFAULT_USER) or dict(_FALLBACK_USER)
        if _SESSION_KEY not in st.session_state:
            st.session_state[_SESSION_KEY] = user["name"]
    return user


def users_for_roles(*roles: str) -> list[dict]:
    return [u for u in load_users() if u["role"] in roles]


def user_option_label(user: dict) -> str:
    return f"{user['name']} ({user['title']})"


def user_option_labels(*roles: str) -> list[str]:
    return [user_option_label(u) for u in users_for_roles(*roles)]


def default_option_index(options: list[str], preferred: str | None) -> int:
    """Index of `preferred` in `options`, matching name or 'Name (Title)'."""
    if not options:
        return 0
    if not preferred:
        return 0
    if preferred in options:
        return options.index(preferred)
    preferred_name = preferred.split(" (")[0].strip()
    for i, opt in enumerate(options):
        if opt == preferred_name or opt.startswith(preferred_name + " "):
            return i
    return 0


def has_permission(action: str) -> bool:
    return get_current_user()["role"] in PERMISSIONS[action]


def can_initiate(request_type: str) -> bool:
    action = _INITIATE_ACTION.get(request_type)
    return bool(action) and has_permission(action)


def initiable_types() -> list[str]:
    return [t for t in REQUEST_TYPE_ORDER if can_initiate(t)]


def can_close_issue(raised_by_role: str) -> bool:
    """Legacy alias: finding closed by the line that raised it, or ADMIN."""
    role = get_current_user()["role"]
    return role == "ADMIN" or (role in PERMISSIONS["close_issue"] and role == raised_by_role)


def can_close_request(req: dict) -> bool:
    """Close rules by request type.

    - VFI: raiser's line (LOD2/LOD3) or ADMIN
    - MMC / NMMC / VAL / VRQ: LoD2 (MVU) or ADMIN after an outcome is recorded
    """
    role = get_current_user()["role"]
    if role == "ADMIN":
        return True
    rtype = req.get("type")
    if rtype == "VFI":
        return role == req.get("initiated_by_role") and role in ("LOD2", "LOD3")
    return role == "LOD2"

def who_can(action: str) -> str:
    """Human-readable list of roles allowed to perform an action (for denial messages)."""
    return " or ".join(ROLE_LABELS[r] for r in PERMISSIONS[action])


def permission_denied(action: str):
    st.info(
        f"You are acting as **{get_current_user()['name']}** "
        f"({ROLE_LABELS[get_current_user()['role']]}). "
        f"Only **{who_can(action)}** can perform this action."
    )


def user_selector():
    """Sidebar 'Acting as' selector. Rendered once from utils.page_setup."""
    users = load_users()
    names = [u["name"] for u in users]
    labels = {u["name"]: f"{u['name']} — {ROLE_LABELS[u['role']]}" for u in users}
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = _DEFAULT_USER
    st.selectbox(
        "Acting as",
        names,
        key=_SESSION_KEY,
        format_func=lambda n: labels.get(n, n),
    )
    u = get_current_user()
    st.caption(f"{u['title']} · {ROLE_LABELS[u['role']]}")
    st.caption("PoC: role simulation — replaced by single sign-on in production")


def role_badge_html(role: str) -> str:
    color = ROLE_COLORS.get(role, "#607d8b")
    return (
        f'<span class="qdb-badge" style="background:{color};">'
        f"{ROLE_LABELS.get(role, role)}</span>"
    )
