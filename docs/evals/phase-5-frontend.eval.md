# Phase 5 Eval — Frontend Dashboard

**Goal under test:** all six required dashboard sections render live API data in a
beautiful, modern, usable UI.

## Tests
### Section coverage (each rendered from live API)
- [ ] **Section 1 — Discovery Overview:** totals, date range, source breakdown, sentiment chart, single headline insight.
- [ ] **Section 2 — Theme Clusters:** ≤5 theme cards (name, volume, sentiment) + size visual; click expands to quotes/sub-patterns.
- [ ] **Section 3 — Q&A Panel:** 6 panels, each with answer + supporting evidence + confidence/frequency signal.
- [ ] **Section 4 — Quote Explorer:** searchable/filterable table; filters by theme, source, rating, date; each quote tagged theme/source/sentiment.
- [ ] **Section 5 — Segment Breakdown:** segments with top frustration/unmet need/behavior, side-by-side comparison.
- [ ] **Section 6 — Unmet Needs Tracker:** ranked list, urgency color-coding, source attribution.

### Behavior & quality
- [ ] Quote explorer filters call the API and update results correctly.
- [ ] Loading, empty, and error states render gracefully for every section.
- [ ] Data-freshness indicator shows `/api/meta` last-updated time.
- [ ] No console errors/warnings during normal use.
- [ ] **PII gate:** no PII visible anywhere in the rendered UI (manual + automated DOM scan).

### Non-functional
- [ ] Responsive on desktop + tablet widths.
- [ ] Accessibility baseline passes (labels, contrast, keyboard nav); Lighthouse a11y ≥ 90.
- [ ] Component tests (Vitest + RTL) for each section's render + filter logic pass.

## Exit Criteria
- All six sections render correct live data and match the problem statement spec.
- Filters work; states handled; no PII visible; no console errors.
- a11y/Lighthouse baseline met.

## Metrics to report
- Lighthouse perf/a11y scores, component test pass rate.
