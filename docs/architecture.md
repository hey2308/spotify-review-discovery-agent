# Architecture — Spotify Discovery Intelligence Agent

> Companion docs: [`problemStatement.md`](./problemStatement.md) · [`implementationPlan.md`](./implementationPlan.md) · [`decisions.md`](./decisions.md) · [`deploymentPlan.md`](./deploymentPlan.md) · [`evals/`](./evals)

This document describes the end-to-end system that turns scattered public Spotify
feedback into structured, dashboard-ready intelligence answering the 6 discovery
questions defined in the problem statement.

---

## 1. System at a Glance

```
                         ┌──────────────────────────────────────────────────┐
                         │                  DATA SOURCES                     │
                         │  App Store · Play Store · Reddit · Community ·    │
                         │  Social (Bluesky/Mastodon)                        │
                         └───────────────┬──────────────────────────────────┘
                                         │  (public APIs / RSS only)
                                         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  INGESTION LAYER                                                            │
│  Source connectors → normalize → PII scrub → dedup (content hash) → store   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  STORAGE                                                                    │
│  PostgreSQL (relational): raw_documents · feedback_items · themes ·         │
│                           analyses · answers · segments · unmet_needs       │
│  ChromaDB (vectors):      embeddings + metadata for clustering & retrieval  │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  AI ANALYSIS PIPELINE (the "agent") — LLM inference via Groq               │
│  1. Sentiment + intent classification (LLM, structured output)             │
│  2. Embeddings → UMAP → HDBSCAN → merge to ≤5 themes → LLM labels          │
│  3. Segment extraction from review language                                 │
│  4. Discovery Q&A synthesis (Q1–Q6) with evidence + confidence             │
│  5. Unmet-needs extraction & urgency scoring                                │
│  Every claim is grounded in stored verbatim quotes (citations).            │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  API LAYER (FastAPI REST)                                                   │
│  /overview /themes /questions /quotes /segments /unmet-needs /meta          │
└───────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  FRONTEND DASHBOARD (React + Vite + TS)                                     │
│  6 sections: Overview · Themes · Q&A · Quote Explorer · Segments · Needs   │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Why "Agent"?

The AI analysis pipeline is **agentic** rather than a single prompt: it runs a
multi-step, tool-using workflow with explicit state, retries, and self-grounding.

- **Tools the agent uses:** SQL retrieval (fetch candidate quotes from Postgres),
  embedding search (ChromaDB similarity query to find evidence for a claim), and
  structured-output LLM calls (Groq).
- **Grounding loop:** every generated answer must cite stored verbatim quotes by
  ID. Answers without sufficient evidence are flagged low-confidence rather than
  hallucinated.
- **Deterministic skeleton, generative content:** clustering and counting are
  deterministic; only labeling, summarizing, and Q&A synthesis use the LLM. This
  keeps results reproducible and auditable.

---

## 3. Component Breakdown

### 3.1 Ingestion Layer
Each source has an isolated **connector** implementing a common interface so new
sources can be added without touching the pipeline.

**Free, public, no-paid-key sources only** — every connector uses a free public API
or feed, with no login-gated scraping and no paid data APIs.

| Connector | Access method (free + public) | Notes |
|---|---|---|
| App Store | Apple RSS customer-reviews JSON endpoint | No auth, free, per-country; ~50 reviews per feed (single page) |
| Play Store | `google-play-scraper` (public listing data) | Free library over public pages; **paginated** via continuation token (200/page, up to 3,000 reviews, early exit at 6-month boundary); rate-limited |
| Reddit | Official Reddit API via PRAW (free read-only OAuth app) | Subreddits: r/spotify, r/Music, r/ifyoulikeblank |
| Community | Spotify Community public RSS/Atom (Khoros boards) | Free public threads only |
| Social | Bluesky (`api.bsky.app` search) / Mastodon (public tag timelines) | Bluesky: **time-slice** pagination via `since`/`until` (100/query/slice, 17 queries); Mastodon: **`max_id`** pagination (40/page, up to 50 pages/tag/instance); cap **3,000** unique posts (`SOCIAL_MAX_ITEMS`); X excluded |

Pipeline per connector: **fetch → map to canonical schema → strip PII → hash &
dedup → upsert**. All connectors are idempotent and windowed to the **last 6 months**.

**Play Store fetch strategy:** reviews are sorted newest-first. The connector
requests pages of 200 (`PLAY_STORE_PAGE_SIZE`) and follows the scraper's
continuation token until either (a) **3,000** reviews are collected
(`PLAY_STORE_MAX_REVIEWS`), (b) the token is exhausted, or (c) the oldest review
in a batch is older than the 6-month window — then pagination stops and only
in-window items are kept.

### 3.2 Storage (PostgreSQL + ChromaDB)
Two complementary stores: **PostgreSQL** is the relational source of truth for all
structured data, and **ChromaDB** holds the embedding vectors used for clustering
and evidence retrieval. They are linked by a shared `feedback_item` id: every
Chroma vector's id equals its Postgres `feedback_items.id`, so a similarity query
returns ids that map straight back to verbatim quotes.

**PostgreSQL — core tables** (see [`decisions.md`](./decisions.md) for rationale):
- `raw_documents` — untouched fetched payloads (provenance / re-processing).
- `feedback_items` — canonical, PII-scrubbed unit of feedback (one review/post/comment).
- `themes` — ≤5 clusters with name, sentiment score, mention volume.
- `feedback_themes` — item↔theme membership.
- `segments` — derived user segments + per-segment rollups.
- `analyses` — per-item AI outputs (sentiment, intent, segment hint, behaviors).
- `answers` — Q1–Q6 synthesized answers + evidence quote IDs + confidence.
- `unmet_needs` — ranked needs, frequency, urgency, source attribution.
- `pipeline_runs` — run metadata for reproducibility & dashboard "last updated".

**ChromaDB — vector collection:**
- `feedback_embeddings` — one persisted vector per feedback item, keyed by the
  Postgres item id, with light metadata (source, date, theme id) for filtered
  similarity search. Embeddings are produced by a local sentence-transformers
  model (Groq does not serve embeddings — see ADR-005). **Local dev:** Chroma runs
  embedded in persistent mode (a local directory). Used only during the **one-time
  analysis run** — the deployed API reads materialized results from Postgres and
  does not query Chroma at request time (see ADR-012).

### 3.3 AI Analysis Pipeline
Stages run in order; each stage is independently re-runnable. Structured results
are written to Postgres and vectors to ChromaDB, so partial failures are
recoverable. All LLM calls run on **Groq** (see ADR-004).

1. **Per-item classification** — sentiment (pos/neu/neg + score), listening intent
   (Q3), behavior signals (Q4), segment hint (Q5). Groq LLM with JSON-schema output.
2. **Theme clustering** — embed (local model) & upsert to ChromaDB → UMAP reduce →
   HDBSCAN cluster → deterministically merge/trim to **max 5** themes → Groq LLM
   names each theme and writes a summary.
3. **Segmentation** — aggregate segment hints into named segments with per-segment
   top frustration / unmet need / behavior.
4. **Discovery Q&A (Q1–Q6)** — retrieval-augmented synthesis: pull top evidence
   per question, generate plain-language answer + cited quote IDs + confidence.
5. **Unmet needs (Q6)** — extract explicit wishes/workarounds, rank by frequency,
   score urgency by emotional intensity, attribute across sources.

### 3.4 API Layer (FastAPI)
Thin, read-optimized REST API serving precomputed analysis. No heavy compute at
request time — the dashboard reads materialized results.

Representative endpoints:
- `GET /api/overview` — totals, date range, source breakdown, sentiment dist, headline insight.
- `GET /api/themes` — ≤5 themes with volume + sentiment; `GET /api/themes/{id}` for quotes/sub-patterns.
- `GET /api/questions` — all 6 answers with evidence + confidence.
- `GET /api/quotes` — filterable/paginated verbatim quotes (theme, source, rating, date, search).
- `GET /api/segments` — segment comparison data.
- `GET /api/unmet-needs` — ranked needs with urgency + attribution.
- `GET /api/meta` — last run time, counts, data freshness.

### 3.5 Frontend Dashboard (React + Vite + TS)
SPA mapping 1:1 to the six required dashboard sections, using TanStack Query for
data fetching, Recharts for visuals, and TanStack Table for the quote explorer.
Styled with Tailwind + shadcn/ui. Designed so the [Definition of Done](./problemStatement.md)
questions are answerable within 5 minutes.

---

## 4. Tech Stack Summary

| Layer | Choice | Rationale (full detail in `decisions.md`) |
|---|---|---|
| Pipeline & backend | Python 3.11, FastAPI, Uvicorn | Best-in-class for AI/data + fast REST |
| Relational store | PostgreSQL 16 | Structured source of truth |
| Vector store | ChromaDB (persistent) | Embeddings for clustering + retrieval |
| ORM / migrations | SQLAlchemy 2.x + Alembic | Schema versioning, reproducibility |
| LLM | Groq (Llama 3.x family; tiered 8B / 70B) | Fast inference, JSON output, low cost |
| Embeddings | Local sentence-transformers (`all-MiniLM-L6-v2` / `bge-small`) | Free/offline; Groq has no embeddings API |
| Clustering | UMAP + HDBSCAN | Density-based, no fixed k, then trim ≤5 |
| Orchestration | Typer CLI, one-time manual run (no scheduler) | Fetch once, analyze once, serve static dashboard |
| Frontend | React 18 + TypeScript + Vite | Modern, fast DX |
| UI / charts / table | Tailwind + shadcn/ui, Recharts, TanStack Table/Query | Beautiful, standard |
| Backend hosting | Render (free web service) | Free Python/FastAPI hosting + managed Postgres |
| Frontend hosting | Vercel | First-class Vite/React hosting, free tier |
| Local dev | Native (Python venv + Uvicorn, Node + Vite) — no Docker | Lightweight; matches hosted runtimes |
| Testing | pytest, Vitest + RTL, AI eval harness | Code + AI-quality coverage |

### 4.1 Deployment Topology

No Docker. No scheduler. Reviews are fetched **once** to build the dashboard; the
deployed app serves that static snapshot.

```
One-time (local / manual CLI)         Render (web service)        Vercel
──────────────────────────────        ────────────────────        ──────────────
Pipeline: ingest → analyze    ──────▶ FastAPI reads &        ◀──── React dashboard
writes results to:                    precomputed results            (static SPA,
  • Render Postgres                   from Postgres only             calls Render API)
  • Chroma (local, analysis only)
```

- **One-time pipeline:** run locally via Typer CLI (`ingest` → `analyze`) **once**
  before deploy. Pulls the **last 6 months** of public feedback from free public APIs,
  runs the full AI pipeline, and writes materialized results to **Render Postgres**.
  Chroma is used only during this run (embedded locally) for clustering/evidence
  retrieval — it is **not** needed on the deployed API host.
- **Backend (FastAPI):** deployed on **Render** as a free web service (`render.yaml`),
  serving read-only precomputed results from Postgres. No embedding or LLM work at
  request time.
- **Frontend (React/Vite):** deployed on **Vercel**; talks to the Render API via a
  configured base URL.
- **Relational DB:** **Render managed PostgreSQL** (free tier) holds the full
  snapshot. (Neon free tier is a drop-in alternative.)
- **CI (GitHub Actions):** lint, type-check, and unit tests on push only — **not**
  a scheduled data pipeline.
- **Secrets:** `GROQ_API_KEY`, `DATABASE_URL`, and source API keys are used during
  the one-time local pipeline run and in Render env vars for the API — never committed.

---

## 5. Cross-Cutting Concerns

- **Privacy (hard constraint):** PII scrubbing happens at ingestion *before*
  storage. No usernames, emails, device IDs, or handles persist anywhere. A
  PII-scan eval gate runs every phase.
- **Verbatim integrity:** quotes are stored and displayed exactly as ingested
  (only PII redacted with `[redacted]` markers). The LLM never rewrites quotes;
  it only references them by ID.
- **Reproducibility:** every artifact links to a `pipeline_run`. Same input
  window + same model version → comparable output.
- **Cost control:** classification uses the smaller Groq model (e.g. Llama 3.1 8B);
  only synthesis/labeling uses the larger Groq model (e.g. Llama 3.3 70B).
  Embeddings run locally (free) and Groq calls are cached by content hash.
- **Auditability:** every AI claim on the dashboard is traceable to source quotes.
- **Configurability:** sources, date window (**last 6 months**), model, and theme count live in config.

---

## 6. Data Flow (Runtime)

1. **One-time ingestion** pulls public feedback for the **last 6 months** from all
   sources, scrubs PII, dedups, and upserts into `feedback_items` + `raw_documents`.
2. **One-time analysis** classifies all items, clusters themes (≤5), derives
   segments, synthesizes Q1–Q6 with evidence, and extracts unmet needs. Vectors
   live in local Chroma during this step; all dashboard-facing results are written
   to Postgres and stamped with a `pipeline_run`.
3. **Deploy** the pre-populated Postgres snapshot to Render; deploy the frontend to Vercel.
4. **API** serves the static materialized results; **frontend** renders the six sections.
5. Stakeholder opens the dashboard and answers the Definition-of-Done questions.

There is no recurring fetch or refresh — the dashboard reflects the one-time snapshot.

---

## 7. Repository Layout (target)

```
Grad_Project/
├── docs/                      # this folder
│   ├── architecture.md
│   ├── implementationPlan.md
│   ├── decisions.md
│   ├── problemStatement.md
│   └── evals/                 # per-phase test + exit criteria
├── backend/
│   ├── app/                   # FastAPI app + routers
│   ├── ingestion/             # source connectors + normalization + PII scrub
│   ├── pipeline/              # analysis stages (classify, cluster, qa, needs)
│   ├── db/                    # models, migrations (alembic)
│   ├── core/                  # config, Groq LLM client, embeddings, Chroma client, prompts
│   └── tests/
├── frontend/
│   ├── src/                   # React app, 6 sections, components, api client
│   ├── vercel.json            # Vercel deploy config
│   └── tests/
├── evals/                     # AI-quality eval harness + golden datasets
├── .github/workflows/         # CI only (lint, test) — no scheduled pipeline
├── render.yaml                # Render backend + managed Postgres
└── README.md
```
