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
git submodule update --init --recursive external/haipipe-toolkit
```

## Haipipe Toolkit Dependency

This project now treats `external/haipipe-toolkit` as the formal haipipe
toolkit submodule. The submodule points to the current source of the `haipipe`
package:

```text
external/haipipe-toolkit -> https://github.com/JHU-CDHAI/WellDoc-SPACE.git
```

That upstream repository is private, so recursive clone and toolkit install
require GitHub access to `JHU-CDHAI/WellDoc-SPACE`.

Install the toolkit from the submodule when running real WellDoc/haipipe
loaders:

```bash
python -m pip install -e external/haipipe-toolkit
```

Or use the helper:

```powershell
scripts/setup_haipipe_toolkit.ps1
```

The default sample-data path still runs without installing the heavy haipipe
dependency. Each run manifest records whether the submodule is present and
whether `haipipe` is importable.

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

## External Repositories

The default config references:

- `external/haipipe-toolkit`: formal haipipe toolkit submodule
- `external/haipipe-toolkit/Tools`: Tools path inside the toolkit source tree
- `../HAI-Agent/packages/codex-oauth`: local Codex OAuth package path

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
