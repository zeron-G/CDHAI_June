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
