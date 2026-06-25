# Implementation Plan — Phase-Wise

> Companion docs: [`architecture.md`](./architecture.md) · [`problemStatement.md`](./problemStatement.md) · [`decisions.md`](./decisions.md) · per-phase exit criteria in [`evals/`](./evals)

The build is sliced into 7 phases. Each phase is independently shippable, has a
matching eval file under [`evals/`](./evals) defining its **tests + exit
criteria**, and must pass that gate before the next phase begins.

| Phase | Name | Outcome | Eval gate |
|---|---|---|---|
| 0 | Foundations & Scaffolding | Repo, DB, config, CI run | [`phase-0-foundations.eval.md`](./evals/phase-0-foundations.eval.md) |
| 1 | Ingestion & Normalization | Public feedback stored, PII-free, deduped | [`phase-1-ingestion.eval.md`](./evals/phase-1-ingestion.eval.md) |
| 2 | AI Analysis Core | Sentiment + ≤5 grounded themes | [`phase-2-analysis-core.eval.md`](./evals/phase-2-analysis-core.eval.md) |
| 3 | Discovery Q&A + Segments + Needs | Q1–Q6, segments, unmet needs | [`phase-3-intelligence.eval.md`](./evals/phase-3-intelligence.eval.md) |
| 4 | Backend API | Endpoints serving materialized insights | [`phase-4-api.eval.md`](./evals/phase-4-api.eval.md) |
| 5 | Frontend Dashboard | 6 sections rendering live data | [`phase-5-frontend.eval.md`](./evals/phase-5-frontend.eval.md) |
| 6 | Integration & Definition of Done | End-to-end run + DoD validated | [`phase-6-integration.eval.md`](./evals/phase-6-integration.eval.md) |

Legend for tasks: each phase lists **Goals → Deliverables → Key Tasks → Exit
Criteria (summary)**. The authoritative pass/fail checklist lives in the eval file.

---

## Phase 0 — Foundations & Scaffolding

**Goal:** A runnable skeleton everyone can build on; no business logic yet.

**Deliverables**
- Monorepo layout (`backend/`, `frontend/`, `evals/`, `docs/`).
- Native local dev setup (no Docker): Python venv + Uvicorn, Node + Vite; a `.env.example`.
- Deploy configs: `render.yaml` (backend + managed Postgres) and `frontend/vercel.json`.
- Config system (env vars + typed settings), secrets via `.env` (never committed).
- DB schema v1 via Alembic migrations (tables from `architecture.md` §3.2).
- Groq LLM client + local embeddings + ChromaDB client abstractions (mockable); Chroma embedded for the one-time analysis run only.
- CI: lint + type-check + unit-test on push (GitHub Actions).

**Key Tasks**
1. Initialize backend (FastAPI + SQLAlchemy + Alembic) and frontend (Vite + TS).
2. Define ORM models and generate the initial migration.
3. Implement `core/config.py`, `core/llm.py` (Groq), `core/embeddings.py` (local), `core/vectorstore.py` (Chroma) with a mock mode.
4. Add task shortcuts/scripts: `dev`, `migrate`, `test`, `lint` (Makefile or npm/uv scripts).
5. Wire CI + add `render.yaml` and `vercel.json` so deploys are one-click from Git.

**Exit Criteria (summary):** local stack runs natively, migrations apply, health
endpoint returns 200, CI green, deploy configs validate. Full gate → [`phase-0-foundations.eval.md`](./evals/phase-0-foundations.eval.md).

---

## Phase 1 — Ingestion & Normalization

**Goal:** Pull public feedback from all 5 source types into a clean, PII-free,
deduped canonical store covering the **last 6 months**.

**Deliverables**
- Connector interface + 5 connectors (App Store, Play Store, Reddit, Community, Social).
- Canonical mapper → `feedback_items`; raw payloads → `raw_documents`.
- **PII scrubber** (usernames, emails, handles, device IDs, phone numbers) run pre-store.
- Content-hash dedup + idempotent upsert.
- `ingest` CLI command with per-source flags and a date window.
- **Play Store pagination** via continuation token (configurable cap, default 3,000 reviews within the 6-month window).
- Connector unit tests using recorded fixtures (no live network in tests).

**Key Tasks**
1. Build the common `SourceConnector` interface (fetch → normalize → yield items).
2. Implement each connector against its public API/RSS (see `architecture.md` §3.1).
3. Implement PII scrubbing with regex + heuristics; mark redactions `[redacted]`.
4. Implement dedup via SHA-256 of normalized text + source key.
5. Add windowing (**last 6 months**) and rate-limit/backoff handling.
6. **Play Store pagination:** loop `google-play-scraper` with continuation tokens
   (200 per page, up to **3,000** reviews), stopping early when the oldest batch
   review falls before the 6-month window.
7. **Social pagination:** Bluesky uses `since`/`until` time-slice loops (cursor
   blocked unauthenticated); Mastodon uses `max_id` tag-timeline loops; cap
   **3,000** unique posts per run (`SOCIAL_MAX_ITEMS`).

**Exit Criteria (summary):** all sources ingest into canonical schema, 0 PII
leaks on the audit scan, dedup rate sane, items within window. Full gate →
[`phase-1-ingestion.eval.md`](./evals/phase-1-ingestion.eval.md).

---

## Phase 2 — AI Analysis Core

**Goal:** Per-item AI classification + clustering of all feedback into **at most 5
themes**, each grounded in real verbatim quotes.

Phase 2 is split into **sub-phases 2A–2F** below. Complete them in order; the
single eval gate at the end ([`phase-2-analysis-core.eval.md`](./evals/phase-2-analysis-core.eval.md))
covers the whole phase.

```
2A Pipeline scaffold ──▶ 2B Classify ──▶ 2C Embed ──▶ 2D Cluster ──▶ 2E Theme labels ──▶ 2F Evidence & rollups
   (CLI + run stamp)      (per-item)      (Chroma)      (≤5 themes)    (LLM names)       (quotes + metrics)
```

| Sub-phase | Name | Outcome |
|---|---|---|
| 2A | Pipeline scaffolding | `analyze` CLI, stage orchestration, `pipeline_runs` integration |
| 2B | Per-item classification | Every item classified → `analyses` (sentiment, intent, behaviors, segment hint) |
| 2C | Embeddings & vector store | All items embedded (content-hash cache) → ChromaDB |
| 2D | Theme clustering | UMAP → HDBSCAN → deterministic merge/trim to **≤ 5** cluster IDs |
| 2E | Theme labeling & persistence | LLM names/summaries → `themes` + `feedback_themes` |
| 2F | Evidence & rollups | Representative quotes, per-theme volume + sentiment |

### Groq rate-limit budget (Phase 2–3)

Free-tier caps for **`llama-3.3-70b-versatile`**: **30 RPM · 1K RPD · 12K TPM · 100K TPD**.
Phase 2 is structured so **70B is never used for per-item work** — only short, batched
or ≤5-call stages — keeping well inside daily limits.

| Sub-phase | Model | Est. calls / run | Token strategy | Limit guard |
|---|---|---|---|---|
| **2B Classify** | `llama-3.1-8b-instant` (8B) | ~900 (7k items ÷ batch 8) | ~400 chars/item, JSON batch | `GROQ_SMALL_RPM=25`, content-hash cache skips re-classify |
| **2E Theme labels** | `llama-3.3-70b-versatile` (70B) | **≤ 5** (one per theme) | Top quotes only (~2k tokens/call) | `GROQ_LARGE_RPM=25` |
| **3 Q&A synthesis** | 70B | **≤ 6** (Q1–Q6) | Retrieval-grounded, capped evidence | Same large-model limiter |
| **3 Segments / needs** | 70B | **≤ 3** | Rollup prompts only | Fits in **~14 calls/day** total for 70B |

**70B daily budget:** 5 + 6 + 3 ≈ **14 calls** ≪ 1,000 RPD. TPM stays low because
70B is not used for 7k-item loops.

**8B daily budget:** first run ≈ 900 calls; **re-runs ≈ 0** when `analyses` rows
already exist (cache). Batching + `GROQ_SMALL_RPM` keeps under typical 8B RPM limits.

Config: `GROQ_SMALL_RPM`, `GROQ_LARGE_RPM`, `CLASSIFICATION_BATCH_SIZE`,
`CLASSIFICATION_MAX_TEXT_CHARS`, `GROQ_MAX_RETRIES` (see `.env.example`).

---

### Phase 2A — Pipeline Scaffolding

**Goal:** A runnable, resumable analysis pipeline skeleton — no AI logic yet beyond wiring.

**Deliverables**
- `pipeline/` package with a stage interface (`run(session, settings, run_id) → stats`).
- `analyze` Typer CLI command (mirrors `ingest`): `--stage`, `--run-id`, dry-run/mock flags.
- Pipeline orchestrator: runs stages in order, updates `pipeline_runs.status` + `item_counts`.
- Stage-level logging, timing, and error handling (failed stage → run marked `failed`, prior stages kept).

**Key Tasks**
1. Add `backend/pipeline/` layout: `orchestrator.py`, `stages/base.py`, `cli.py` (or extend `ingestion.cli`).
2. Wire `analyze` into Makefile / entry points alongside `ingest`.
3. Stamp every stage output to the active `pipeline_run_id` (reuse ingestion run or create analysis run).
4. Add unit tests for orchestration with mocked stages (order, failure propagation, idempotent re-run).

**Exit criteria (sub-phase):** `analyze --dry-run` executes stage chain with mocks; run metadata written to `pipeline_runs`.

---

### Phase 2B — Per-Item Classification

**Goal:** Classify every `feedback_item` with structured Groq output stored in `analyses`.

**Deliverables**
- Classification prompts + Pydantic JSON schemas (sentiment label + score, listening intent, behavior signals, segment hint).
- `pipeline/stages/classify.py` + `pipeline/classifier.py`: **batched** Groq **8B** calls, validate/repair JSON, upsert `analyses`.
- Content-hash cache: skip items that already have an `analyses` row (idempotent re-run).
- Rate limiter (`core/rate_limit.py`) + config (`GROQ_SMALL_RPM`, `CLASSIFICATION_BATCH_SIZE`).
- Golden-set eval hook for sentiment accuracy (macro-F1 ≥ 80%) at `evals/golden/sentiment.json`.

**Key Tasks**
1. Define prompts in `core/prompts/classification.py` and schemas in `pipeline/schemas.py`.
2. Implement retry/repair loop on invalid JSON (re-prompt with error context, max N retries).
3. Batch **8 items/request** (configurable) on **8B only**; throttle to 25 RPM by default.
4. Write fixture-based tests (mock Groq) + golden-set unit test for sentiment.

**Exit criteria (sub-phase):** 100% of items in DB have a valid `analyses` row; cache hit on re-run; sentiment F1 ≥ 80% on golden set.

---

### Phase 2C — Embeddings & Vector Store

**Goal:** Generate local embeddings for all items and persist vectors in ChromaDB for clustering/retrieval.

**Deliverables**
- `pipeline/stages/embed.py` + `pipeline/embedder.py`: encode all items via `core/embeddings.py`.
- Default model **`BAAI/bge-small-en-v1.5`** (384-dim, cosine-normalized).
- Upsert to Chroma collection `feedback_embeddings` (id = `feedback_items.id`, metadata: source, date, content_hash).
- Content-hash cache: skip items already in Chroma with matching hash; delete orphan vectors.
- Chroma persistence dir from config (`CHROMA_PERSIST_DIR`); `reset_vector_store()` dev helper.

**Key Tasks**
1. Implement batch embedding (`EMBEDDING_BATCH_SIZE=64`) with progress logging (7k+ items).
2. Upsert/delete-sync Chroma so collection matches current `feedback_items` set.
3. Add smoke test: embed fixture items, query nearest neighbors, verify id round-trip.
4. Document Chroma as **analysis-only** (not needed on deployed API — see ADR-012).

**Exit criteria (sub-phase):** Chroma collection count == `feedback_items` count; similarity query returns valid Postgres IDs.

---

### Phase 2D — Theme Clustering

**Goal:** Deterministically cluster embedded feedback and enforce the **≤ 5 themes** hard rule.

**Deliverables**
- `pipeline/stages/cluster.py`: UMAP dimensionality reduction → HDBSCAN density clustering.
- Deterministic merge/trim algorithm when HDBSCAN produces > 5 clusters (merge smallest/nearest until ≤ 5).
- Stable cluster IDs across re-runs on the same input (seeded UMAP, fixed merge order).
- Intermediate assignments stored (cluster id per item) before LLM labeling.

**Key Tasks**
1. Implement clustering pipeline with configurable UMAP/HDBSCAN hyperparameters in settings.
2. Handle edge cases: fewer than 5 natural clusters, noise points (HDBSCAN label −1), very small clusters.
3. Assert `len(clusters) <= 5` in code (hard fail, not soft warning).
4. Unit tests on synthetic embedding fixtures (known cluster counts, merge behavior).

**Exit criteria (sub-phase):** clustering always yields 1–5 clusters; re-run on same data gives stable cluster membership (within tolerance).

---

### Phase 2E — Theme Labeling & Persistence

**Goal:** Name and summarize each cluster with Groq, then persist to `themes` and `feedback_themes`.

**Deliverables**
- `pipeline/stages/theme_labels.py`: for each cluster, pass top verbatim quotes to Groq **70B** model (**≤ 5 calls**).
- LLM outputs: theme name, one-line summary (no paraphrased quotes — labels/summaries only).
- `themes` rows: name, summary, mention_volume, sentiment_score, `pipeline_run_id`.
- `feedback_themes` rows: item ↔ theme membership from cluster assignments.
- Use `GROQ_LARGE_RPM` limiter (default 25 RPM) — well under 30 RPM / 1K RPD caps.

**Key Tasks**
1. Write theme-labeling prompt (top N quotes per cluster as evidence input).
2. Parse/validate LLM output; retry on schema failure.
3. Compute mention_volume and aggregate sentiment_score from per-item `analyses` in each cluster.
4. Upsert themes idempotently per run (replace or version by `pipeline_run_id`).

**Exit criteria (sub-phase):** `themes` count ≤ 5, every theme has name + summary + volume + sentiment; `feedback_themes` covers all classified items.

---

### Phase 2F — Evidence Selection & Rollups

**Goal:** Attach verbatim representative quotes to each theme and finalize Phase 2 metrics.

**Deliverables**
- Representative-quote selection: nearest-to-centroid items per cluster (verbatim text from `feedback_items`).
- Store quote IDs on `themes` (e.g. `representative_quote_ids` JSON column or join table).
- Per-theme rollup: volume, mean sentiment, source breakdown (app_store / play_store / social / …).
- `analyze` full run produces exportable summary (theme count, classification coverage, cache stats, token cost).

**Key Tasks**
1. Implement centroid-nearest quote picker using Chroma or numpy on UMAP coords.
2. Sanity-check: selected quotes belong to the theme's cluster (no cross-cluster leakage).
3. Add pipeline summary report (stdout + optional JSON artifact under `data/analyzed/`).
4. Run full Phase 2 eval gate on live ingested data (~7k items).

**Exit criteria (sub-phase):** every theme has ≥ 1 verbatim quote ID from DB; rollups match manual spot-check; Phase 2 eval checklist green.

---

### Phase 2 — Overall Deliverables (summary)

- Per-item classifier → `analyses` (sentiment, intent, behaviors, segment hint).
- Embeddings in ChromaDB (cached by content hash).
- Clustering → **≤ 5** themes with stable IDs.
- `themes` + `feedback_themes` populated with volume, sentiment, labels, summaries.
- Representative verbatim quotes per theme.

### Phase 2 — Exit Criteria (summary)

≤5 themes always; every theme has verbatim evidence; sentiment accuracy ≥ 80% vs
golden set; clustering stable on re-run. Full gate →
[`phase-2-analysis-core.eval.md`](./evals/phase-2-analysis-core.eval.md).

---

## Phase 3 — Discovery Q&A + Segmentation + Unmet Needs

**Goal:** Produce the intelligence that directly answers the problem statement:
all 6 questions, user segments, and the unmet-needs tracker.

**Deliverables**
- Retrieval-augmented Q&A for **Q1–Q6**: plain-language answer + cited quote IDs + confidence/frequency signal.
- Segmentation: named segments with per-segment top frustration / unmet need / behavior + comparative rollup.
- Unmet-needs extraction: ranked list, mention frequency, urgency score, source attribution.
- All outputs written to `answers`, `segments`, `unmet_needs` and stamped to a run.

**Key Tasks**
1. For each question, define an evidence-retrieval query + synthesis prompt.
2. Enforce grounding: answers must cite ≥N quotes or be marked low-confidence.
3. Aggregate segment hints into stable named segments with rollups.
4. Extract unmet needs (explicit wishes + workarounds), rank, score urgency.
5. Compute source attribution (cross-platform vs concentrated).

**Exit Criteria (summary):** all 6 answers present + grounded, no hallucinated
quotes, segments coherent, unmet needs ranked with attribution. Full gate →
[`phase-3-intelligence.eval.md`](./evals/phase-3-intelligence.eval.md).

---

## Phase 4 — Backend API

**Goal:** Expose all materialized intelligence through a clean, fast, documented REST API.

**Deliverables**
- Endpoints: `/overview`, `/themes`, `/themes/{id}`, `/questions`, `/quotes`, `/segments`, `/unmet-needs`, `/meta`.
- Filtering/pagination/search on `/quotes` (theme, source, rating, date, text).
- OpenAPI docs auto-generated; response schemas typed (Pydantic).
- API integration tests against a seeded test DB.

**Key Tasks**
1. Define Pydantic response models matching frontend needs.
2. Implement read-optimized queries (no heavy compute at request time).
3. Add pagination + filtering + full-text search for quotes.
4. Add caching headers + `/meta` freshness info.
5. Write integration tests + contract snapshot for the frontend.

**Exit Criteria (summary):** every endpoint returns correct shape, quote filters
work, p95 latency under target, no PII in any response. Full gate →
[`phase-4-api.eval.md`](./evals/phase-4-api.eval.md).

---

## Phase 5 — Frontend Dashboard

**Goal:** A beautiful, modern dashboard rendering all six required sections from live API data.

**Deliverables**
- Section 1 — Discovery Overview (totals, date range, source breakdown, sentiment chart, headline insight).
- Section 2 — Theme Clusters (≤5 cards + size visual + expand to quotes/sub-patterns).
- Section 3 — Q&A Intelligence Panel (6 panels with answer + evidence + confidence).
- Section 4 — Verbatim Quote Explorer (searchable/filterable table, tags, no PII).
- Section 5 — User Segment Breakdown (comparative, side-by-side).
- Section 6 — Unmet Needs Tracker (ranked, urgency color-coding, source attribution).
- Loading/empty/error states; responsive layout; data-freshness indicator.

**Key Tasks**
1. Scaffold app shell, routing/layout, theme, API client (TanStack Query).
2. Build shared components (cards, charts via Recharts, table via TanStack Table).
3. Implement each section against its endpoint.
4. Implement quote explorer filters bound to API params.
5. Polish UX (accessibility, responsiveness, empty/error states).

**Exit Criteria (summary):** all six sections render live data correctly, filters
work, no PII visible, no console errors, passes Lighthouse/a11y baseline. Full
gate → [`phase-5-frontend.eval.md`](./evals/phase-5-frontend.eval.md).

---

## Phase 6 — Integration & Definition of Done

**Goal:** The system runs end-to-end and is deployed (Render + Vercel); a
stakeholder can answer all DoD questions in under 5 minutes.

**Deliverables**
- One-time end-to-end run: ingest → analyze → serve → render.
- Deployed environment: backend live on Render, frontend live on Vercel, Postgres pre-populated by the one-time pipeline run.
- Seeded demo dataset + documented one-time pipeline run steps.
- README with local setup, one-time pipeline run, deploy instructions, and architecture overview link.
- DoD validation script/checklist mapping each DoD question to a dashboard element.
- Final eval pass across all phases (regression).

**Key Tasks**
1. Run the one-time pipeline locally (`run-all`) against Render Postgres; verify full snapshot populated.
2. Deploy backend to Render and frontend to Vercel; verify the live dashboard.
3. Confirm `/meta` reflects the snapshot date range and pipeline run stamp.
4. Write README + demo walkthrough; run the DoD validation checklist end-to-end.
5. Final hardening: error handling, logging, cost report.

**Exit Criteria (summary):** full pipeline runs clean from scratch, DoD's 5
questions answerable on the dashboard within 5 minutes, all prior eval gates still
green. Full gate → [`phase-6-integration.eval.md`](./evals/phase-6-integration.eval.md).

---

## Sequencing & Dependencies

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6
(scaffold)  (data)      (themes)    (Q&A/seg)   (API)       (UI)        (DoD)
                         2A→2F
```

Phase 2 sub-phases (see § Phase 2): **2A** scaffold → **2B** classify → **2C** embed → **2D** cluster → **2E** theme labels → **2F** evidence & rollups.

- Frontend (Phase 5) can start scaffolding in parallel with Phase 4 using mocked
  API contracts, but cannot pass its gate until Phase 4 is green.
- The AI eval harness (golden datasets, LLM-as-judge) is set up in Phase 0 and
  extended each phase.
