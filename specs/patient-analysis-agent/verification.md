# Verification

Run from `CDHAI_June`:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
```

Expected:

- Tests pass.
- A run directory is created under `runs/demo/`.
- Reports exist under the run's `reports/` directory.
- The persistent knowledge base contains JSONL report and insight entries.
- `analysis/research_protocol.json`, `analysis/reference_manifest.json`,
  `analysis/figure_index.json`, and `analysis/ml_prediction_metrics.json` exist.
- Each `cycles/cycle_XX/` directory contains `research_cycle_review.json`.
- Each `cycles/cycle_XX/task_chain/` directory contains `task_graph.json`,
  `evidence_ledger.json`, `gate_decision.json`, and task directories with
  `config/`, `scripts/`, `runs/`, `results/`, `images/`, and `notebooks/`.
- Reports include deterministic figure links and a reference manifest section.
- CI validates ruff, pytest, mock pipeline smoke run, and package build.
