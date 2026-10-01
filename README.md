# QDB Model Governance Platform — Proof of Concept

A model risk management (MRM) platform for **Qatar Development Bank**: one inventory of every
model, with validation, findings, model changes, monitoring, documents and an audit trail an
auditor can rely on.

The inventory holds QDB's **pilot models** — the IFRS 9 suite (PD, LGD, EAD, staging, scenario
weights, ECL engine), the CreditLens obligor rating models, the pricing model, the scoring models
in development (transaction, credit bureau individual and corporate, combination module) and
placeholder models for liquidity, market, operational and non-financial risk. **Model names and
relationships are real; dates, exposures, metrics and findings are mock data** to be edited.
People are placeholders (Model Owner 1, Model Developer 1, Model Validator 1, Internal Auditor 1, MRM Administrator 1, CRO) —
rename them to real people on the Administration page. Models are numbered QDB-001, QDB-002 …
and can be renumbered there too.

Governance set-up (decided 30 September 2026):

- Validation by one QDB validator or an external consultant — no dedicated validation unit.
- Approval: Management Risk Committee for Tier 1; CRO for Tier 2 and Tier 3 (may delegate Tier 3).
- Validation rating scale: Fit for Purpose · Fit with Conditions · Restricted Use · Not Fit for Purpose.
- Benchmarks: Federal Reserve **SR 26-2** (April 2026, replaced SR 11-7), PRA SS1/23, and the
  **QCB Artificial Intelligence Guideline** (2024), which applies to QDB as a QCB-licensed bank.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. On first run it builds the database
(`data/qdb_mrm.db`) and the evidence folder (`data/evidence/`) from `data/seed/`.

To start again from the seed data (discarding changes made in the app):

```bash
python scripts/reset_db.py
```

### Using a dedicated evidence folder

Uploaded documents and evidence are stored as files, one sub-folder per model, with a SHA-256
fingerprint recorded at upload and re-checked on every download. Point the platform at any folder
(for example a shared drive) with environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `QDB_MRM_EVIDENCE_DIR` | `data/evidence` | Dedicated evidence folder |
| `QDB_MRM_DB` | `data/qdb_mrm.db` | SQLite database file |

## Pages

| Page | Purpose |
|---|---|
| My Tasks | Start here: everything waiting on you — information requests, reviews, sign-offs, approvals, conditions |
| Dashboard | Model risk at a glance: KPIs, tier and validation status, models needing escalation, validation calendar |
| Model Inventory | Filterable register of all models, including the AI-system flag; click a row to open the model |
| Model Detail | Overview (uses, tier sign-off), Governance & Lifecycle (version history), Validation & Findings (MC / VAL / FND threads), Performance Monitoring, Documentation & Audit (document uploads, checklist, file integrity, audit trail), Edit Record; one-click PDF factsheet |
| Findings Tracker | Bank-wide findings plus other open change and validation requests |
| Registers | Tier sign-off queue, EUC / identification register, AI register for the QCB filing (CSV export) |
| Register Model / Tool | Identification questionnaire that routes a candidate to the model inventory, the EUC register or the AI register, then captures the record and proposed tier |
| How It Works | Quick guide (who does what, the five steps), then the framework: model definition, tiering, lifecycle, governance structure, permissions, roadmap |
| Administration | MRM Administrator: rename people and roles, set accountability for all models, renumber model IDs, audit check, database backup |

## Controls built into the platform

| Control | How |
|---|---|
| Tamper-evident audit log | Append-only (database triggers block edits and deletes) and hash-chained; every change stores the record's before and after state |
| Evidence integrity | SHA-256 stored at upload and verified on download; altered or missing files are flagged |
| Independence | A model's owner or developer cannot be assigned its validation or change review |
| Segregation of duties | The MRM Administrator schedules and assigns work but cannot raise findings, close requests or record changes; findings close only by the line that raised them |
| Single source of truth | Tier, validation frequency, approval body, last validation, rating and next due date are derived, never typed |
| Rules in the data layer | Permissions and rules are enforced in `data_store.py`, not just hidden in the pages |
| Model identification | Five-question test based on SR 26-2 and the QCB AI Guideline; every decision is kept, including "not a model" |
| Tier sign-off (gate G1) | Owner proposes, MRM confirms (never the proposer), an override needs a reason and CRO approval; history kept |
| Record editing | Owners and developers edit their own models; owner, developer, validator and sponsor are assigned by the MRM Administrator only |
| Lifecycle gates G1–G5 | Tier confirmed → submitted with required documents → validation signed off → approved (Management Risk Committee for Tier 1, CRO for Tier 2/3) → implementation verified; a model cannot reach use without all five |
| Validation engagement | Scope and independence declaration, information requests answered with evidence, draft with proposed rating, owner's factual-accuracy review (7 days), sign-off; validations close only through sign-off |
| Approvals and conditions | Decisions recorded with the committee minute reference; conditions are marked met by the owner and verified by a validator or the CRO |

## Editing the model data

Models are registered and edited in the app (Register Model / Tool, and each model's Edit Record
tab). The seed files below only define the starting data; edit them and run
`python scripts/reset_db.py` to start again from a different baseline:

| File | Contents |
|---|---|
| `data/seed/models.json` | One record per model: identification, owner, developer, validator, tier scores, status, dependencies, documentation checklist, change log, audit reviews, AI-system flags |
| `data/seed/validation_requests.json` | Validation (VAL), model change (MC) and finding (FND) requests with their threads |
| `data/seed/users.json` | Users and roles for the "Acting as" selector, including the CRO (replaced by single sign-on in production) |
| `data/seed/tools.json` | EUC tools, AI tools and "not a model" decisions |
| `data/seed/evidence.json` + `data/seed/evidence/` | Seed evidence files |
| `data/seed/monitoring.csv` | Quarterly monitoring metrics with amber and red thresholds |
| `data/seed/audit_log.json` | Historical audit events |

`scripts/build_pilot_seed.py` generated the first version of these files; do not re-run it unless
you want to discard edits to the seed.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests          # rules, repository, workflows, inventory, validation workflow (58 tests)
python scripts/smoke_test.py    # every page and form through Streamlit AppTest
```

Both run against a throwaway copy of the seed, never your working database. A database from an
earlier version (before model numbering changed to QDB-001) is kept as a backup file next to
the new one and rebuilt from the seed on first start.

## Structure

```
app.py              Entry point (navigation)
views/              Dashboard, Inventory, Model Detail, Findings, Registers, Register, Framework
config.py           Database and evidence-folder locations
repository.py       SQLite storage, audit log with hash chain (no Streamlit dependency)
governance.py       QDB rules: rating scale, approval bodies, frequencies, independence
tiering.py          Rule-based tiering engine
data_loader.py      Read side, with derived fields
data_store.py       Write side: one transaction per change, audit before/after, rule checks
factsheet.py        One-page PDF model factsheet
auth.py             Roles and permissions (single place to plug in SSO)
utils.py            Branding and display helpers
data/seed/          Seed data for the pilot inventory
scripts/            Reset, seed generator, smoke test
tests/              Unit tests
```
