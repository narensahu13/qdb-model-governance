"""Smoke test: run every page through Streamlit's AppTest and fail on exceptions.

Covers:
  - every page rendered as at least one user of each role (LOD1/LOD2/LOD3/ADMIN)
  - Model Detail for all 22 models
  - tier reconciliation (computed == stored)
  - tiering calculator combinations
  - write path end-to-end via direct data_store calls, against backed-up copies
    of the JSON files (seeded demo data is restored afterwards)

Usage:  python scripts/smoke_test.py
"""

import json
import shutil
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

PAGES = [
    "app.py",
    "views/dashboard.py",
    "views/inventory.py",
    "views/model_detail.py",
    "views/findings.py",
    "views/framework.py",
]

# One representative user per role.
ROLE_USERS = {
    "LOD1": "Ahmed Al-Kuwari",
    "LOD2": "Hassan Al-Mohannadi",
    "LOD3": "Abdulla Al-Sayed",
    "ADMIN": "Maryam Al-Kaabi",
}

failed = False


def ss_get(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except Exception:
        return default


def run_page(page: str, label: str, session: dict | None = None, query: dict | None = None):
    global failed
    at = AppTest.from_file(str(ROOT / page), default_timeout=30)
    for k, v in (session or {}).items():
        at.session_state[k] = v
    if query:
        at.query_params.update(query)
    at.run()
    if at.exception:
        failed = True
        print(f"FAIL  {label}")
        for exc in at.exception:
            print(f"      {exc.value}")
        return at
    print(f"OK    {label}")
    return at


# ---------------------------------------------------------------- pages x roles
for role, user in ROLE_USERS.items():
    for page in PAGES:
        run_page(page, f"{page} as {user} ({role})", {"current_user_name": user})

# ---------------------------------------------------------------- all models
with open(DATA / "models.json", encoding="utf-8") as f:
    models = json.load(f)

for mid in [m["model_id"] for m in models]:
    run_page("views/model_detail.py", f"Model Detail for {mid}",
             {"selected_model_id": mid})

# ---------------------------------------------------------------- validation register list ↔ detail
# List view (no md_selected_request) and detail view (request id in session).
at = run_page(
    "views/model_detail.py",
    "Validation register list (QDB-CR-001)",
    {
        "current_user_name": ROLE_USERS["LOD2"],
        "selected_model_id": "QDB-CR-001",
    },
)
if at is not None and not at.exception:
    if ss_get(at, "md_selected_request"):
        failed = True
        print("FAIL  Validation register list unexpectedly opened a detail")
    else:
        print("OK    Validation register stays on list without selection")

at = run_page(
    "views/model_detail.py",
    "Validation register detail (VAL-001)",
    {
        "current_user_name": ROLE_USERS["LOD2"],
        "selected_model_id": "QDB-CR-001",
        "md_selected_request": "VAL-001",
    },
)
if at is not None and not at.exception:
    if ss_get(at, "md_selected_request") != "VAL-001":
        failed = True
        print(f"FAIL  Validation register detail lost selection "
              f"(got {ss_get(at, 'md_selected_request')!r})")
    else:
        # Back to list button should be present in detail mode.
        back_btns = [b for b in at.button if "Back to list" in (b.label or "")]
        if not back_btns:
            failed = True
            print("FAIL  Validation register detail missing Back to list")
        else:
            back_btns[0].click().run()
            if at.exception:
                failed = True
                print("FAIL  Back to list raised")
                for exc in at.exception:
                    print(f"      {exc.value}")
            elif ss_get(at, "md_selected_request"):
                failed = True
                print(f"FAIL  Back to list did not clear selection "
                      f"(got {ss_get(at, 'md_selected_request')!r})")
            else:
                print("OK    Validation register Back to list returns to register")

at = run_page(
    "views/model_detail.py",
    "Validation register detail open MC (MC-001 on QDB-CR-002)",
    {
        "current_user_name": ROLE_USERS["LOD1"],
        "selected_model_id": "QDB-CR-002",
        "md_selected_request": "MC-001",
    },
)

# Stale selection for another model must not crash (cleared on model scope).
at = run_page(
    "views/model_detail.py",
    "Validation register stale selection cleared on model change",
    {
        "current_user_name": ROLE_USERS["LOD2"],
        "selected_model_id": "QDB-CR-001",
        "md_selected_request": "MC-001",  # belongs to QDB-CR-002
        "_md_req_model": "QDB-CR-002",
    },
)
if at is not None and not at.exception:
    # Model is QDB-CR-001; MC-001 is not on this model → cleared.
    if ss_get(at, "md_selected_request") == "MC-001":
        failed = True
        print("FAIL  Stale request selection was kept for the wrong model")
    else:
        print("OK    Stale request selection cleared for model mismatch")

# ---------------------------------------------------------------- tiering
from tiering import compute_tier

for m in models:
    computed = compute_tier(**m["tier_scores"])["tier"]
    if computed != m["tier"]:
        failed = True
        print(f"FAIL  Tier reconciliation for {m['model_id']}: "
              f"stored={m['tier']} computed={computed} scores={m['tier_scores']}")
    else:
        print(f"OK    Tier reconciliation for {m['model_id']} (Tier {computed})")

# Tiering calculator on the Framework page: exercise rating combinations.
for mat, comp, reg in [
    ("High", "High", "High"),
    ("Low", "Low", "Low"),
    ("Medium", "High", "Medium"),
    ("Low", "High", "Medium"),
    ("High", "Low", "Low"),
]:
    at = AppTest.from_file(str(ROOT / "views/framework.py"), default_timeout=30)
    at.run()
    at.selectbox(key="calc_materiality").select(mat)
    at.selectbox(key="calc_complexity").select(comp)
    at.selectbox(key="calc_regulatory").select(reg)
    at.run()
    if at.exception:
        failed = True
        print(f"FAIL  Tiering calculator for {mat}/{comp}/{reg}")
        for exc in at.exception:
            print(f"      {exc.value}")
    else:
        print(f"OK    Tiering calculator for {mat}/{comp}/{reg}")

# ---------------------------------------------------------------- write paths
# Exercised via direct data_store calls. The JSON files are backed up first and
# restored afterwards so the seeded demo data is never polluted.
WRITE_FILES = ["models.json", "validations.json", "issues.json",
               "validation_requests.json", "evidence.json", "audit_log.json"]
backups = {}
for name in WRITE_FILES:
    backups[name] = (DATA / name).read_bytes()

created_evidence_files = []

try:
    import streamlit as st

    import auth
    import data_store

    def check(label, condition):
        global failed
        if condition:
            print(f"OK    {label}")
        else:
            failed = True
            print(f"FAIL  {label}")

    # ---- raise finding (FND) as LOD2
    st.session_state["current_user_name"] = ROLE_USERS["LOD2"]
    new_id = data_store.add_issue({
        "model_id": "QDB-CR-001",
        "severity": "Low",
        "title": "SMOKE TEST issue",
        "description": "Temporary issue created by the smoke test.",
        "remediation": "None — will be rolled back.",
        "owner": "Ahmed Al-Kuwari (Head of Credit Risk)",
        "due_date": "2027-01-31",
    })
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    rec = next(i for i in reqs if i["request_id"] == new_id)
    check(f"Write path: FND {new_id} raised by LOD2",
          rec["type"] == "FND"
          and rec["initiated_by"] == ROLE_USERS["LOD2"] and rec["initiated_by_role"] == "LOD2"
          and rec["status"] == "Open" and rec["thread"] == [])

    # ---- respond as LOD1
    st.session_state["current_user_name"] = ROLE_USERS["LOD1"]
    data_store.add_issue_response(new_id, "First-line response from smoke test.")
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    rec = next(i for i in reqs if i["request_id"] == new_id)
    check("Write path: LOD1 response recorded on FND",
          len(rec["thread"]) == 1 and rec["thread"][0]["role"] == "LOD1"
          and rec["status"] == "In Progress")

    # ---- permission checks through auth
    check("Permissions: LOD1 can initiate MC / VAL",
          auth.can_initiate("MC") and auth.can_initiate("VAL"))
    check("Permissions: LOD1 cannot initiate FND",
          not auth.can_initiate("FND"))
    check("Permissions: LOD1 cannot close a LOD2-raised finding",
          not auth.can_close_issue("LOD2"))
    st.session_state["current_user_name"] = ROLE_USERS["LOD2"]
    check("Permissions: LOD2 can close its own FND", auth.can_close_issue("LOD2"))
    check("Permissions: LOD2 can initiate MC / VAL / FND",
          auth.can_initiate("MC") and auth.can_initiate("VAL") and auth.can_initiate("FND"))
    st.session_state["current_user_name"] = ROLE_USERS["LOD3"]
    check("Permissions: LOD3 can initiate VAL / FND",
          auth.can_initiate("VAL") and auth.can_initiate("FND"))
    check("Permissions: LOD3 cannot initiate MC", not auth.can_initiate("MC"))
    st.session_state["current_user_name"] = ROLE_USERS["LOD2"]

    # ---- close as the raiser (LOD2)
    data_store.close_issue(new_id, "Closed by smoke test.")
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    rec = next(i for i in reqs if i["request_id"] == new_id)
    check("Write path: FND closed by raiser with closure comment",
          rec["status"] == "Closed" and rec["closed_date"] is not None
          and rec["thread"][-1]["text"].startswith("[Closure]"))

    # ---- closed request rejects evidence upload
    closed_blocked = False
    try:
        data_store.register_evidence(
            "QDB-CR-001", "validation_request", new_id, "should_fail.txt",
            b"nope", "Document", "Should be blocked.",
        )
    except ValueError:
        closed_blocked = True
    check("Write path: closed request rejects evidence upload", closed_blocked)

    # ---- record validation as LOD2 (schedule must roll forward)
    vid = data_store.add_validation("QDB-CR-001", {
        "date": "2026-09-26",
        "type": "Periodic (annual/biennial)",
        "outcome": "Fit for Purpose",
        "validator": ROLE_USERS["LOD2"],
        "tests": ["Discriminatory power (Gini/KS)"],
        "summary": "Smoke test validation.",
    })
    ms = json.loads((DATA / "models.json").read_text(encoding="utf-8"))
    m1 = next(m for m in ms if m["model_id"] == "QDB-CR-001")
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    vrec = next(v for v in reqs if v.get("request_id") == vid)
    check("Write path: VAL request closed with schedule updated",
          vrec["type"] == "VAL" and vrec["status"] == "Closed"
          and vrec["outcome"] == "Fit for Purpose"
          and m1["last_validation"] == "2026-09-26"
          and m1["next_validation_due"] == "2027-09-26")

    # ---- material change as LOD1 -> status In Validation + MC request
    st.session_state["current_user_name"] = ROLE_USERS["LOD1"]
    change_id = data_store.add_change_entry("QDB-CR-001", {
        "date": "2026-09-26",
        "version": "9.9-smoke",
        "description": "Smoke test material change.",
        "author": ROLE_USERS["LOD1"],
        "classification": "Material",
        "justification": "Methodology change (test).",
    })
    ms = json.loads((DATA / "models.json").read_text(encoding="utf-8"))
    m1 = next(m for m in ms if m["model_id"] == "QDB-CR-001")
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    mc = [r for r in reqs if r["type"] == "MC" and r["model_id"] == "QDB-CR-001"
          and r["status"] != "Closed" and "9.9-smoke" in r.get("title", "")
          and r.get("materiality") == "Material"]
    check("Write path: material change sets In Validation + opens MC",
          m1["status"] == "In Validation" and m1["pending_revalidation"] is True
          and m1["change_log"][-1]["classification"] == "Material"
          and m1["change_log"][-1]["change_id"] == change_id
          and len(mc) >= 1)

    # ---- evidence attached in context (validation_request + change + request_response)
    eid_val = data_store.register_evidence(
        "QDB-CR-001", "validation_request", mc[0]["request_id"], "smoke_val.txt",
        b"smoke validation evidence", "Document", "Smoke val evidence.",
    )
    eid_chg = data_store.register_evidence(
        "QDB-CR-001", "change", change_id, "smoke_chg.txt",
        b"smoke change evidence", "Code", "Smoke change evidence.",
    )
    st.session_state["current_user_name"] = ROLE_USERS["LOD2"]
    open_id = data_store.add_issue({
        "model_id": "QDB-CR-001",
        "severity": "Low",
        "title": "SMOKE evidence issue",
        "description": "Temporary.",
        "remediation": "None.",
        "owner": "Ahmed Al-Kuwari (Head of Credit Risk)",
        "due_date": "2027-01-31",
    })
    st.session_state["current_user_name"] = ROLE_USERS["LOD1"]
    resp_id = data_store.peek_next_response_id(open_id)
    eid_resp = data_store.register_evidence(
        "QDB-CR-001", "request_response", resp_id, "smoke_resp.txt",
        b"smoke response evidence", "Document", "Smoke response evidence.",
    )
    data_store.add_issue_response(open_id, "Response with evidence.", [eid_resp])
    reg = json.loads((DATA / "evidence.json").read_text(encoding="utf-8"))
    for eid in (eid_val, eid_chg, eid_resp):
        ev = next(e for e in reg if e["evidence_id"] == eid)
        created_evidence_files.append(ROOT / ev["stored_path"])
    check("Write path: evidence linked to request/change/response",
          all((ROOT / next(e for e in reg if e["evidence_id"] == eid)["stored_path"]).exists()
              for eid in (eid_val, eid_chg, eid_resp))
          and next(e for e in reg if e["evidence_id"] == eid_val)["linked_type"] == "validation_request"
          and next(e for e in reg if e["evidence_id"] == eid_chg)["linked_type"] == "change"
          and next(e for e in reg if e["evidence_id"] == eid_resp)["linked_type"] == "request_response")
    reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    open_rec = next(i for i in reqs if i["request_id"] == open_id)
    check("Write path: thread carries response_id and evidence_ids",
          open_rec["thread"][0].get("response_id") == resp_id
          and open_rec["thread"][0]["evidence_ids"] == [eid_resp])

    seed_reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
    check("Schema: validation_requests carry typed request_id",
          all(r.get("request_id") and r.get("type") in auth.REQUEST_TYPES for r in seed_reqs))
    check("Schema: change_log entries carry change_id",
          all("change_id" in c for m in json.loads((DATA / "models.json").read_text(encoding="utf-8"))
              for c in m.get("change_log", [])))

    # ---- audit trail captured everything above
    log = json.loads((DATA / "audit_log.json").read_text(encoding="utf-8"))
    actions = [e["action"] for e in log[-20:]]
    check("Write path: audit trail captured workflow events",
          {"raise_issue", "respond_issue", "close_issue", "add_validation",
           "record_change", "upload_evidence"}.issubset(set(actions))
          or {"initiate_fnd", "respond_request", "close_request", "initiate_val",
              "record_change", "upload_evidence"}.issubset(set(actions)))
finally:
    # Restore the seeded demo data exactly and remove test artefacts.
    for name, blob in backups.items():
        (DATA / name).write_bytes(blob)
    for p in created_evidence_files:
        p.unlink(missing_ok=True)
    print("OK    Demo data restored after write tests")

# ---------------------------------------------------------------- fresh sessions + deep links
# Brand-new tab = empty session state. Every page must render, and
# /model_detail?model=<id> must select that model without a pre-set user.
for page in PAGES:
    at = run_page(page, f"Fresh session: {page}", session=None)
    if page == "views/model_detail.py" and at is not None and not at.exception:
        if ss_get(at, "current_user_name") != ROLE_USERS["ADMIN"]:
            failed = True
            print(f"FAIL  Fresh session self-initialized user on {page}: "
                  f"got {ss_get(at, 'current_user_name')!r}")
        else:
            print("OK    Fresh session self-initialized default user")

at = run_page(
    "views/model_detail.py",
    "Deep link ?model=QDB-CR-004 (empty session)",
    query={"model": "QDB-CR-004"},
)
if at is not None and not at.exception:
    if ss_get(at, "selected_model_id") != "QDB-CR-004":
        failed = True
        print(f"FAIL  Deep link did not select QDB-CR-004 "
              f"(got {ss_get(at, 'selected_model_id')!r})")
    else:
        print("OK    Deep link selected QDB-CR-004")
    if ss_get(at, "current_user_name") != ROLE_USERS["ADMIN"]:
        failed = True
        print("FAIL  Deep link did not self-initialize default user")
    else:
        print("OK    Deep link self-initialized default user")

at = run_page(
    "views/model_detail.py",
    "Deep link ?model=DOES-NOT-EXIST (empty session)",
    query={"model": "DOES-NOT-EXIST"},
)
if at is not None and not at.exception:
    selected = ss_get(at, "selected_model_id")
    if selected == "DOES-NOT-EXIST":
        failed = True
        print("FAIL  Invalid deep link was accepted as the selected model")
    else:
        print(f"OK    Invalid deep link fell back to {selected}")

at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
at.query_params["model"] = "QDB-CR-001"
at.switch_page("views/model_detail.py")
at.run()
if at.exception:
    failed = True
    print("FAIL  app.py + switch_page + ?model=QDB-CR-001")
    for exc in at.exception:
        print(f"      {exc.value}")
else:
    print("OK    app.py + switch_page + ?model=QDB-CR-001")
    if ss_get(at, "selected_model_id") != "QDB-CR-001":
        failed = True
        print(f"FAIL  app.py deep link selected {ss_get(at, 'selected_model_id')!r}")
    else:
        print("OK    app.py deep link selected QDB-CR-001")

# Fresh session for each role via app.py and each view (no selected_model_id).
for role, user in ROLE_USERS.items():
    run_page("app.py", f"Fresh-ish app.py as {user} ({role})",
             {"current_user_name": user})
    run_page("views/model_detail.py", f"Fresh model_detail as {user} ({role})",
             {"current_user_name": user})

# ---------------------------------------------------------------- form submits (backup / restore)
form_backups = {}
for name in WRITE_FILES:
    form_backups[name] = (DATA / name).read_bytes()
form_evidence_files = []

try:
    # LOD2 records a completed VAL through the Initiate request form
    at = AppTest.from_file(str(ROOT / "views/model_detail.py"), default_timeout=30)
    at.session_state["current_user_name"] = ROLE_USERS["LOD2"]
    at.session_state["selected_model_id"] = "QDB-CR-001"
    at.run()
    if at.exception:
        failed = True
        print("FAIL  Form setup (validation) raised")
        for exc in at.exception:
            print(f"      {exc.value}")
    else:
        at.selectbox(key="ir_type").select("VAL — Validation")
        at.run()
        at.text_input(key="ir_title").input("SMOKE VAL form")
        at.text_area(key="ir_desc").input("Smoke-test validation via AppTest.")
        at.multiselect(key="val_tests").select("Documentation review")
        at.button("ir_submit").click().run()
        if at.exception:
            failed = True
            print("FAIL  VAL initiate form submit")
            for exc in at.exception:
                print(f"      {exc.value}")
        else:
            recs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
            found = any(v.get("title") == "SMOKE VAL form" for v in recs)
            if found:
                print("OK    VAL initiate form submit (LOD2)")
            else:
                failed = True
                print("FAIL  VAL initiate form submit did not persist a record")

    # LOD2 raises a FND
    at = AppTest.from_file(str(ROOT / "views/model_detail.py"), default_timeout=30)
    at.session_state["current_user_name"] = ROLE_USERS["LOD2"]
    at.session_state["selected_model_id"] = "QDB-CR-001"
    at.run()
    if not at.exception:
        at.selectbox(key="ir_type").select("FND — Finding")
        at.run()
        at.text_input(key="ir_title").input("SMOKE form issue")
        at.text_area(key="ir_desc").input("Raised by AppTest.")
        at.text_area(key="ir_rem").input("No action — will be rolled back.")
        at.button("ir_submit").click().run()
        if at.exception:
            failed = True
            print("FAIL  FND initiate form submit")
            for exc in at.exception:
                print(f"      {exc.value}")
        else:
            recs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
            found = any(i.get("title") == "SMOKE form issue" and i.get("type") == "FND" for i in recs)
            print("OK    FND initiate form submit (LOD2)" if found
                  else "FAIL  FND initiate form submit did not persist")
            if not found:
                failed = True

    # LOD1 records a non-material change (opens MC with Non-material)
    at = AppTest.from_file(str(ROOT / "views/model_detail.py"), default_timeout=30)
    at.session_state["current_user_name"] = ROLE_USERS["LOD1"]
    at.session_state["selected_model_id"] = "QDB-CR-001"
    at.run()
    if not at.exception:
        at.text_input(key="chg_version").input("9.8-smoke")
        at.selectbox(key="chg_class").select("Non-material")
        at.text_area(key="chg_desc").input("Smoke-test non-material change.")
        at.text_area(key="chg_just").input("Cosmetic — AppTest.")
        at.button("chg_submit").click().run()
        if at.exception:
            failed = True
            print("FAIL  Record-change form submit")
            for exc in at.exception:
                print(f"      {exc.value}")
        else:
            ms = json.loads((DATA / "models.json").read_text(encoding="utf-8"))
            m1 = next(m for m in ms if m["model_id"] == "QDB-CR-001")
            found = any(e.get("version") == "9.8-smoke" for e in m1.get("change_log", []))
            reqs = json.loads((DATA / "validation_requests.json").read_text(encoding="utf-8"))
            mc_nm = any(
                r.get("type") == "MC" and r.get("materiality") == "Non-material"
                and "9.8-smoke" in r.get("title", "")
                for r in reqs
            )
            print("OK    Record-change form submit (LOD1 + MC Non-material)" if found and mc_nm
                  else "FAIL  Record-change form submit did not persist")
            if not (found and mc_nm):
                failed = True

    # LOD3 records an audit review
    at = AppTest.from_file(str(ROOT / "views/model_detail.py"), default_timeout=30)
    at.session_state["current_user_name"] = ROLE_USERS["LOD3"]
    at.session_state["selected_model_id"] = "QDB-CR-001"
    at.run()
    if not at.exception:
        at.text_area(key="aud_scope").input("Smoke-test audit scope.")
        at.button("aud_submit").click().run()
        if at.exception:
            failed = True
            print("FAIL  Audit-review form submit")
            for exc in at.exception:
                print(f"      {exc.value}")
        else:
            ms = json.loads((DATA / "models.json").read_text(encoding="utf-8"))
            m1 = next(m for m in ms if m["model_id"] == "QDB-CR-001")
            found = any(a.get("scope") == "Smoke-test audit scope." for a in m1.get("audit_reviews", []))
            print("OK    Audit-review form submit (LOD3)" if found
                  else "FAIL  Audit-review form submit did not persist")
            if not found:
                failed = True

    # Dashboard Open button (same-tab navigation) must not exception
    at = AppTest.from_file(str(ROOT / "views/dashboard.py"), default_timeout=30)
    at.run()
    if at.exception:
        failed = True
        print("FAIL  Fresh dashboard before Open click")
    elif at.button:
        at.button[0].click().run()
        if at.exception:
            failed = True
            print("FAIL  Dashboard Open button")
            for exc in at.exception:
                print(f"      {exc.value}")
        else:
            print("OK    Dashboard Open button")
    else:
        print("OK    Dashboard Open button (none rendered)")

finally:
    for name, blob in form_backups.items():
        (DATA / name).write_bytes(blob)
    for p in form_evidence_files:
        p.unlink(missing_ok=True)
    print("OK    Demo data restored after form tests")

sys.exit(1 if failed else 0)
