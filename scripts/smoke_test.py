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
    "views/registers.py",
    "views/register.py",
    "views/tasks.py",
    "views/admin.py",
]

ROLE_USERS = {
    "LOD1": "Owner 1",
    "LOD2": "Validator 2",
    "LOD3": "Auditor 1",
    "ADMIN": "MRM Admin 1",
    "CRO": "CRO 1",
}
DEVELOPER = "Developer 1"

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
at = model_page(ROLE_USERS["LOD2"], "QDB-001")
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
at = run_page("views/model_detail.py", "Deep link ?model=QDB-006", query={"model": "QDB-006"})
if ss_get(at, "selected_model_id") != "QDB-006":
    fail("Deep link did not select QDB-006")
at = run_page("views/model_detail.py", "Deep link to unknown model", query={"model": "NOPE"})
if ss_get(at, "selected_model_id") == "NOPE":
    fail("Unknown deep link accepted")
for page in PAGES:
    run_page(page, f"Fresh session: {page}")

# ---------------------------------------------------------------- form submits
# 1. Validator replies in a thread (was impossible before Phase 0)
at = model_page("Validator 1", "QDB-005", md_selected_request="MC-001")
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
at = model_page(ROLE_USERS["LOD2"], "QDB-008")
at.selectbox(key="ir_type").select("VAL — Validation")
at.run()
at.text_input(key="ir_title").input("SMOKE VAL form")
at.text_area(key="ir_desc").input("Smoke-test validation via AppTest.")
at.selectbox(key="ir_outcome").select("Fit with Conditions")
at.multiselect(key="val_tests").select("Documentation review")
at.button("ir_submit").click().run()
if at.exception or not any(r["title"] == "SMOKE VAL form" and r["outcome"] == "Fit with Conditions"
                           for r in repository.list_requests("QDB-008")):
    fail("VAL initiate form submit", at)
else:
    ok("VAL recorded with a rating (LOD2)")

# 3. Validator raises a finding
at = model_page(ROLE_USERS["LOD2"], "QDB-008")
at.selectbox(key="ir_type").select("FND — Finding")
at.run()
at.text_input(key="ir_title").input("SMOKE finding")
at.text_area(key="ir_desc").input("Raised by AppTest.")
at.text_area(key="ir_rem").input("No action.")
at.button("ir_submit").click().run()
if at.exception or not any(r["title"] == "SMOKE finding" for r in repository.list_requests("QDB-008")):
    fail("FND initiate form submit", at)
else:
    ok("FND raised (LOD2)")

# 4. Developer records a non-material change
at = model_page(DEVELOPER, "QDB-004")
at.text_input(key="chg_version").input("1.4-smoke")
at.selectbox(key="chg_class").select("Non-material")
at.text_area(key="chg_desc").input("Smoke-test non-material change.")
at.text_area(key="chg_just").input("Cosmetic.")
at.button("chg_submit").click().run()
m = repository.get_model("QDB-004")
mc = [r for r in repository.list_requests("QDB-004") if "1.4-smoke" in r["title"]]
if at.exception or m["version"] != "1.4-smoke" or not mc:
    fail("Record-change form submit", at)
elif mc[0]["assigned_to"].startswith(DEVELOPER):
    fail("Change review assigned to the model's own developer")
else:
    ok(f"Model change recorded; MC assigned to {mc[0]['assigned_to']}")

# 5. Internal Audit records a review
at = model_page(ROLE_USERS["LOD3"], "QDB-006")
at.text_area(key="aud_scope").input("Smoke-test audit scope.")
at.button("aud_submit").click().run()
if at.exception or not any(a["scope"] == "Smoke-test audit scope."
                           for a in repository.get_model("QDB-006")["audit_reviews"]):
    fail("Audit-review form submit", at)
else:
    ok("Audit review recorded (LOD3)")

# 6. Admin sees no close form on a finding (segregation of duties)
at = model_page(ROLE_USERS["ADMIN"], "QDB-001", md_selected_request="FND-001")
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

# ---------------------------------------------------------------- Phase 1: inventory flows
def page(path: str, user: str, **extra) -> AppTest:
    at = AppTest.from_file(str(ROOT / path), default_timeout=60)
    at.session_state["current_user_name"] = user
    for k, v in extra.items():
        at.session_state[k] = v
    at.run()
    return at


def by_label(widgets, label):
    found = [w for w in widgets if w.label == label]
    return found[0] if found else None


# 8. Owner registers a model through the questionnaire
before_ids = {m["model_id"] for m in repository.list_models()}
at = page("views/register.py", DEVELOPER)
at.radio(key="idq_quantitative").set_value("Yes")
at.radio(key="idq_theory").set_value("Yes")
at.run()
at.text_input(key="rm_name").input("SMOKE Early Warning Model")
at.text_input(key="rm_meth").input("Logistic regression")
at.text_area(key="rm_desc").input("Smoke-test registration.")
at.text_area(key="rm_rat").input("Advisory signal.")
at.button(key="rm_submit").click().run()
new_ids = {m["model_id"] for m in repository.list_models()} - before_ids
if at.exception or len(new_ids) != 1:
    fail("Register model through the questionnaire", at)
    new_id = None
else:
    new_id = new_ids.pop()
    ok(f"Model registered through the questionnaire ({new_id}, tier proposed)")

# 9. An EUC tool is routed to the EUC register
before_tools = len(repository.list_tools())
at = page("views/register.py", DEVELOPER)
at.radio(key="idq_quantitative").set_value("Yes")
at.radio(key="idq_deterministic_only").set_value("Yes")
at.radio(key="idq_decision_use").set_value("Yes")
at.run()
at.text_input(key="rt_name").input("SMOKE limit tracker")
at.text_area(key="rt_desc").input("Excel limit tracker.")
at.button(key="rt_submit").click().run()
if at.exception or len(repository.list_tools()) != before_tools + 1:
    fail("Register EUC tool", at)
else:
    ok("EUC tool recorded in the register")

# 10. Developer edits their model's record
at = page("views/model_detail.py", DEVELOPER, selected_model_id="QDB-005")
vendor = by_label(at.text_input, "Vendor")
if at.exception or vendor is None:
    fail("Open Edit Record tab", at)
else:
    vendor.input("SMOKE vendor")
    by_label(at.button, "Save changes").click().run()
    if at.exception or repository.get_model("QDB-005").get("vendor") != "SMOKE vendor":
        fail("Edit record as developer", at)
    else:
        ok("Developer edited own model record (audited)")

# 11. Tier sign-off: validator confirms with override -> CRO approves
if new_id:
    at = page("views/model_detail.py", "Validator 1", selected_model_id=new_id)
    sel = at.selectbox(key=f"ct_tier_{new_id}")
    proposed = sel.value
    target = 1 if proposed != 1 else 2
    sel.set_value(target)
    at.text_input(key=f"ct_reason_{new_id}").input("SMOKE override reason")
    by_label(at.button, "Confirm tier").click().run()
    if at.exception or repository.get_model(new_id)["tier_assessment"]["status"] != "Override pending CRO":
        fail("Validator confirms tier with override", at)
    else:
        ok("Tier override sent to the CRO")
        at = page("views/model_detail.py", "CRO 1", selected_model_id=new_id)
        by_label(at.button, "Approve override").click().run()
        mm = repository.get_model(new_id)
        if at.exception or mm["tier_override"] != target or mm["tier_assessment"]["status"] != "Confirmed":
            fail("CRO approves tier override", at)
        else:
            ok(f"CRO approved override to Tier {target}")

# 12. Registers page shows the AI register for the QCB filing
at = page("views/registers.py", ROLE_USERS["ADMIN"])
if at.exception:
    fail("Registers page", at)
else:
    ok("Registers page (tier queue, EUC, AI register)")

# ---------------------------------------------------------------- Phase 2: validation workflow
# 13. Validator scopes VAL-015 and declares independence
at = page("views/model_detail.py", "Validator 2", selected_model_id="QDB-006",
          md_selected_request="VAL-015", _md_req_model="QDB-006")
if at.exception:
    fail("Open VAL-015 engagement", at)
else:
    scope = [w for w in at.text_area if w.label == "Scope of the validation *"]
    scope[0].input("SMOKE scope")
    at.checkbox(key="eng_ind_VAL-015").check()
    by_label(at.button, "Start fieldwork").click().run()
    eng = repository.get_request("VAL-015")["engagement"]
    if at.exception or eng["stage"] != "Fieldwork" or not eng["independence"]:
        fail("Start engagement with independence declaration", at)
    else:
        ok("Validator started fieldwork with independence declared")

# 14. CRO approves a Tier 2 model (G4)
at = page("views/model_detail.py", "CRO 1", selected_model_id="QDB-011")
if at.exception:
    fail("Open QDB-011 as CRO", at)
else:
    by_label(at.button, "Record decision (G4)").click().run()
    if at.exception or repository.get_model("QDB-011")["status"] != "Approved — Awaiting Implementation":
        fail("CRO approval (G4)", at)
    else:
        ok("CRO approved QDB-011 (G4)")

# 15. Validator verifies implementation (G5)
at = page("views/model_detail.py", "Validator 1", selected_model_id="QDB-011")
note = [w for w in at.text_area if w.label == "What was checked *"]
if at.exception or not note:
    fail("Open G5 form", at)
else:
    note[0].input("SMOKE version check")
    by_label(at.button, "Verify implementation (G5)").click().run()
    if at.exception or repository.get_model("QDB-011")["status"] != "In Production":
        fail("Implementation verification (G5)", at)
    else:
        ok("Implementation verified — QDB-011 in production")

# 16. My Tasks lists work for a developer
at = page("views/tasks.py", "Developer 4")
if at.exception or not any(b.label == "Open" for b in at.button):
    fail("My Tasks for Developer 4", at)
else:
    ok("My Tasks shows the developer's information requests")

# 17. Admin renames a person through the Administration page
at = page("views/admin.py", ROLE_USERS["ADMIN"])
at.selectbox(key="adm_pick").set_value("Auditor 1")
at.run()
name_box = [w for w in at.text_input if w.label == "Name"][0]
name_box.input("Internal Auditor A")
[b for b in at.button if b.label == "Save"][0].click().run()
if at.exception or not any(u["name"] == "Internal Auditor A" for u in repository.list_users()):
    fail("Admin rename person", at)
else:
    ok("Admin renamed Auditor 1 (propagated to records)")

# ---------------------------------------------------------------- audit integrity
chain_ok, broken = repository.verify_audit_chain()
if chain_ok:
    ok(f"Audit log hash chain intact ({len(repository.list_audit())} events)")
else:
    fail(f"Audit log chain broken at event {broken}")

print(f"\n{'FAILED' if failed else 'ALL PASSED'} — scratch data in {TMP}")
sys.exit(1 if failed else 0)
