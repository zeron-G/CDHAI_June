# Verification

Run from `CDHAI_June`:

```bash
python -m pytest
python -m ruff check src tests
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
python -m build
```

Expected default behavior:

- Every cycle contains a `personalized_forecasting` task.
- Without cohort configuration, the task is `skipped` with a readiness artifact.
- The normal mock pipeline still reaches the insight stage when HAPF is not
  configured as a blocking gate.
- Cycle reports contain a HAPF section and link to task artifacts.

Configured integration smoke:

```powershell
$env:CDHAI_HAPF_CGM_PATH = "<local record_CGM5Min.parquet>"
$env:CDHAI_HAPF_HELDOUT_SUBJECT = "<subject_key>"
python -m cdhai_june run --input "<single patient file>" --patient-id "<subject_key>" --cycles 2 --llm-provider mock
```

Expected configured behavior:

- Cycle 1 runs HAPF and writes cached model artifacts.
- Cycle 2 reuses the cache and writes a new cycle-local interpretation.
- Reports and manifest include population/personalized/deployed metrics and the
  personalization-gate outcome without exposing the raw subject key.

## Recorded Result

Local verification on 2026-06-22:

- Ruff: passed.
- Pytest: 14 tests passed without warnings.
- Package: source distribution and wheel built successfully.
- Real A-User-Store smoke: 2 cycles completed against the aligned CGM cohort.
- Cycle 1 trained HAPF; cycle 2 reused the cache.
- The selected holdout rejected personalization and used the population
  fallback because personalized RMSE was worse at both horizons. This is the
  expected harm-prevention behavior, not a failed run.
- Four generated reports, two HAPF task configs, and HAPF result summaries were
  checked for the raw held-out key; no disclosure was found.
- Smoke artifact root:
  `runs/hapf_cycle_integration_smoke/patient_3d7854dcb897/20260622_000125`.
