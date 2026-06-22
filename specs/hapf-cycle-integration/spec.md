# HAPF Cycle Integration Spec

## Goal

Integrate CDHAI-HAPF as a formal external foundation and a first-class,
evidence-producing task in every enabled CDHAI_June research cycle.

## Ownership Boundary

- CDHAI-HAPF owns model architecture, population training, patient adaptation,
  conformal calibration, and personalization-gate evaluation.
- CDHAI_June owns data-readiness checks, cycle scheduling, cache/reuse policy,
  evidence-ledger integration, report synthesis, and knowledge-base persistence.
- CDHAI_June must not copy or fork HAPF model implementation into its package.

## Inputs

- A single-patient `PatientDataset` used by the normal CDHAI_June pipeline.
- An optional governed cohort CGM Parquet path with `subject_key`, `DT_s`, and
  `BGValue`, configured by `CDHAI_HAPF_CGM_PATH`.
- An optional held-out subject key configured by
  `CDHAI_HAPF_HELDOUT_SUBJECT`. When omitted, the current `patient_id` may be
  used only if it is present in the cohort `subject_key` column.
- A pinned HAPF submodule and HAPF experiment configuration.

## Cycle Behavior

Every enabled cycle adds a `personalized_forecasting` task after the lightweight
neural-network baseline. The task must produce one of:

1. `completed`: HAPF result, gate decision, metrics, calibration artifacts, and
   deterministic cycle interpretation.
2. `skipped`: a structured readiness/evidence-gap artifact identifying missing
   cohort data, target identity, package dependency, or model configuration.
3. `failed`: a sanitized integration failure artifact. It must not leak
   credentials or identifiers into public reports.

Repeated cycles reuse a cache keyed by cohort file metadata, held-out subject,
HAPF configuration, and pinned source metadata. Every cycle still writes a
cycle-local interpretation and evidence-ledger record.

## Reporting Contract

- Cycle reports contain a dedicated HAPF personalized-forecasting section.
- Completed HAPF evidence includes population, personalized, and deployed RMSE,
  conformal coverage, and whether the personalization gate accepted adaptation.
- Completed evidence is persisted as an insight for cross-cycle retrieval.
- Final synthesis reports how many cycles had completed HAPF evidence and how
  many accepted personalization.
- Skipped HAPF tasks are evidence gaps, never evidence against personalization.

## Safety and Privacy

- HAPF imports are lazy and execute only pinned allowlisted package code.
- No arbitrary generated scripts are executed.
- Cohort data, subject keys, predictions, checkpoints, and run outputs remain
  gitignored/local.
- Reports use the HAPF `heldout_alias` and aggregate metrics, not raw subject
  identifiers.
- Model output is exploratory forecasting evidence, not diagnosis or treatment
  advice.

## Compatibility

- Default mock/sample runs remain functional without PyTorch or an initialized
  HAPF submodule.
- Existing task and report artifacts remain backward-compatible.
- HAPF is an optional dependency and a formal submodule.

