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
- Treat `external/haipipe-toolkit` as the formal haipipe toolkit submodule.
  Keep direct toolkit use behind adapter boundaries so the default dry-run path
  can still work before the heavier toolkit dependency is installed.
- Preserve compatibility with local `Tools` and `HAI-Agent/packages/codex-oauth`
  paths through configuration rather than hard-coded imports.

## Validation

For focused changes, run:

```bash
python -m pytest
python -m cdhai_june run --input examples/sample_patient.csv --patient-id demo --cycles 2 --llm-provider mock
```

Use real LLM and database paths only after the dry-run path is green.
