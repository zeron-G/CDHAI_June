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
cd D:/data/code/github/CDHAI/CDHAI_June
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
```

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
  responses route, following the design in
  `../HAI-Agent/packages/codex-oauth`.
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

## Adjacent Repositories

The default config references local sibling projects:

- `../WellDoc-SPACE`
- `../WellDoc-SPACE/Tools`
- `../HAI-Agent/packages/codex-oauth`

The current MVP keeps these as optional paths. The next integration step is to
add concrete loaders for WellDoc per-patient stores and wrappers for useful
Tools search/discovery utilities.

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
