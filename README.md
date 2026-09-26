# QDB Model Governance Platform — Proof of Concept

A Model Risk Management (MRM) proof-of-concept for **Qatar Development Bank**: a central
model inventory with full per-model governance drill-down (ownership, tiering, validation
history, findings and remediation, performance monitoring, documentation and audit trail).

Framework aligned to Fed SR 11-7, PRA SS1/23 and ECB internal-model guidance, with a
Qatar-specific regulatory lens (QCB instructions, IFRS 9, Qatar AML/CFT Law No. 20 of 2019).

> All data in this PoC is **mock data** created to illustrate the governance framework —
> including deliberately realistic problem states (overdue validations, open high-severity
> findings, a model in production without approval).

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

## Pages

| Page | Purpose |
|---|---|
| Executive Dashboard | Model risk profile at a glance: KPIs, tier/status charts, attention-required list, validation calendar |
| Model Inventory | Filterable, searchable register of all models; click a row to drill down |
| Model Detail | Full governance record per model: Overview, Governance & Lifecycle, **Validation & Findings** (typed requests MMC/NMMC/VAL/VRQ/VFI), Performance Monitoring, Documentation & Audit |
| Findings Tracker | Bank-wide VFI register plus other open validation requests (MMC/VRQ); detail lives on Model Detail |
| Governance Framework | The proposed MRM policy: model definition, tiering methodology, lifecycle, committees, implementation roadmap |

## Replacing mock data with real QDB models

All data lives in `data/` and is loaded through `data_loader.py` — no page code changes needed:

| File | Contents |
|---|---|
| `data/models.json` | One record per model: identification, ownership, tiering, lifecycle dates, regulatory mapping, documentation checklist, change log, audit reviews, dependencies |
| `data/validation_requests.json` | **Source of truth** for validation workflow: typed requests (MMC, NMMC, VAL, VRQ, VFI) with status, assignment, thread, outcome |
| `data/validations.json` | Historical archive (migrated into validation_requests) |
| `data/issues.json` | Historical archive of findings (migrated into VFI requests) |
| `data/monitoring.csv` | Quarterly KPI history per model metric with amber/red thresholds |

To add a real model, copy an existing record in `models.json` and edit the fields. Overdue
statuses (validations and findings) are computed automatically against today's date.

`scripts/generate_monitoring.py` regenerates the mock monitoring history if needed.

## Structure

```
app.py                     Entry point (navigation + theme)
views/                     Dashboard, Inventory, Model Detail, Findings Tracker, Framework
data/                      Mock inventory, validations, issues, monitoring
data_loader.py             Data access layer (swap for a DB later)
utils.py                   Branding, badges, shared styling
scripts/                   Mock data generator
```
