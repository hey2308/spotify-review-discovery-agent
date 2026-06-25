# Spotify Discovery Intelligence Agent

Turn scattered public Spotify feedback into structured, dashboard-ready intelligence.

## Docs

- [Problem statement](docs/problemStatement.md)
- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementationPlan.md)
- [Decisions](docs/decisions.md)
- [Phase evals](docs/evals/)

## Phase 0 — Quick start (native, no Docker)

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL (local or hosted free tier, e.g. Render / Neon)

### 1. Configure environment

```bash
cp .env.example .env
# Edit DATABASE_URL and optional GROQ_API_KEY
```

### 2. Install dependencies

```bash
make install
```

### 3. Run database migrations

```bash
make migrate
```

### 4. Start backend and frontend

In one terminal:

```bash
make backend
```

In another terminal:

```bash
make frontend
```

- API: http://localhost:8000/api/health
- Frontend: http://localhost:5173 (proxies `/api` to the backend)

Without `GROQ_API_KEY`, the backend runs in **mock mode** (no paid LLM calls).

### 5. Run tests and lint

```bash
make test
make lint
```

## Repository layout

```
backend/
  app/          # FastAPI routers (Phase 4+)
  core/         # config, Groq LLM, embeddings, Chroma
  db/           # SQLAlchemy models + Alembic migrations
  ingestion/    # Phase 1 — source connectors
  pipeline/     # Phases 2–3 — AI analysis stages
  tests/
frontend/
  src/sections/ # Phase 5 — dashboard sections
  src/components/
evals/golden/   # AI-quality golden datasets
docs/           # architecture, plan, decisions, per-phase evals
```

## Deployment

See **[Deployment plan](docs/deploymentPlan.md)** for the full Render + Vercel guide.

- **Backend:** Render (`render.yaml`) — API-only install (`pip install .`) + managed Postgres + auto-migrations on deploy
- **Frontend:** Vercel (`frontend/vercel.json`, root dir `frontend`)
- **Pipeline:** one-time local CLI run (`ingest` → `analyze`) before deploy — requires `pip install -e ".[pipeline]"` or `make install`

Set `VITE_API_BASE_URL` on Vercel to your Render API URL.

## Current status

**Phase 1 complete:** ingestion CLI, 5 source connectors, PII scrubbing, dedup, schema storage.

### Run ingestion (live — needs Postgres + optional API keys)

```bash
make migrate
make ingest
# or: cd backend && ingest ingest --source app_store --months 6
```

Live Reddit fetch requires `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env`.
