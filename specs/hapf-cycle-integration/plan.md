# Implementation Plan

1. Add HAPF submodule/config/foundation status and optional install metadata.
2. Add a lazy HAPF integration adapter with readiness, execution, cache, and
   cycle-interpretation contracts.
3. Schedule `personalized_forecasting` in each task cycle and feed its evidence
   to the task gate.
4. Add HAPF references and research-protocol hooks.
5. Render HAPF results in cycle/final reports and persist completed model
   insights into the personal knowledge base.
6. Add focused adapter/task/report tests and broaden pipeline regression tests.
7. Run lint, pytest, mock pipeline smoke, package build, and a configured local
   HAPF integration smoke using the A-User-Store composite.

## Risks

- HAPF requires a cohort and stable subject identity; a single patient file is
  not sufficient to train a population model.
- Repeated model training is expensive; cache correctness is required.
- A configured patient id may not match `subject_key`; silent auto-selection is
  forbidden by default.
- Optional PyTorch imports must not break clean public CI runners.

