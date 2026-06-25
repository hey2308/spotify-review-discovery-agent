# Phase 3 Eval — Discovery Q&A + Segments + Unmet Needs

**Goal under test:** the system answers all 6 discovery questions (grounded),
derives coherent user segments, and produces a ranked unmet-needs tracker.

## Tests
### Discovery Q&A (Q1–Q6)
- [ ] Exactly **6 answers** exist, one per question, each non-empty and in plain language.
- [ ] Each answer cites **≥ N verbatim quote IDs** (default N=3) that exist in the DB.
- [ ] Each answer carries a confidence/frequency signal; under-evidenced answers are marked **low-confidence**, not fabricated.
- [ ] No answer contains a quote string absent from `feedback_items` (anti-hallucination check).
- [ ] Each answer includes a source breakdown of its supporting evidence.

### Segmentation (Q5)
- [ ] Segments are derived from review language and given human-readable labels.
- [ ] Each segment has top frustration, top unmet need, and most common behavior.
- [ ] A comparative rollup exists allowing side-by-side reading.
- [ ] Segment assignment is reproducible across runs (within tolerance).

### Unmet needs (Q6)
- [ ] Needs are ranked by mention frequency across sources.
- [ ] Each need has an urgency score derived from emotional intensity of language.
- [ ] Each need has source attribution (cross-platform vs concentrated).

### AI-quality (LLM-as-judge + human review)
- [ ] Answers score **≥ 4/5** mean on faithfulness + relevance rubric.
- [ ] Human reviewer agrees each answer is supported by its cited quotes (spot check all 6).

## Exit Criteria
- All 6 questions answered, grounded, and confidence-tagged — zero hallucinated quotes.
- Segments coherent with complete per-segment rollups.
- Unmet needs ranked with urgency + attribution.

## Metrics to report
- Avg citations/answer, % low-confidence, judge faithfulness scores, #segments, #unmet needs.
