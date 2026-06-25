# Phase 0 Eval — Foundations & Scaffolding

**Goal under test:** the skeleton runs and is reproducible. No business logic yet.

## Tests
### Code / infra
- [ ] Local dev runs natively (no Docker): backend (`uvicorn`) and frontend (`vite`) start with no errors.
- [ ] Backend connects to Postgres via a `DATABASE_URL` (local Postgres or hosted free tier).
- [ ] Embedded ChromaDB (persistent dir) can create + query a test collection locally during analysis.
- [ ] `render.yaml` and `frontend/vercel.json` are present and valid (config lint passes).
- [ ] Alembic migration applies cleanly to an empty DB and creates all schema-v1 tables.
- [ ] Migration is reversible (`downgrade` then `upgrade` succeeds).
- [ ] Backend `GET /api/health` returns `200` with build/version info.
- [ ] Frontend dev server serves a placeholder page that calls `/api/health`.
- [ ] Groq LLM client + local embeddings + Chroma client run in **mock mode** with no API keys set.
- [ ] With a `GROQ_API_KEY` set, a smoke test gets a valid JSON completion from Groq.
- [ ] CI pipeline runs lint + type-check + unit tests and is green.

### Config / safety
- [ ] Settings load from env; missing required vars fail fast with a clear message.
- [ ] `.env` and secrets are git-ignored; no secret is committed (scan passes).

## Exit Criteria
- All checkboxes above pass.
- A new contributor can clone, follow the README, and reach a healthy local stack natively.
- Schema matches `architecture.md` §3.2 (reviewed).

## Out of scope (do NOT block on)
- Real data, real LLM calls, real UI sections.
