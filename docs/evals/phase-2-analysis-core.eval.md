# Phase 2 Eval — AI Analysis Core

**Goal under test:** per-item AI classification works, and all feedback clusters
into **at most 5** themes, each grounded in real verbatim quotes.

## Tests
### Per-item classification
- [ ] Every item gets sentiment (label + score), intent, behavior signals, segment hint.
- [ ] Output validates against the JSON schema; invalid responses are repaired/retried, not stored raw.
- [ ] **Sentiment accuracy ≥ 80%** vs the labeled golden set (macro-F1 reported).
- [ ] Classification is cached by content hash (re-run does not re-call the LLM for unchanged items).

### Theme clustering (hard business rule)
- [ ] Number of themes is **always ≤ 5** (assert on multiple input sizes).
- [ ] Every theme has a name, a one-line summary, mention volume, and a sentiment score.
- [ ] Every theme references **real verbatim quote IDs** that exist in the DB (no invented text).
- [ ] Representative quotes are genuinely near the cluster centroid (sanity-checked).
- [ ] Re-running clustering on the same data yields stable themes (label drift within tolerance).

### AI-quality (LLM-as-judge + human spot check)
- [ ] Theme labels score **≥ 4/5** mean on relevance/clarity rubric.
- [ ] Human review confirms themes are coherent and non-overlapping (spot check ≥ 20 items).

## Exit Criteria
- ≤5 themes guaranteed on every run; each fully populated and evidence-backed.
- Sentiment meets the accuracy threshold.
- Clustering stable and reproducible; no hallucinated quotes.

## Metrics to report
- Sentiment macro-F1, #themes, per-theme volume/sentiment, judge scores, cache hit rate, token cost.
