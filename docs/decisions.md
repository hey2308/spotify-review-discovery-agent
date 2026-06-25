# Decision Log

> Companion docs: [`architecture.md`](./architecture.md) · [`implementationPlan.md`](./implementationPlan.md) · [`problemStatement.md`](./problemStatement.md)

Record of significant **technical** and **business/product** decisions, with the
context, the choice, and the trade-offs. Format follows a lightweight ADR
(Architecture Decision Record) style. Add new entries at the bottom; never delete —
supersede instead.

Status legend: ✅ Accepted · 🔄 Superseded · 💭 Proposed

---

## ADR-001 — Backend & pipeline language: Python ✅
**Context:** The core work is AI/NLP analysis (LLMs, embeddings, clustering) plus a
web API.
**Decision:** Python 3.11 for both the analysis pipeline and the backend API.
**Why:** Richest AI/data ecosystem (sentence-transformers, UMAP, HDBSCAN, LLM
SDKs), and FastAPI gives a high-performance API in the same language — no
context-switch between pipeline and serving.
**Trade-offs:** Slower raw throughput than Go/Rust, but request-time work is light
(serving precomputed results), so this is irrelevant here.

## ADR-002 — Web framework: FastAPI ✅
**Context:** Need a typed, documented REST API the frontend consumes.
**Decision:** FastAPI + Uvicorn.
**Why:** Async, auto OpenAPI docs, Pydantic validation, minimal boilerplate.
**Trade-offs:** Not batteries-included like Django; acceptable since we don't need
an admin/ORM-heavy framework.

## ADR-003 — Data store: PostgreSQL (relational) + ChromaDB (vectors) ✅
**Context:** We need relational data (items, themes, answers) **and** vector
similarity (clustering, evidence retrieval).
**Decision:** PostgreSQL 16 as the relational source of truth (Render managed
Postgres free tier in production; Neon free tier is a drop-in alternative), plus
**ChromaDB** in **embedded persistent mode** for the one-time analysis run only.
Chroma vector ids equal the Postgres `feedback_items.id` so similarity results map
straight back to verbatim quotes. The deployed API reads only from Postgres — Chroma
is not required in production.
**Why:** ChromaDB is open-source, free, and trivial to run embedded locally during
the one-time pipeline. It ships built-in local embedding functions and keeps
clustering/evidence retrieval clean. All dashboard-facing results are materialized
into Postgres before deploy, so Render needs no vector store.
**Trade-offs:** Two stores during the one-time run (mitigated by the shared id
contract). Chroma data is ephemeral after analysis completes — only Postgres matters
for the live dashboard.
**Supersedes:** the earlier single-DB `pgvector` choice, per user direction to use ChromaDB.

## ADR-004 — LLM provider: Groq, tiered open models ✅
**Context:** AI must perform the analysis; cost, speed, and reproducibility matter.
**Decision:** Use **Groq** for all LLM inference, behind a thin client abstraction.
Tier the models: a **small fast model (e.g. Llama 3.1 8B Instant)** for high-volume
per-item classification, and a **stronger model (e.g. Llama 3.3 70B Versatile)** for
synthesis/labeling. All calls use **structured (JSON) outputs** with validation + repair.
**Why:** Groq's LPU inference is extremely fast and low-cost, has a generous free
tier (good for a grad project), serves strong open Llama models, and exposes an
OpenAI-compatible API so the client stays simple and swappable. Tiering keeps the
high-volume classification cheap while reserving the larger model for synthesis.
**Trade-offs:** Groq's JSON mode is slightly less strict than some providers'
native schema enforcement (mitigated by validation + repair), and it offers
**no embeddings endpoint** (handled by ADR-005). Two models to manage; mitigated by config.
**Supersedes:** the earlier provider-agnostic OpenAI/Anthropic default, per user direction to use Groq.

## ADR-005 — Embeddings: local sentence-transformers ✅
**Context:** Need embeddings for clustering and evidence retrieval, but Groq does
not provide an embeddings API.
**Decision:** Generate embeddings locally with a **sentence-transformers** model
(default `all-MiniLM-L6-v2`, optional `bge-small-en-v1.5`), wired in as ChromaDB's
embedding function so vectors are produced and stored consistently.
**Why:** Free, offline, and fast on CPU; pairs naturally with ChromaDB (ADR-003)
which supports sentence-transformers embedding functions out of the box. Keeps the
project fully runnable for grading without any embeddings API key.
**Trade-offs:** Slightly lower embedding quality than large hosted models; more
than sufficient for clustering review-length text. Local model adds a small
container/download footprint.

## ADR-006 — Clustering: UMAP + HDBSCAN, trimmed to ≤5 themes ✅
**Context:** Problem statement caps themes at **5**; we must not invent a fixed `k`.
**Decision:** UMAP dimensionality reduction → HDBSCAN density clustering →
deterministic merge/trim to at most 5 themes → LLM names each theme.
**Why:** HDBSCAN finds natural clusters without a preset count and handles noise;
we then enforce the ≤5 business constraint by merging the smallest/closest
clusters. Counting/clustering stays deterministic; only naming is generative.
**Trade-offs:** Merging may combine nuanced clusters; acceptable given the hard
5-theme cap, and sub-patterns are preserved within each theme.

## ADR-007 — Grounded, evidence-cited AI outputs ✅
**Context:** Constraints forbid invented quotes and require confidence signals.
**Decision:** Every AI answer/theme must cite stored verbatim quote IDs. Answers
lacking sufficient evidence are marked **low-confidence**, never fabricated. The
LLM never rewrites quotes — it only references them.
**Why:** Guarantees auditability, prevents hallucination, satisfies the
"verbatim only" and "confidence/frequency signal" requirements.
**Trade-offs:** Some questions may surface fewer confident answers; this is the
honest, correct behavior.

## ADR-008 — PII removed at ingestion, before storage ✅
**Context:** Hard privacy constraint: no usernames, emails, device IDs, or
reviewer PII in **any** artifact.
**Decision:** PII scrubbing runs in the ingestion layer **before** anything is
persisted. Redactions are marked `[redacted]`. A PII-audit scan is an eval gate
in every phase.
**Why:** Eliminates PII at the earliest point so no downstream store, log, API
response, or dashboard view can leak it.
**Trade-offs:** Aggressive scrubbing may redact a few false positives (e.g. a band
name resembling a handle); preferred over any leak risk.

## ADR-009 — Source selection: free public APIs only ✅
**Context:** Public data only; no login-gated scraping, no ToS violations, and
(per user direction) **no paid data APIs** — only free public APIs/feeds.
**Decision:** Use free, public access per source — Apple RSS reviews,
`google-play-scraper` (free library over public Play Store pages), **Reddit
official API (PRAW, free read-only OAuth app)**, Spotify Community public RSS, and
**Bluesky (AT Protocol public API) / Mastodon** for social. **X/Twitter is
excluded** — it has no usable free tier.
**Why:** Every path is free, public, and ToS-compatible. Bluesky/Mastodon give an
open, free, compliant social signal where X does not.
**Trade-offs:** Social volume may be lower than a paid X feed; acceptable, free, and
compliant. The connector interface lets us add another source later without
architectural change.

## ADR-010 — Orchestration: one-time CLI run, no scheduler ✅
**Context:** Reviews are fetched **once** to create the dashboard — no recurring
ingestion or refresh. The pipeline must still be reproducible for re-runs during
development, but there is no production scheduler.
**Decision:** A Typer-based CLI with idempotent stages (`ingest`, `analyze`,
`run-all`) invoked **manually once** before deploy. Each run is stamped in
`pipeline_runs`. The developer runs the full pipeline locally (with `DATABASE_URL`
pointing at Render Postgres), then deploys the API and frontend to serve the
static snapshot.
**Why:** Matches the product need (one snapshot dashboard), avoids any scheduler/
cron/CI batch job complexity, and keeps heavy embedding/LLM work off the Render
API host entirely.
**Trade-offs:** Dashboard data is static after the one-time run; refreshing requires
a manual re-run. Acceptable — explicitly out of scope.
**Supersedes:** the earlier GitHub Actions scheduled-pipeline approach.

## ADR-011 — Frontend stack: React + Vite + TS, Tailwind/shadcn, Recharts ✅
**Context:** Need a beautiful, modern, real (non-mock) interactive dashboard.
**Decision:** React 18 + TypeScript + Vite; Tailwind + shadcn/ui for UI; Recharts
for charts; TanStack Table + TanStack Query for the quote explorer and data fetching.
**Why:** Fast DX, strong typing against the API contract, polished components, and
charting/table libraries that fit the six required sections directly.
**Trade-offs:** Some setup overhead vs a no-build approach; justified by UX quality
and maintainability requirements.

## ADR-012 — Hosting: Render + Vercel, no Docker, no scheduler ✅
**Context:** The system must be deployable and runnable for free, **without Docker**,
and with a **one-time data fetch** (no recurring pipeline).
**Decision:** Run the ingestion+analysis pipeline **once locally** via the Typer CLI,
writing results to **Render managed PostgreSQL**. Deploy the FastAPI backend on
**Render** (free web service, via `render.yaml`) and the React/Vite frontend on
**Vercel**. Local dev runs natively (Python venv + Uvicorn, Node + Vite) — no
containers. A seeded demo dataset lets the dashboard be evaluated without running
the full pipeline. GitHub Actions is used for **CI only** (lint, test) — not data
fetching.
**Why:** All platforms have free tiers with first-class support for these runtimes
and Git-based deploys. A one-time local pipeline run is simpler than any scheduler
and keeps the always-on API within free-tier memory (read-only Postgres queries).
**Trade-offs:** Free tiers cold-start/sleep; dashboard is a static snapshot until
manually re-run. Slightly less identical local-vs-prod parity than Docker, mitigated
by matching runtime versions.
**Supersedes:** the earlier Docker Compose packaging and scheduled GitHub Actions
pipeline decisions, per user direction.

## ADR-013 — Phase gates driven by eval files ✅
**Context:** AI systems need explicit quality gates, not just unit tests.
**Decision:** Each phase has an `eval.md` under [`evals/`](./evals) defining tests +
exit criteria (code tests **and** AI-quality evals: golden sets, LLM-as-judge,
human spot checks). A phase isn't "done" until its gate passes.
**Why:** Makes "done" objective and catches AI-quality regressions the compiler can't.
**Trade-offs:** Up-front effort to build the eval harness; pays off in trust and
reproducibility — central to a grad project's defensibility.

## ADR-014 — Review lookback window: last 6 months ✅
**Context:** The problem statement originally specified 8–12 weeks; the project scope
was narrowed to a longer but fixed snapshot window.
**Decision:** Ingest and analyze only feedback from the **last 6 months** (rolling
from the pipeline run date). Enforced in connector windowing and validated in Phase 1
evals.
**Why:** Broader signal for theme clustering and segment analysis while keeping the
one-time fetch bounded and reproducible.
**Trade-offs:** Larger volume than 8–12 weeks → longer one-time pipeline run and
higher Groq token cost; mitigated by caching and tiered models.

---

## Open Questions / To Revisit
- 💭 Whether to add X/Twitter as a source if API budget becomes available (ADR-009).
- 💭 Whether to localize/translate non-English reviews before analysis.
