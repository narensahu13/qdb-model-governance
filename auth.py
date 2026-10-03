"""Identity & permissions layer.

ALL identity and permission checks in the app go through this module only.
In this PoC the "logged-in" user is simulated with a sidebar selector backed
by a mock user directory (users table, seeded from data/seed/users.json). In production this module is the
single place to swap in real authentication (SSO / AD groups): replace
`get_current_user` with the SSO principal lookup and every page keeps working
unchanged.
"""

import streamlit as st

import repository

ROLE_LABELS = {
    "LOD1": "Model owner / developer",
    "LOD2": "Model validator",
    "LOD3": "Internal audit",
    "ADMIN": "MRM administrator",
    "SPONSOR": "Model sponsor",
    "VIEWER": "Read-only (model user)",
}

ROLE_COLORS = {
    "LOD1": "#1f77b4",
    "LOD2": "#14284b",
    "LOD3": "#b8933d",
    "ADMIN": "#607d8b",
    "SPONSOR": "#6a1b9a",
    "VIEWER": "#90a4ae",
}

# Three request types: Model Change, Validation, Finding.
REQUEST_TYPES = {
    "MC": {
        "label": "Model Change",
        "short": "MC",
        "default_assignee_roles": ["LOD2"],
        "description": (
            "Record a model change for the validator's review. Materiality (Material / "
            "Non-material) is a field on the request — Material changes require "
            "revalidation before the new version is used."
        ),
    },
    "VAL": {
        "label": "Validation",
        "short": "VAL",
        "default_assignee_roles": ["LOD2"],
        "description": (
            "Validation request or independent validation (initial, periodic, targeted, "
            "or ad-hoc). Owners may request one; the validator records it with a rating."
        ),
    },
    "FND": {
        "label": "Finding",
        "short": "FND",
        "default_assignee_roles": ["LOD1"],
        "description": (
            "Validation or audit finding. The validator or Internal Audit raises it; the "
            "owner responds; the line that raised it closes it."
        ),
    },
}

REQUEST_TYPE_ORDER = ["MC", "VAL", "FND"]

# Permission matrix as data: action -> roles allowed to perform it.
# Segregation of duties: the MRM Administrator coordinates (schedules and
# assigns work) but cannot raise findings, close requests or record changes.
PERMISSIONS = {
    "initiate_model_change": ["LOD1", "LOD2"],
    "initiate_validation": ["LOD1", "LOD2", "LOD3", "ADMIN"],
    "initiate_finding": ["LOD2", "LOD3"],
    "respond_request": ["LOD1", "LOD2", "LOD3", "ADMIN"],
    "close_request": ["LOD2", "LOD3"],  # further restricted to the raiser's line for FND
    "assign_request": ["LOD2", "ADMIN"],
    "upload_evidence": ["LOD1", "LOD2", "LOD3", "ADMIN"],
    "record_change": ["LOD1"],
    "record_audit": ["LOD3"],
    # Phase 1 — inventory
    "register_model": ["LOD1", "ADMIN"],
    "register_tool": ["LOD1", "ADMIN"],
    "edit_model": ["LOD1", "ADMIN"],          # LOD1 only for models they own or develop
    "assign_accountability": ["ADMIN"],       # owner, developer, validator, sponsor
    "propose_tier": ["LOD1", "ADMIN"],
    "confirm_tier": ["LOD2", "ADMIN"],        # never the person who proposed it
    "approve_tier_override": ["SPONSOR"],     # the model's own sponsor
    # Phase 2 — validation workflow
    "submit_for_validation": ["LOD1", "ADMIN"],   # G2; LOD1 only for own models
    "run_engagement": ["LOD2"],                    # scope, info requests, draft, sign-off (G3)
    "answer_info_request": ["LOD1"],
    "owner_review": ["LOD1"],
    "record_approval": ["LOD1", "SPONSOR"],        # G4: the model's owner, then its sponsor
    "update_condition": ["LOD1", "LOD2"],
    "verify_implementation": ["LOD2"],             # G5
    "administer": ["ADMIN"],                        # Administration page
    # Phase 3 — KMPIs (key model performance indicators)
    "define_kmpi": ["LOD1", "ADMIN"],              # LOD1 only for own models
    "enter_kmpi": ["LOD1"],                        # owner or developer of the model
    "review_kmpi": ["LOD2"],                       # independent review of a submitted return
}

ACTION_LABELS = {
    "initiate_model_change": "Initiate a Model Change (MC)",
    "initiate_validation": "Initiate a Validation (VAL)",
    "initiate_finding": "Raise a Finding (FND)",
    "respond_request": "Post in a request thread",
    "close_request": "Close a request (raiser's line only for findings)",
    "assign_request": "Assign a request to a validator or owner",
    "upload_evidence": "Upload evidence and model documents",
    "record_change": "Record a model change",
    "record_audit": "Record an internal audit review",
    "register_model": "Register a model or tool (identification questionnaire)",
    "register_tool": "Record an EUC / AI tool in the registers",
    "edit_model": "Edit a model record (owners and developers: own models only)",
    "assign_accountability": "Assign owner, developer, validator and sponsor",
    "propose_tier": "Propose a tier assessment",
    "confirm_tier": "Confirm a tier assessment (gate G1)",
    "approve_tier_override": "Approve a tier override (the model's sponsor)",
    "submit_for_validation": "Submit a model for validation (gate G2)",
    "run_engagement": "Run a validation engagement and sign it off (gate G3)",
    "answer_info_request": "Answer a validator's information request",
    "owner_review": "Give the owner's factual-accuracy review of a draft report",
    "record_approval": "Approve a model (gate G4: its owner, then its sponsor)",
    "update_condition": "Update a condition of approval (owner: met; validator: verify)",
    "verify_implementation": "Verify implementation (gate G5)",
    "administer": "Administration: people, accountability, model IDs, database",
    "define_kmpi": "Define or change a model's KMPIs",
    "enter_kmpi": "Enter and submit KMPI values for a period",
    "review_kmpi": "Review a submitted KMPI return",
}

INITIATE_ACTION = {
    "MC": "initiate_model_change",
    "VAL": "initiate_validation",
    "FND": "initiate_finding",
}
_INITIATE_ACTION = INITIATE_ACTION

_SESSION_KEY = "current_user_name"
_DEFAULT_USER = "MRM Administrator 1"  # MRM Administrator


@st.cache_data
def _users() -> list[dict]:
    return repository.list_users()


def load_users() -> list[dict]:
    return _users()


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


def require(action: str) -> None:
    """Raise PermissionError unless the acting user may perform `action`."""
    if not has_permission(action):
        user = get_current_user()
        raise PermissionError(
            f"{user['name']} ({ROLE_LABELS[user['role']]}) cannot: "
            f"{ACTION_LABELS.get(action, action)}."
        )


def can_initiate(request_type: str) -> bool:
    action = _INITIATE_ACTION.get(request_type)
    return bool(action) and has_permission(action)


def initiable_types() -> list[str]:
    return [t for t in REQUEST_TYPE_ORDER if can_initiate(t)]


def can_close_request(req: dict) -> bool:
    """Close rules by request type (no administrator override).

    - FND: only the line that raised it (validator or Internal Audit)
    - MC / VAL: a validator (LoD2)
    """
    role = get_current_user()["role"]
    if req.get("type") == "FND":
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
    role_label = ROLE_LABELS[u["role"]]
    st.caption(u["title"] if u["title"] == role_label else f"{u['title']} · {role_label}")
    st.caption("PoC: role simulation — replaced by single sign-on if the platform goes to production")


def role_badge_html(role: str) -> str:
    color = ROLE_COLORS.get(role, "#607d8b")
    return (
        f'<span class="qdb-badge" style="background:{color};">'
        f"{ROLE_LABELS.get(role, role)}</span>"
    )
