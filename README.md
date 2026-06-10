# CDHAI_June

CDHAI_June is a single-patient data analysis agent scaffold. It reads one
patient's data, runs deterministic Python profiling and statistics first, asks
an LLM to draft reports and propose deeper hypotheses, executes allowlisted
statistical probes, then repeats the narrative cycle across reports.

The default loop runs 5 cycles and can be changed with `--cycles` or
`analysis.max_narrative_cycles` in `configs/default.yaml`.

Each report cycle is intended to be a research loop, not a loose test pass:
the pipeline now emits a literature-backed research protocol, explicit
hypotheses, a task-cycle exploration chain, mathematical definitions,
statistical/effect-size audit tables, neural-network prediction tasks, figure
indexes, reference manifests, evidence gates, and claim-integrity guardrails
before asking the LLM to write narrative text.

## Why This Shape

The project follows the flow in the sketch:

1. Individual patient data enters a personal knowledge base.
2. Python scripts produce a basic data description without relying on an LLM.
3. An LLM writes an initial report from structured analysis outputs.
4. Each probe cycle asks the LLM to look across the data and prior reports,
   propose hypotheses, and select a statistical test family.
5. Python executes allowlisted tests and creates JSON, plots, and Markdown.
6. Reports and insights are stored in the personal knowledge base so later
   cycles can discover cross-report relationships.
7. Application-facing outputs are generated as report files, structured JSON,
   and future message/checklist/suggestion artifacts.

## Local Setup

```bash
git clone --recurse-submodules https://github.com/zeron-G/CDHAI_June.git
cd CDHAI_June
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
```

If you cloned without submodules:

```bash
git submodule update --init --recursive
```

## Foundational Dependencies

This project treats the repositories from the original project brief as
foundational dependencies under `external/`:

```text
external/haipipe-toolkit -> https://github.com/JHU-CDHAI/WellDoc-SPACE.git
external/tools           -> https://github.com/jluo41/Tools.git
external/codex-oauth     -> https://github.com/zeron-G/codex_oauth.git
external/academic-research-skills -> https://github.com/Imbad0202/academic-research-skills.git
```

Roles:

- `haipipe-toolkit`: current `haipipe`/WellDoc source for patient records,
  stores, cases, models, and future real-data loaders.
- `tools`: research/plugin/skill toolkit, including haipipe workflow skills and
  discovery utilities.
- `codex-oauth`: preferred local Codex OAuth LLM transport. When installed, the
  `codex_oauth` provider uses this package first and only falls back to the
  built-in compatibility client when the package is absent.
- `academic-research-skills`: paper-grade research pipeline substrate. CDHAI_June
  adapts its literature matrix, preregistration, IMRAD, statistical reporting,
  review, and integrity-gate patterns into per-cycle patient-data reports.

`JHU-CDHAI/WellDoc-SPACE` is private, so recursive clone and haipipe install
require GitHub access to that organization repository.

Set up the lighter foundations:

```powershell
scripts/setup_foundations.ps1
```

Install the heavier haipipe toolkit when running real WellDoc/haipipe loaders:

```bash
python -m pip install -e external/haipipe-toolkit
```

Or use the helper:

```powershell
scripts/setup_haipipe_toolkit.ps1
```

The default sample-data path still runs without installing the heavy haipipe or
Codex OAuth dependencies. Each run manifest records whether all foundational
submodules are present and whether installable packages are importable.

## Paper-Grade Research Loop

The deterministic analysis phase writes these artifacts before narrative
generation:

```text
analysis/
  basic_profile.json
  cgm_metrics.json
  event_metrics.json
  ml_prediction_metrics.json
  ml_next_glucose_predictions.csv
  research_protocol.json
  literature_matrix.json
  reference_manifest.json
  figure_index.json
  research_integrity_checklist.json
cycles/cycle_XX/
  hypotheses.json
  test_results.json
  task_chain/
    task_graph.json
    evidence_ledger.json
    gate_decision.json
    task_001_literature_search/
      config/
      scripts/
      runs/
      results/
      images/
      notebooks/
  research_cycle_review.json
```

The protocol encodes research questions, hypotheses, falsification criteria,
mathematical definitions, a statistical analysis plan, ML-prediction baseline,
visualization plan, and citation policy. Reports may cite only the verified
reference manifest unless a future external-discovery adapter verifies new
sources. Single-patient associations are always framed as exploratory evidence,
not clinical guidance.

Cycle reports embed or link the task-chain artifacts produced by each
exploration step, including JSON evidence ledgers, CSV prediction outputs,
Markdown literature matrices, and PNG visualizations.

Inside each narrative cycle, `TaskCycleRunner` creates a bounded exploration
loop. It plans and executes allowlisted tasks for literature mapping, feature
engineering, statistical packaging, neural-network training/prediction,
visualization, and result interpretation. If the evidence gate still sees a
gap, it can dispatch follow-up sensitivity or evidence-gap tasks until
`analysis.task_cycle.max_rounds` is reached. Only a `ready_for_insight` gate
allows the cycle to move into the insight/report stage.

Smoke test:

```bash
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
python -m pytest
python -m ruff check src tests
```

Generated artifacts are written under `runs/` and are ignored by git.

## LLM Providers

Provider options:

- `mock`: local deterministic report drafting. This is the default and is good
  for pipeline testing.
- `codex_oauth`: reads the local Codex OAuth session and calls the Codex
  responses route. It prefers the foundational `external/codex-oauth` package
  when installed.
- `openai_compatible`: calls an OpenAI-compatible `/responses` endpoint.

Example with Codex OAuth:

```bash
$env:CDHAI_LLM_PROVIDER = "codex_oauth"
$env:CDHAI_LLM_MODEL = "gpt-4o-mini"
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo
```

The code never logs access tokens. Keep `~/.codex/auth.json` private.

## Database Access

Database credentials are not stored in this repository. Put runtime-only values
in environment variables or a local `.env` file based on `.env.example`.

Use the JHU VPN before connecting to the configured SSH host. If a tunnel is
needed, create it outside the pipeline, then point future database loaders at
the local tunnel port.

## External Repositories

The default config references:

- `external/haipipe-toolkit`: formal haipipe toolkit submodule
- `external/tools`: formal Tools submodule
- `external/codex-oauth`: formal Codex OAuth submodule
- `external/academic-research-skills`: formal academic research workflow
  submodule

The next integration step is to add concrete loaders for WellDoc/haipipe
per-patient stores and wrappers for useful Tools search/discovery utilities.

## Output Layout

```text
runs/
  personal_knowledge_base/<patient_path_segment>/
    insights.jsonl
    reports.jsonl
  <patient_path_segment>/<run_id>/
    analysis/
    cycles/
      cycle_XX/research_cycle_review.json
    reports/
    manifest.json
```

`patient_id` remains in the manifest and reports, while `patient_path_segment`
is a sanitized filesystem-safe slug used only for local output paths. Each
cycle stores its hypotheses, statistical test results, task-chain artifacts,
and report. The final report links evidence across the earlier reports.

## CI/CD

GitHub Actions are configured under `.github/workflows/`:

- `ci.yml`: ruff lint, pytest on Ubuntu/Windows with Python 3.11 and 3.12,
  mock pipeline smoke run, package build, and artifact upload.
- `release.yml`: tag/manual release artifact build after tests pass.

The CI path intentionally does not initialize private/heavy submodules, so the
default mock/sample-data workflow remains reproducible in a clean public runner.
