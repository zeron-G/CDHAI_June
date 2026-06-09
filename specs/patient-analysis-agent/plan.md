# Implementation Plan

1. Scaffold package, config, scripts, examples, and tests.
2. Implement robust local table loading and schema detection.
3. Implement deterministic baseline profiling, CGM metrics, event summaries,
   and simple plots.
4. Implement LLM provider abstraction with mock, Codex OAuth, and
   OpenAI-compatible providers.
5. Implement hypothesis planning and allowlisted statistical test execution.
6. Persist reports and insights into a patient knowledge base.
7. Add paper-grade research artifacts: protocol, literature matrix, reference
   manifest, figure index, ML prediction baseline, and cycle audit.
8. Add task-cycle exploration chain with task graph, scripts/config/results,
   neural-network task execution, visualizations, evidence ledger, and gate.
9. Add CI/CD: lint, test matrix, pipeline smoke run, package build, release
   artifact workflow.
10. Verify with smoke test and unit tests.

## Risks

- Real WellDoc stores may need a richer multi-table loader than the generic MVP.
- Codex OAuth backend compatibility can change; keep `mock` as a stable
  fallback and keep provider logic isolated.
- Clinical interpretation should remain research-supportive, not medical
  advice.
- Citation metadata and literature claims must remain explicit and re-verifiable
  before publication.
- Task-cycle scripts are generated as reproducibility artifacts; they should not
  become an arbitrary-code execution path without sandboxing.
