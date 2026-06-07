# Patient Analysis Agent Spec

## Goal

Create a local agent program that reads data for a single patient, performs
deterministic baseline analysis, uses an LLM to write reports and propose
hypotheses, executes statistical probes in code, and repeats the loop for a
configurable number of cycles.

## Non-goals

- Do not build a patient-facing UI in this first project.
- Do not train or deploy glucose forecasting models here.
- Do not directly store database passwords or OAuth tokens.
- Do not let model-generated code execute without a future sandbox and review
  gate.

## Inputs

- Single-file patient data: CSV, TSV, JSON, JSONL, Parquet, XLSX.
- Directory of patient tables as a future-friendly form.
- Optional WellDoc per-patient stores once integrated.

## Outputs

- Basic profile JSON and Markdown report.
- CGM, meal, exercise, and event-derived statistical summaries when columns are
  detected.
- Research protocol, literature matrix, verified reference manifest, figure
  index, ML prediction baseline, and per-cycle research audit.
- Cycle reports for each narrative/probe iteration.
- A persistent personal knowledge base under `runs/personal_knowledge_base`.
- Final structured manifest for application handoff.

## Invariants

- Deterministic Python analysis runs before LLM reporting.
- Each report cycle must include a literature context, explicit hypothesis,
  mechanistic rationale, mathematical/statistical formulation, effect-size-aware
  test result, ML triangulation when relevant, visualization links, limitations,
  and references.
- LLM output is parsed into schemas or treated as text only.
- Statistical tests are selected from an allowlist.
- Unsupported, skipped, or underpowered findings are reported as evidence gaps,
  not as proof of no relationship.
- Reports cite only `reference_manifest.json` entries unless a future external
  discovery step verifies and adds new sources.
- Artifacts are reproducible from config, input path, and run id.
- Secrets and patient-identifiable data remain outside git.

## Extension Points

- WellDoc loader: map `Ptt`, `CGM5Min`, `Diet5Min`, `Exercise5Min`, and
  `Med5Min` records into the project `PatientDataset` shape.
- Foundation dependencies: keep `external/haipipe-toolkit`, `external/tools`,
  `external/codex-oauth`, and `external/academic-research-skills` as first-class
  submodules. Prefer installed packages/adapters from those foundations before
  using built-in fallback code.
- Tools/search: add an external discovery adapter from `external/tools` that
  returns citations or known domain facts into the personal knowledge base.
- Academic research: use `external/academic-research-skills` templates and
  integrity checks as the foundation for literature review, preregistration,
  IMRAD reporting, statistical reporting, peer-review-style critique, and final
  citation/claim verification.
- Application: expose `manifest.json` and reports to message, UI checklist, and
  suggestion generators.
