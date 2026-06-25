# Evals — Phase Gates

Each phase of the [implementation plan](../implementationPlan.md) has an eval file
here defining the **tests** and **exit criteria** that must pass before the next
phase begins. Evals combine two kinds of checks:

- **Code tests** — deterministic unit/integration tests (pytest, Vitest).
- **AI-quality evals** — golden datasets, LLM-as-judge scoring, and human spot
  checks for outputs the compiler can't verify (themes, answers, segments).

A phase is **DONE** only when every item in its eval checklist passes.

| Phase | Eval file |
|---|---|
| 0 | [phase-0-foundations.eval.md](./phase-0-foundations.eval.md) |
| 1 | [phase-1-ingestion.eval.md](./phase-1-ingestion.eval.md) |
| 2 | [phase-2-analysis-core.eval.md](./phase-2-analysis-core.eval.md) |
| 3 | [phase-3-intelligence.eval.md](./phase-3-intelligence.eval.md) |
| 4 | [phase-4-api.eval.md](./phase-4-api.eval.md) |
| 5 | [phase-5-frontend.eval.md](./phase-5-frontend.eval.md) |
| 6 | [phase-6-integration.eval.md](./phase-6-integration.eval.md) |

## Shared conventions
- **Golden dataset:** a small, hand-labeled set of ~100–150 feedback items kept in
  `evals/golden/`, used across phases for sentiment, theme, and Q&A scoring.
- **LLM-as-judge:** a rubric prompt scores generated answers/themes 1–5 on
  faithfulness, relevance, and clarity; runs are logged for comparison.
- **PII gate (every phase):** an automated scan asserts **zero** PII in any stored
  data, API response, log, or rendered view. A single hit fails the phase.
- **Thresholds** below are starting targets; tighten as the golden set grows.
