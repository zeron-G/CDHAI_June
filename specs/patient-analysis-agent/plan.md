# Implementation Plan

1. Scaffold package, config, scripts, examples, and tests.
2. Implement robust local table loading and schema detection.
3. Implement deterministic baseline profiling, CGM metrics, event summaries,
   and simple plots.
4. Implement LLM provider abstraction with mock, Codex OAuth, and
   OpenAI-compatible providers.
5. Implement hypothesis planning and allowlisted statistical test execution.
6. Persist reports and insights into a patient knowledge base.
7. Verify with smoke test and unit tests.

## Risks

- Real WellDoc stores may need a richer multi-table loader than the generic MVP.
- Codex OAuth backend compatibility can change; keep `mock` as a stable
  fallback and keep provider logic isolated.
- Clinical interpretation should remain research-supportive, not medical
  advice.
