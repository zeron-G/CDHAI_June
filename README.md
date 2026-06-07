# CDHAI_June

CDHAI_June is a single-patient data analysis agent scaffold. It reads one
patient's data, runs deterministic Python profiling and statistics first, asks
an LLM to draft reports and propose deeper hypotheses, executes allowlisted
statistical probes, then repeats the narrative cycle across reports.

The default loop runs 5 cycles and can be changed with `--cycles` or
`analysis.max_narrative_cycles` in `configs/default.yaml`.

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
```

Roles:

- `haipipe-toolkit`: current `haipipe`/WellDoc source for patient records,
  stores, cases, models, and future real-data loaders.
- `tools`: research/plugin/skill toolkit, including haipipe workflow skills and
  discovery utilities.
- `codex-oauth`: preferred local Codex OAuth LLM transport. When installed, the
  `codex_oauth` provider uses this package first and only falls back to the
  built-in compatibility client when the package is absent.

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

Smoke test:

```bash
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
python -m pytest
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

The next integration step is to add concrete loaders for WellDoc/haipipe
per-patient stores and wrappers for useful Tools search/discovery utilities.

## Output Layout

```text
runs/
  personal_knowledge_base/<patient_id>/
    insights.jsonl
    reports.jsonl
  <patient_id>/<run_id>/
    analysis/
    cycles/
    reports/
    manifest.json
```

Each cycle stores its hypotheses, statistical test results, and report. The
final report links evidence across the earlier reports.
