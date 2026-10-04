# OMEGA-X ASCENSION

Phase 1 foundation for a production-oriented autonomous AI platform. This release deliberately uses a **modular monolith**: one API/runtime deployment, PostgreSQL for durable state, Redis for coordination, LangGraph for explicit workflows, and OpenAI-compatible model endpoints for local or remote open-weight inference.

## What works
- API liveness/readiness and Prometheus metrics
- Persistent workflow runs and append-only audit events
- Capability-based model routing across configured endpoints
- CEO -> Planner -> Specialist -> Critic -> Judge graph
- Human-approval policy and API primitive for future deployment-class actions
- 16 role definitions without 16 separately deployed services
- PostgreSQL/pgvector and Redis connectivity

## Start
```bash
cp .env.example .env
# Set matching POSTGRES_PASSWORD and REDIS_PASSWORD values in .env.
docker compose up --build
curl http://localhost:8000/health/ready
```

Configure one or more OpenAI-compatible endpoints in `OMEGA_MODEL_PROVIDERS`, for example:
```json
[{"name":"local-qwen","base_url":"http://host.docker.internal:8001/v1","api_key":"local","model":"Qwen/Qwen3-8B","capabilities":["reasoning","planning","analysis","summarization"],"priority":50}]
```
No fake LLM fallback is provided. If no qualified provider is configured, workflow creation returns a clear service error.

## API
- `POST /v1/runs` with `{"goal":"...","task_type":"planning"}`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/approve` for approval-gated actions
- `GET /metrics`

## Development
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
```

See `docs/architecture-review.md`, `docs/architecture.md`, and `docs/roadmap.md`.

## Phase 2: authentication, tenant isolation, checkpoints
All `/v1` endpoints require a signed Bearer JWT with `sub`, `tenant_id`, `scope`, `iss`, `aud`, `iat`, and `exp`. Scopes are `runs:read`, `runs:write`, and `runs:approve`.

Upgrade an existing Phase 1 database before starting v0.2.0:
```bash
psql "$OMEGA_CHECKPOINT_DATABASE_URL" -f deploy/migrations/002_auth_tenancy.sql
```
Existing data is assigned to legacy tenant `00000000-0000-0000-0000-000000000001`.

The durable LangGraph key uses the run UUID as `thread_id` and verified tenant UUID as `checkpoint_ns`.

## Phase 3: PostgreSQL row-level security
Apply the Phase 3 migration with the owner role, then run the API with the restricted `omega_app` connection:

```bash
psql "postgresql://omega:OWNER_PASSWORD@localhost:5432/omega" \
  -f deploy/migrations/003_database_rls.sql
```

Change the placeholder `omega_app` password before applying the migration. Each repository transaction sets `omega.tenant_id` locally; PostgreSQL RLS enforces that value on `workflow_runs` and `audit_events`.

## Phase 4 reliability remediation
The API no longer runs schema DDL and no longer executes workflows in request-process background tasks. `migrate` provisions schema/checkpoints, `api` enqueues durable jobs, and `worker` leases them atomically.

Required before startup:
```bash
python scripts/generate_env.py
# Then configure OMEGA_MODEL_PROVIDERS with your real model endpoint.
docker compose up --build
```

Never use the example secrets outside local development.
