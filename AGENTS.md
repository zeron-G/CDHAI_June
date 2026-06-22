# CDHAI_June Agent Notes

This project is a single-patient analysis agent scaffold. Keep the first
principle clear: deterministic Python analysis should do as much work as
possible before an LLM is asked to summarize, hypothesize, or plan the next
probe.

## Boundaries

- Do not commit patient-identifiable data, database passwords, OAuth tokens, or
  generated run artifacts.
- Treat the JHU server details as runtime configuration only. Use environment
  variables, SSH agent, or interactive password entry outside this repository.
- Keep LLM-generated work behind typed schemas and allowlisted statistical
  tools. Do not execute arbitrary model-written code by default.
- Treat `external/haipipe-toolkit`, `external/tools`,
  `external/codex-oauth`, `external/academic-research-skills`, and
  `external/cdhai-hapf` as the formal
  foundation layer for this project. Keep direct use behind adapter boundaries
  so the default dry-run path can still work before heavier or private
  dependencies are installed.
- Prefer the `codex_oauth` package from `external/codex-oauth` for the
  `codex_oauth` LLM provider when it is installed; use the built-in transport
  compatibility code only as fallback.
- Keep per-cycle exploration inside the controlled `TaskCycleRunner`. It may
  generate scripts/config/results/images/notebook artifacts, but execution must
  stay inside allowlisted package code unless a future sandbox is added.
- Keep HAPF model ownership in `external/cdhai-hapf`. CDHAI_June may validate
  inputs, invoke the pinned API, cache aggregate results, and report evidence,
  but must not duplicate HAPF architecture or expose raw subject identifiers.

## Validation

For focused changes, run:

```bash
python -m pytest
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
python -m ruff check src tests
python -m build
```

Use real LLM and database paths only after the dry-run path is green.
