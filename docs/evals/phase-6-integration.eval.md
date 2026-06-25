# Phase 6 Eval — Integration & Definition of Done

**Goal under test:** the whole system runs end-to-end from scratch, and a
stakeholder can answer every Definition-of-Done question within 5 minutes.

## Tests
### End-to-end
- [ ] One-time pipeline steps documented: run `ingest` → `analyze` locally, then start backend + frontend.
- [ ] Deployed environment works: backend live on Render, frontend live on Vercel, Postgres pre-populated by the one-time pipeline run.
- [ ] Dashboard renders the full snapshot from the one-time fetch (no scheduler, no recurring jobs).
- [ ] Re-run on the same window produces comparable output; each run stamped in `pipeline_runs`.
- [ ] All prior phase eval gates (0–5) still pass (regression suite green).

### Definition of Done — stakeholder can answer on the dashboard
- [ ] **DoD-1:** single biggest reason users fail to discover new music (Overview headline + Q1).
- [ ] **DoD-2:** which user segment is most affected (Segment Breakdown).
- [ ] **DoD-3:** what the algorithm gets wrong most often (Q2 panel).
- [ ] **DoD-4:** what users do instead of using Spotify for discovery (Q6 / Unmet Needs).
- [ ] **DoD-5:** the three things the product team should prioritize next (derived from Unmet Needs + Q&A).
- [ ] **Timed walkthrough:** a first-time viewer answers all 5 in **under 5 minutes** without reading raw reviews.

### Constraint re-check (final sweep)
- [ ] Free public-API sources only; no paid APIs, no login-gated/ToS-violating access.
- [ ] ≤5 themes; all 6 questions answered and displayed.
- [ ] Zero PII anywhere (data, API, logs, UI).
- [ ] All displayed quotes are verbatim (no paraphrase/invention).
- [ ] Real backend + real frontend (not a mockup); AI performed the analysis.

### Docs & delivery
- [ ] README covers native local setup, one-time pipeline run, deploy (Render + Vercel), architecture link, and demo walkthrough.
- [ ] Cost report (tokens/run) and known limitations documented.

## Exit Criteria
- Full one-time pipeline run completes cleanly and populates the dashboard snapshot.
- All 5 DoD questions answerable on the dashboard within 5 minutes.
- Every problem-statement constraint re-verified; all eval gates green.

## Metrics to report
- End-to-end run time, time-to-answer (DoD walkthrough), total token cost, final constraint checklist.
