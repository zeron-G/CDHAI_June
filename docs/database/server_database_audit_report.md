# Server Database Audit Report

Generated for CDHAI_June database onboarding.

## Current Access Status

- SSH host: `10.175.198.65`
- SSH port: `22`
- Network reachability from this workstation: reachable on SSH.
- Current status: SSH authentication succeeded when the credential was supplied at runtime.
- Data extracted during this audit: metadata reports only.
- PHI/row-level patient data written locally: none.

The accessible server data is organized primarily as a WellDoc-SPACE workspace
rather than as a conventional SQL database exposed to this account.

## Audit Tools

Run directly on the server after SSH login:

```bash
python3 scripts/server_database_audit.py \
  --output-dir ~/cdhai_database_audit \
  --max-exact-rows 100000
```

Run from the local workstation through SSH:

```powershell
python scripts/remote_database_audit.py `
  --host 10.175.198.65 `
  --user rgao28 `
  --ask-password `
  --local-output-dir reports/database_audit/latest
```

The generated files are:

```text
reports/database_audit/latest/
  database_inventory.json
  database_inventory_report.md
```

`reports/` is ignored by git so audit artifacts are not accidentally committed.

Run the WellDoc-SPACE manifest audit on the server workspace root:

```bash
python3 scripts/welldoc_space_manifest_audit.py \
  --base /nvme1/group_share/WellDoc-SPACE/_WorkSpace \
  --output-json welldoc_space_manifest_summary.json \
  --output-md welldoc_space_database_report.md
```

This generated the following local, git-ignored artifacts:

```text
reports/database_audit/latest/
  welldoc_space_manifest_summary.json
  welldoc_space_database_report.md
  CDHAI_database_research_readiness_report.md
  figures/
  tables/
```

## What The Audit Collects

The audit is aggregate-only by default:

- Host context: hostname, user, platform, Python version.
- Database service hints: listening TCP ports and available database CLI tools.
- PostgreSQL inventory when `psql` is usable:
  - database names,
  - database sizes,
  - schemas, tables, views, materialized views,
  - estimated row counts and relation sizes,
  - column names, types, nullability, and domain tags,
  - exact row count and missingness for tables under `--max-exact-rows`,
  - numeric/date ranges only for non-sensitive column names.
- SQLite inventory under configured roots:
  - file path,
  - file size,
  - table/view names,
  - row counts,
  - columns and domain tags.

The audit does not export raw rows, categorical values, names, emails, phone numbers, addresses, MRNs, dates of birth, tokens, passwords, or authentication values.

## Current Server Findings

- Host: `cdhai-Lambda-Vector`
- Main data root: `/nvme1/group_share/WellDoc-SPACE/_WorkSpace`
- Conventional database CLIs on PATH: no `psql`, `mysql`, `mariadb`, `mongosh`, or `sqlite3`; `redis-cli` is present and Redis listens on localhost.
- `/share/welldocdata` is visible but empty.
- `/home/cdhai` is not readable by the current account.
- The WellDoc-SPACE workspace contains 659 parsed manifests:
  - `CaseSet`: 458
  - `RecordSet`: 151
  - `AIDataSet`: 35
  - `SourceSet`: 11
  - `endpoint_set`: 3
  - `unknown`: 1
- Major data stores:
  - `1-SourceStore`: WellDoc, OhioT1DM, CGMacros, Dubosson, Shanghai, AIREADI, and MIMIC-IV source families.
  - `2-RecStore`: patient-time records such as `Ptt`, `CGM5Min`, `Diet5Min`, `Exercise5Min`, `Med5Min`, vitals/labs, and MIMIC events.
  - `3-CaseStore`: model-ready case/window definitions for long time-series, event response, FairGlucose, and MIMIC admission tasks.
  - `4-AIDataStore`: training splits for EventGlucose, FairGlucose, PretrainGlucose, PretrainCGM_Stride4H, OhioT1DM, and MIMIC admission tasks.
  - `5-ModelInstanceStore`: existing model checkpoints, trainer states, result JSON, and figures.
  - `6-EndpointStore`: OhioT1DM CGM forecast/LTS endpoints plus two USDA nutrition SQLite assets.

## Expected Database Signals For CDHAI_June

The project can use the database immediately once these domain signals are mapped:

- `patient_identity`: patient or subject ids, which must be hashed and never used as model features directly.
- `timestamp`: observation, event, message, or UI interaction times.
- `glucose_cgm`: CGM or blood glucose observations.
- `meal_food`: meal names, carbohydrates, calories, or food events.
- `activity`: exercise, steps, heart rate, or activity windows.
- `medication`: insulin, dose, medication events.
- `message_ui`: messages, suggestions, checklists, notifications, clicks, or engagement.
- `outcome_label`: labels, responses, targets, classes, or endpoint outcomes.

## Training And Research Integration Plan

1. Build a de-identified data catalog.
   - Keep a private subject map on the server.
   - Use stable hashed subject ids in exported research datasets.
   - Mark columns as `identifier`, `time`, `measurement`, `event`, `intervention`, `engagement`, or `outcome`.

2. Normalize tables into a patient-event schema.
   - `observations`: patient hash, timestamp, variable, value, unit, source table.
   - `events`: patient hash, timestamp, event type, event payload, source table.
   - `interventions`: patient hash, timestamp, message/suggestion/checklist item, delivery state.
   - `outcomes`: patient hash, timestamp/window, label or measured response.

3. Create model-ready windows.
   - CGM forecasting windows: past glucose plus behavior events -> next glucose / time-in-range.
   - Meal response windows: pre-meal baseline plus carbs/meal context -> post-meal peak delta.
   - Activity response windows: activity/steps windows -> subsequent glucose change.
   - Engagement windows: message/UI exposure -> click, checklist completion, or response.

4. Train in stages.
   - Stage A: deterministic descriptive reports and cohort QA.
   - Stage B: self-supervised time-series pretraining across all patients.
   - Stage C: supervised next-glucose and event-response models.
   - Stage D: insight-agent evaluation against held-out patients and held-out time.
   - Stage E: application suggestion models only after clinical and IRB review.

5. Prevent leakage.
   - Split by patient first, then by time within patient.
   - Do not let future events, future UI actions, or post-outcome data enter feature windows.
   - Keep repeated runs versioned by extraction SQL, source snapshot, feature config, and model config.

6. Use project foundations.
   - `haipipe-toolkit`: map server records into haipipe/WellDoc-compatible patient datasets and model tasks.
   - `Tools`: keep the search/discovery/tool workflow around each research cycle.
   - `academic-research-skills`: maintain literature matrices, preregistration, statistical reporting, and integrity gates.
   - `codex_oauth`: use LLMs only after deterministic analysis artifacts are generated.

## Next Required Action

Use `reports/database_audit/latest/CDHAI_database_research_readiness_report.md`
as the concrete onboarding report, then implement a `WellDocWorkspaceLoader`
that reads server manifests, materializes de-identified single-patient bundles,
and feeds the existing CDHAI_June task-cycle research loop.
