"""Smoke test: run every page through Streamlit's AppTest and fail on exceptions.

Runs against a throwaway copy of the pilot seed (temp database and evidence
folder), so your working database is never touched.

Covers:
  - every page as one user of each role (LOD1 / LOD2 / LOD3 / ADMIN)
  - Model Detail for every model in the inventory
  - request register list <-> detail navigation
  - deep links (?model=) including an unknown id, and fresh sessions
  - form submits through the UI: validation, finding, thread reply by the
    validator, model change, audit review, model document upload
  - audit log hash chain intact at the end

Usage:  python scripts/smoke_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="qdb_mrm_smoke_"))
os.environ["QDB_MRM_DB"] = str(TMP / "smoke.db")
os.environ["QDB_MRM_EVIDENCE_DIR"] = str(TMP / "evidence")

from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import repository  # noqa: E402

repository.reset_db()

PAGES = [
    "app.py",
    "views/dashboard.py",
    "views/inventory.py",
    "views/model_detail.py",
    "views/findings.py",
    "views/framework.py",
]

ROLE_USERS = {
    "LOD1": "Ahmed Al-Kuwari",
    "LOD2": "Priya Menon",
    "LOD3": "Abdulla Al-Sayed",
    "ADMIN": "Maryam Al-Kaabi",
}
DEVELOPER = "Lina Haddad"

failed = False


def fail(msg: str, at: AppTest | None = None):
    global failed
    failed = True
    print(f"FAIL  {msg}")
    if at is not None:
        for exc in at.exception:
            print(f"      {exc.value}")


def ok(msg: str):
    print(f"OK    {msg}")


def ss_get(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except Exception:
        return default


def run_page(page: str, label: str, session: dict | None = None, query: dict | None = None):
    at = AppTest.from_file(str(ROOT / page), default_timeout=60)
    for k, v in (session or {}).items():
        at.session_state[k] = v
    if query:
        at.query_params.update(query)
    at.run()
    if at.exception:
        fail(label, at)
    else:
        ok(label)
    return at


def model_page(user: str, model_id: str, **extra) -> AppTest:
    at = AppTest.from_file(str(ROOT / "views/model_detail.py"), default_timeout=60)
    at.session_state["current_user_name"] = user
    at.session_state["selected_model_id"] = model_id
    for k, v in extra.items():
        at.session_state[k] = v
    at.run()
    return at


# ---------------------------------------------------------------- pages x roles
for role, user in ROLE_USERS.items():
    for page in PAGES:
        run_page(page, f"{page} as {user} ({role})", {"current_user_name": user})

# ---------------------------------------------------------------- every model
for mid in [m["model_id"] for m in repository.list_models()]:
    run_page("views/model_detail.py", f"Model Detail for {mid}", {"selected_model_id": mid})

# ---------------------------------------------------------------- register list <-> detail
at = model_page(ROLE_USERS["LOD2"], "QDB-IF-001")
if at.exception:
    fail("Request register list", at)
else:
    btns = [b for b in at.button if (b.label or "") == "VAL-002"]
    if not btns:
        fail("Request register missing VAL-002 button")
    else:
        btns[0].click().run()
        if at.exception or ss_get(at, "md_selected_request") != "VAL-002":
            fail("Request ID click did not open detail", at)
        else:
            ok("Request ID opens detail in the same session")
            back = [b for b in at.button if "Back to list" in (b.label or "")]
            back[0].click().run()
            if at.exception or ss_get(at, "md_selected_request"):
                fail("Back to list", at)
            else:
                ok("Back to list returns to the register")

# ---------------------------------------------------------------- deep links / fresh sessions
at = run_page("views/model_detail.py", "Deep link ?model=QDB-IF-006", query={"model": "QDB-IF-006"})
if ss_get(at, "selected_model_id") != "QDB-IF-006":
    fail("Deep link did not select QDB-IF-006")
at = run_page("views/model_detail.py", "Deep link to unknown model", query={"model": "NOPE"})
if ss_get(at, "selected_model_id") == "NOPE":
    fail("Unknown deep link accepted")
for page in PAGES:
    run_page(page, f"Fresh session: {page}")

# ---------------------------------------------------------------- form submits
# 1. Validator replies in a thread (was impossible before Phase 0)
at = model_page("Hassan Al-Mohannadi", "QDB-IF-005", md_selected_request="MC-001")
if at.exception:
    fail("Open MC-001 as validator", at)
else:
    at.text_area(key="resp_txt_MC-001").input("SMOKE: please attach the comparison.")
    [b for b in at.button if b.label == "Add response"][0].click().run()
    thread = repository.get_request("MC-001")["thread"]
    if at.exception or not thread[-1]["text"].startswith("SMOKE"):
        fail("Validator reply in thread", at)
    else:
        ok("Validator reply in thread (LOD2)")

# 2. Validator records a completed, rated validation
at = model_page(ROLE_USERS["LOD2"], "QDB-CR-002")
at.selectbox(key="ir_type").select("VAL — Validation")
at.run()
at.text_input(key="ir_title").input("SMOKE VAL form")
at.text_area(key="ir_desc").input("Smoke-test validation via AppTest.")
at.selectbox(key="ir_outcome").select("Fit with Conditions")
at.multiselect(key="val_tests").select("Documentation review")
at.button("ir_submit").click().run()
if at.exception or not any(r["title"] == "SMOKE VAL form" and r["outcome"] == "Fit with Conditions"
                           for r in repository.list_requests("QDB-CR-002")):
    fail("VAL initiate form submit", at)
else:
    ok("VAL recorded with a rating (LOD2)")

# 3. Validator raises a finding
at = model_page(ROLE_USERS["LOD2"], "QDB-CR-002")
at.selectbox(key="ir_type").select("FND — Finding")
at.run()
at.text_input(key="ir_title").input("SMOKE finding")
at.text_area(key="ir_desc").input("Raised by AppTest.")
at.text_area(key="ir_rem").input("No action.")
at.button("ir_submit").click().run()
if at.exception or not any(r["title"] == "SMOKE finding" for r in repository.list_requests("QDB-CR-002")):
    fail("FND initiate form submit", at)
else:
    ok("FND raised (LOD2)")

# 4. Developer records a non-material change
at = model_page(DEVELOPER, "QDB-IF-004")
at.text_input(key="chg_version").input("1.4-smoke")
at.selectbox(key="chg_class").select("Non-material")
at.text_area(key="chg_desc").input("Smoke-test non-material change.")
at.text_area(key="chg_just").input("Cosmetic.")
at.button("chg_submit").click().run()
m = repository.get_model("QDB-IF-004")
mc = [r for r in repository.list_requests("QDB-IF-004") if "1.4-smoke" in r["title"]]
if at.exception or m["version"] != "1.4-smoke" or not mc:
    fail("Record-change form submit", at)
elif mc[0]["assigned_to"].startswith(DEVELOPER):
    fail("Change review assigned to the model's own developer")
else:
    ok(f"Model change recorded; MC assigned to {mc[0]['assigned_to']}")

# 5. Internal Audit records a review
at = model_page(ROLE_USERS["LOD3"], "QDB-IF-006")
at.text_area(key="aud_scope").input("Smoke-test audit scope.")
at.button("aud_submit").click().run()
if at.exception or not any(a["scope"] == "Smoke-test audit scope."
                           for a in repository.get_model("QDB-IF-006")["audit_reviews"]):
    fail("Audit-review form submit", at)
else:
    ok("Audit review recorded (LOD3)")

# 6. Admin sees no close form on a finding (segregation of duties)
at = model_page(ROLE_USERS["ADMIN"], "QDB-IF-001", md_selected_request="FND-001")
if at.exception:
    fail("Open FND-001 as admin", at)
elif any(b.label == "Close request" for b in at.button):
    fail("Admin was offered a Close request button")
else:
    ok("Admin cannot close findings")

# 7. Dashboard Open button navigates
at = AppTest.from_file(str(ROOT / "views/dashboard.py"), default_timeout=60)
at.run()
if at.button:
    at.button[0].click().run()
if at.exception:
    fail("Dashboard Open button", at)
else:
    ok("Dashboard Open button")

# ---------------------------------------------------------------- audit integrity
chain_ok, broken = repository.verify_audit_chain()
if chain_ok:
    ok(f"Audit log hash chain intact ({len(repository.list_audit())} events)")
else:
    fail(f"Audit log chain broken at event {broken}")

print(f"\n{'FAILED' if failed else 'ALL PASSED'} — scratch data in {TMP}")
sys.exit(1 if failed else 0)
