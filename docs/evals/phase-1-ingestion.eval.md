# Phase 1 Eval — Ingestion & Normalization

**Goal under test:** public feedback from all 5 source types lands in a clean,
PII-free, deduped canonical store within the **last 6 months**.

## Tests
### Connectors (use recorded fixtures — no live network in CI)
- [ ] App Store connector parses fixture → valid `feedback_items` (rating, title, text, date).
- [ ] Play Store connector parses fixture → valid items.
- [ ] Reddit connector parses fixture (post + top comments) → valid items.
- [ ] Community connector parses fixture (thread + posts) → valid items.
- [ ] Social connector parses fixture → valid items.
- [ ] Each item carries `source`, original `date`, and a provenance link to `raw_documents`.

### Normalization & dedup
- [ ] Canonical schema fields populated for every source; missing optional fields handled gracefully.
- [ ] Re-running ingestion on the same input adds **no** duplicates (idempotent upsert).
- [ ] Content-hash dedup collapses identical text from the same source.
- [ ] All stored items fall within the configured **last 6 months** window.

### Privacy (PII gate — hard fail on any hit)
- [ ] PII scrubber removes usernames, emails, @handles, phone numbers, device IDs **before** storage.
- [ ] Audit scan over `feedback_items` + `raw_documents` finds **0** PII matches.
- [ ] Redactions appear as `[redacted]`; surrounding verbatim text is preserved.
- [ ] Logs contain no PII.

## Exit Criteria
- All 5 sources ingest successfully into the canonical store.
- PII audit returns zero hits across stored data and logs.
- Dedup verified idempotent; window constraint enforced.
- Ingestion run is recorded in `pipeline_runs` with per-source counts.

## Metrics to report
- Items per source, dedup rate, % redacted, date-range coverage.
