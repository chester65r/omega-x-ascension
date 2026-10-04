# OMEGA-X ASCENSION — Base44 Dev Environment

## Project overview
Python/FastAPI modular monolith (backend-only, no frontend). PostgreSQL/pgvector for state, Redis for coordination, LangGraph for workflows, OpenAI-compatible model endpoints for LLM inference. API serves on port 8000 (mapped to host 3000 in Base44 compose).

## Architecture
- **api** — uvicorn dev server with `--reload`, serves FastAPI app at `omega.main:app`
- **worker** — `python -m omega.worker`, leases durable jobs and runs LangGraph workflows
- **migrate** — one-shot: creates DB roles (omega_app, omega_worker, omega_checkpoint), runs Alembic migrations, sets up LangGraph checkpoint tables
- **postgres** — pgvector/pgvector:pg16 with pgcrypto + vector extensions (init.sql)
- **redis** — redis:7-alpine with append-only persistence

## Setup
- Source lives in `omega-x-ascension/` subdirectory (not repo root)
- Local infra credentials (DB passwords, Redis password, JWT signing key) are generated in `.env.base44-defaults` at repo root (gitignored)
- `docker-compose.base44.yml` at repo root bind-mounts `./omega-x-ascension` to `/app` and installs deps via `pip install -e .` on each service startup
- All services use `python:3.12-slim` base image (never a prebuilt app image)

## Boot order
postgres (healthy) → migrate (completed) → api + worker (parallel)

## Health endpoints
- `GET /health/live` — liveness (always ok)
- `GET /health/ready` — readiness (checks DB + Redis connectivity)
- `GET /metrics` — Prometheus metrics

## API (requires signed JWT Bearer token)
- `POST /v1/runs` — create workflow run (scope: `runs:write`)
- `GET /v1/runs/{run_id}` — get run status (scope: `runs:read`)
- `POST /v1/runs/{run_id}/approve` — approve gated run (scope: `runs:approve`)
- JWT must have `sub`, `tenant_id`, `scope`, `iss`, `aud`, `iat`, `exp` claims

## External credentials
- `OMEGA_MODEL_PROVIDERS` — JSON array of LLM endpoints. Optional; defaults to `[]`. Without a provider, the app boots and health endpoints work, but `POST /v1/runs` returns 503. Configure via the Base44 secrets dashboard.

## Verification
```bash
docker compose -f docker-compose.base44.yml up -d --build
# Wait for migrate to complete, then:
curl http://localhost:3000/health/ready
# Should return {"status":"ready","configured_models":0}
```

## Tests
```bash
cd omega-x-ascension && pip install -e '.[dev]' && pytest -q
```
