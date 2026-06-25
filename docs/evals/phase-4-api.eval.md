# Phase 4 Eval — Backend API

**Goal under test:** all materialized intelligence is served via a correct, fast,
documented REST API.

## Tests
### Contract & correctness (integration tests on a seeded DB)
- [ ] `GET /api/overview` → totals, date range, source breakdown, sentiment distribution, headline insight.
- [ ] `GET /api/themes` → ≤5 themes with volume + sentiment; `GET /api/themes/{id}` → quotes + sub-patterns.
- [ ] `GET /api/questions` → all 6 answers with evidence + confidence.
- [ ] `GET /api/quotes` → paginated verbatim quotes, each tagged theme/source/sentiment.
- [ ] `GET /api/segments` → comparative segment data.
- [ ] `GET /api/unmet-needs` → ranked needs with urgency + attribution.
- [ ] `GET /api/meta` → last run time + freshness + counts.
- [ ] All responses validate against their Pydantic/OpenAPI schemas.

### Quote explorer filtering
- [ ] Filter by theme, source, rating, and date range each return correct subsets.
- [ ] Free-text search matches quote content.
- [ ] Pagination is stable and correct (no dupes/skips across pages).

### Non-functional & safety
- [ ] **PII gate:** no endpoint response contains any PII (automated scan over sampled responses).
- [ ] p95 latency under target (e.g. < 300 ms) on the seeded dataset.
- [ ] OpenAPI docs generate and match implemented routes.
- [ ] Error cases (bad params, unknown id) return clean typed errors, not 500s.

## Exit Criteria
- Every endpoint returns the correct shape and data.
- Quote filtering/search/pagination verified.
- Zero PII in responses; latency target met; docs generated.

## Metrics to report
- Endpoint pass rate, p50/p95 latency, payload sizes.
