# Deployment Plan — Render (Backend) + Vercel (Frontend)

> Companion docs: [`architecture.md`](./architecture.md) · [`implementationPlan.md`](./implementationPlan.md) · [`decisions.md`](./decisions.md) (ADR-012)

This document is the step-by-step guide for deploying **Spotify Discovery Intelligence** to production:

| Component | Platform | Role |
|---|---|---|
| React dashboard | **Vercel** | Static SPA; calls the Render API |
| FastAPI API | **Render** | Read-only REST API over precomputed Postgres data |
| PostgreSQL | **Render** (managed) | Source of truth for the dashboard snapshot |
| Ingestion + AI pipeline | **Local machine** (one-time) | Fetches data, runs analysis, writes to Render Postgres |

There is **no Docker**, **no scheduler**, and **no recurring pipeline** in production. The live app serves a **static snapshot** produced by a one-time local CLI run before deploy. See [`architecture.md` §4.1](./architecture.md) for the topology rationale.

---

## 1. Deployment Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ONE-TIME (your laptop, before go-live)                                  │
│  ingest → analyze  ──writes──▶  Render PostgreSQL                       │
│  (ChromaDB stays local; not deployed)                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────┐     ┌──────────────────────────┐
│  Render Web Service      │     │  Vercel                  │
│  FastAPI (read-only)     │◀────│  React + Vite SPA        │
│  /api/*                  │     │  VITE_API_BASE_URL       │
└──────────────────────────┘     └──────────────────────────┘
```

**Config files already in the repo:**

- [`render.yaml`](../render.yaml) — Render Blueprint (Postgres + API web service)
- [`frontend/vercel.json`](../frontend/vercel.json) — SPA rewrites for client-side routing

---

## 2. Prerequisites

### Accounts & access

- [Render](https://render.com) account (free tier is sufficient for demo/grad project)
- [Vercel](https://vercel.com) account
- Git repository connected to both platforms (GitHub recommended)
- [Groq](https://console.groq.com) API key for the **one-time analysis run** (optional Reddit keys if ingesting Reddit live)

### Local machine (for pipeline + migrations)

- Python **3.11+**
- Node.js **20+** (only needed if you want to verify the frontend build locally)
- Repo cloned and dependencies installed:

```powershell
cd c:\Projects\Grad_Project
make install
```

### What is *not* deployed

| Item | Where it runs | Why |
|---|---|---|
| ChromaDB / embeddings index | Local only during `analyze` | Analysis-time retrieval; API reads materialized Postgres results |
| `ingest` / `analyze` CLIs | Local only | Heavy CPU/RAM/LLM work kept off the free Render web service |
| SQLite (`data/spotify_discovery.db`) | Local dev only | Production uses Render Postgres |

---

## 3. Environment Variables

### 3.1 Render — API web service

Set in the Render dashboard (or via Blueprint + manual secrets). The Blueprint in `render.yaml` wires `DATABASE_URL` automatically from the managed database.

| Variable | Required | Example / notes |
|---|---|---|
| `DATABASE_URL` | Yes | Auto-injected from `spotify-discovery-db` via Blueprint |
| `APP_ENV` | Yes | `production` (set in `render.yaml`) |
| `CORS_ORIGINS` | Yes | `https://your-app.vercel.app` (comma-separated if multiple) |
| `GROQ_API_KEY` | No for API | Omit on API if you only serve precomputed data; API runs in mock mode without it |
| `APP_VERSION` | No | Defaults to `0.1.0` |
| `LOG_LEVEL` | No | `INFO` recommended in production |

**`DATABASE_URL` format:** Render provides `postgresql://…`. SQLAlchemy in this project uses **psycopg v3**, so convert to:

```text
postgresql+psycopg://USER:PASSWORD@HOST/DATABASE
```

If the Blueprint injects `postgresql://`, the backend **auto-normalizes** it to
`postgresql+psycopg://` and adds `sslmode=require` for Render hosts — no manual edit needed.

### 3.2 Render — managed PostgreSQL

No manual env vars. Copy the **External Database URL** from the Render Postgres dashboard when running migrations or the pipeline from your laptop.

### 3.3 Vercel — frontend

| Variable | Required | Example |
|---|---|---|
| `VITE_API_BASE_URL` | Yes | `https://spotify-discovery-api.onrender.com` |

Rules:

- Use the **full origin** of the Render API (scheme + host, **no trailing slash**).
- Rebuild/redeploy the frontend after changing this value (`VITE_*` vars are baked in at build time).
- Do **not** commit production URLs to `.env` in the repo.

### 3.4 Local — one-time pipeline run

Create a local `.env` (from [`.env.example`](../.env.example)) pointing at **Render Postgres**:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/spotify_discovery
GROQ_API_KEY=gsk_...
REDDIT_CLIENT_ID=...        # optional
REDDIT_CLIENT_SECRET=...    # optional
CHROMA_PERSIST_DIR=./chroma_data
```

Keep `GROQ_API_KEY` and source API keys on your machine only during the pipeline run. They are **not** required on the deployed API unless you plan to re-run analysis on Render (out of scope).

---

## 4. Deployment Sequence

Follow this order. Skipping the pipeline step yields an empty dashboard (API returns zeros / empty lists).

### Step 1 — Provision Render infrastructure

**Option A — Blueprint (recommended)**

1. Push the repo to GitHub.
2. In Render: **New → Blueprint** → connect the repo.
3. Render reads [`render.yaml`](../render.yaml) and creates:
   - `spotify-discovery-db` (PostgreSQL, free tier)
   - `spotify-discovery-api` (Python web service, free tier)
4. Wait for the initial deploy to finish (it may fail health checks until migrations + data exist — expected).

**Option B — Manual**

1. Create a **PostgreSQL** instance named `spotify-discovery-db`.
2. Create a **Web Service**:
   - **Root directory:** `backend`
   - **Runtime:** Python 3
   - **Build command:** `pip install .`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/api/health`
3. Link `DATABASE_URL` from the database to the web service.

### Step 2 — Apply database migrations

Run Alembic **against Render Postgres** from your local machine:

```powershell
cd c:\Projects\Grad_Project

# Ensure .env DATABASE_URL points at Render (postgresql+psycopg://…)
make migrate
```

Verify tables exist (optional):

```powershell
cd backend
python -c "from db.session import get_engine; print(get_engine().connect().exec_driver_sql('SELECT 1').scalar())"
```

**Optional hardening:** add a Render pre-deploy hook so migrations run on every API deploy:

```yaml
# render.yaml — add under the web service
preDeployCommand: alembic upgrade head
```

### Step 3 — Run the one-time pipeline (populate Postgres)

Point `DATABASE_URL` at Render Postgres, then ingest and analyze:

```powershell
cd c:\Projects\Grad_Project\backend

# 1) Fetch ~6 months of public feedback (hours depending on sources/throttling)
ingest ingest --months 6

# 2) Run full AI analysis (classification → themes → Q&A → segments → unmet needs)
analyze analyze
```

Notes:

- **Resume:** if `analyze` fails mid-run, resume with `analyze analyze --run-id <uuid>`.
- **Dry run / mock:** `analyze analyze --dry-run` writes run metadata only — useful for smoke tests, not for production data.
- **Chroma** data is written to local `CHROMA_PERSIST_DIR`; it is not uploaded to Render.
- Expect **several GB** of model download on first run (sentence-transformers). Ensure stable network and disk space.
- Groq rate limits apply; tune `GROQ_SMALL_RPM` / `GROQ_LARGE_RPM` in `.env` if you hit 429s.

Confirm data landed:

```powershell
# Quick API check against local uvicorn pointed at Render DB, or after Step 4:
curl https://YOUR-API.onrender.com/api/overview
curl https://YOUR-API.onrender.com/api/meta
```

`/api/meta` should report the pipeline run ID and snapshot date range.

### Step 4 — Configure and deploy the Render API

1. In Render → `spotify-discovery-api` → **Environment**:
   - Set `CORS_ORIGINS` to your Vercel URL (you can update after Step 5 if the URL is not known yet).
   - Confirm `DATABASE_URL` is set (Render injects `postgresql://`; the app normalizes it automatically).
2. Trigger **Manual Deploy** (or push to the tracked branch).
3. Wait for `/api/health` to return `200`:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "mock_mode": "true"
}
```

`mock_mode: true` on the API is expected when `GROQ_API_KEY` is unset — the API only reads Postgres.

### Step 5 — Deploy the frontend on Vercel

1. In Vercel: **Add New Project** → import the Git repo.
2. **Root Directory:** `frontend`
3. **Framework Preset:** Vite
4. **Build Command:** `npm run build` (default)
5. **Output Directory:** `dist` (default)
6. **Environment variable:**

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://spotify-discovery-api.onrender.com` |

7. Deploy.

[`frontend/vercel.json`](../frontend/vercel.json) already configures SPA fallback (`/* → /index.html`) so section navigation works on refresh.

### Step 6 — Wire CORS (final)

1. Copy the production Vercel URL (e.g. `https://spotify-discovery.vercel.app`).
2. In Render → `CORS_ORIGINS`:

   ```text
   https://spotify-discovery.vercel.app
   ```

   For preview deployments, add comma-separated origins:

   ```text
   https://spotify-discovery.vercel.app,https://spotify-discovery-*.vercel.app
   ```

   (Render does not support wildcards in CORS — list each preview origin you need, or use only the production URL.)

3. Redeploy the API service after changing `CORS_ORIGINS`.

### Step 7 — Production smoke test

| Check | Command / action | Expected |
|---|---|---|
| API health | `GET /api/health` | `status: ok` |
| OpenAPI | `GET /api/docs` | Swagger UI loads |
| Overview data | `GET /api/overview` | Non-zero `total_items`, valid `date_range` |
| Meta stamp | `GET /api/meta` | `pipeline_run_id` present |
| Frontend loads | Open Vercel URL | Dashboard renders six sections |
| Browser network | DevTools → Network | `/api/*` calls go to Render origin, no CORS errors |
| Quote explorer | Filter + paginate | Results update without console errors |

---

## 5. Platform-Specific Notes

### 5.1 Render free tier

- **Cold starts:** the web service spins down after inactivity; first request may take 30–60s.
- **Memory:** the API installs the full backend package (including ML libraries). If the service crashes on boot, upgrade to a paid instance or split API-only dependencies in a future refactor.
- **Postgres:** free database expires after 90 days of inactivity; back up or re-run the pipeline if the instance is recycled.
- **Build time:** `pip install .` pulls heavy packages; first deploy can take several minutes.

### 5.2 Vercel

- `VITE_API_BASE_URL` is embedded at **build time**. Changing the API URL requires a **redeploy**.
- Local dev uses the Vite proxy (`/api → localhost:8000`); production calls the absolute Render URL from `client.ts`.
- Custom domains: add in Vercel project settings, then add the custom origin to Render `CORS_ORIGINS`.

### 5.3 CI (GitHub Actions)

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs lint, test, and frontend build on push. It does **not** deploy or run the pipeline. Deploys are triggered by Render/Vercel Git integrations.

---

## 6. Refreshing Dashboard Data

To update the snapshot (manual, out of band):

1. Point local `.env` `DATABASE_URL` at Render Postgres.
2. Re-run `ingest ingest --months 6` (or targeted `--source`).
3. Re-run `analyze analyze` (or resume with `--run-id`).
4. Verify `/api/meta` on Render reflects the new run.
5. No frontend redeploy needed unless API URL changed.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CORS error in browser | `CORS_ORIGINS` missing Vercel URL | Add exact origin on Render; redeploy API |
| `fetch` failed / network error | Wrong `VITE_API_BASE_URL` | Set to Render HTTPS origin; redeploy Vercel |
| Empty dashboard sections | Pipeline not run against prod DB | Run Steps 2–3 against Render Postgres |
| `relation does not exist` | Migrations not applied | `make migrate` with Render `DATABASE_URL` |
| DB connection refused | Wrong URL scheme or SSL | Use `postgresql+psycopg://`; check Render external URL |
| API 502 / OOM on boot | Free tier memory | Upgrade Render plan or slim API dependencies |
| Slow first load | Render cold start | Wait and retry; consider paid tier for always-on |
| `mock_mode: true` warnings | No `GROQ_API_KEY` on API | Expected for read-only API; add key only if needed |

---

## 8. Security Checklist

- [ ] `.env` is gitignored; no secrets in the repository
- [ ] `GROQ_API_KEY` and Reddit credentials used only locally for pipeline runs
- [ ] Render Postgres external URL is not committed or shared publicly
- [ ] `CORS_ORIGINS` lists only trusted frontend origins (not `*`)
- [ ] Vercel environment variables scoped to Production (and Preview if needed)

---

## 9. Custom Domains (Optional)

| Service | Steps |
|---|---|
| **Vercel** | Project → Domains → add `dashboard.example.com` → configure DNS |
| **Render** | Service → Settings → Custom Domains → add `api.example.com` |
| **CORS** | Set `CORS_ORIGINS=https://dashboard.example.com` |
| **Frontend** | Set `VITE_API_BASE_URL=https://api.example.com` and redeploy |

---

## 10. Definition of Done (Deploy Gate)

Aligns with [`phase-6-integration.eval.md`](./evals/phase-6-integration.eval.md):

- [ ] Render Postgres provisioned and migrations at `head`
- [ ] One-time pipeline completed; `/api/overview` and `/api/meta` return live snapshot data
- [ ] Render API reachable at `/api/health` and `/api/docs`
- [ ] Vercel frontend loads all six dashboard sections with live data
- [ ] No CORS or console errors in production
- [ ] Stakeholder can answer the five Definition-of-Done questions from the live dashboard in under 5 minutes

---

## 11. Quick Reference Commands

```powershell
# Local install
make install

# Migrations (DATABASE_URL → Render Postgres)
make migrate

# One-time data pipeline
cd backend
ingest ingest --months 6
analyze analyze

# Local verification before deploy
make backend          # terminal 1 — optional, against Render DB
make frontend         # terminal 2 — uses Vite proxy

# Production URLs (after deploy)
# API:    https://<render-service>.onrender.com/api/health
# Docs:   https://<render-service>.onrender.com/api/docs
# UI:     https://<vercel-project>.vercel.app
```
