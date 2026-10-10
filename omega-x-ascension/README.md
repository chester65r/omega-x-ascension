# OMEGA-X ASCENSION

Production-oriented autonomous AI platform with a modular monolith architecture. This release deliberately uses a **modular monolith**: one API/runtime deployment, PostgreSQL for durable state, Redis for coordination, LangGraph for explicit workflows, and OpenAI-compatible model endpoints for local or remote open-weight inference.

## What works
- API liveness/readiness and Prometheus metrics
- Persistent workflow runs and append-only audit events
- Capability-based model routing across configured endpoints
- CEO -> Planner -> Specialist -> Critic -> Judge graph
- Human-approval policy and API primitive for future deployment-class actions
- 16 role definitions without 16 separately deployed services
- PostgreSQL/pgvector and Redis connectivity
- Separate, network-isolated computer sandbox with bounded resources (disabled by default)
- Android Local AI chat, browser page preview, and sandbox workspace file editor

## Start
```bash
python scripts/generate_env.py
# Optional: configure an OpenAI-compatible provider; input is hidden and saved to .env only.
python scripts/configure_provider.py
docker compose up --build -d
curl http://127.0.0.1:8000/health/ready
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
All `/v1` endpoints require a signed Bearer JWT with `sub`, `tenant_id`, `scope`, `iss`, `aud`, `iat`, and `exp`. Scopes include `runs:read`, `runs:write`, and `runs:approve`. Computer tools additionally require explicit `computer:read`, `computer:write`, and/or `computer:execute` scopes. The default token does not grant computer access.

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

Computer/shell execution is disabled by default and is not a hardened public sandbox. Keep OMEGA_ENABLE_COMPUTER_EXECUTION=false for internet-facing or multi-tenant deployments.

## Deployment and first-run verification

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for provider configuration, secure environment setup, operator-token issuance, backend health checks, and Android connection guidance. Live model inference requires a real provider endpoint and key; the default configuration intentionally does not pretend to have one.


## Safe local-first setup

Generate protected local secrets rather than copying placeholder secrets:

    python scripts/generate_env.py
    python scripts/configure_provider.py
    docker compose up --build -d

The API provider setup helper hides the key while typing and writes it only to the local .env file (mode 0600). It cannot create keys for third-party accounts. A local model avoids a paid-provider API key; see docs/DEPLOYMENT.md.

The computer terminal and workspace editor use a separate Docker sandbox service, not subprocess execution inside the API container. Computer tools stay disabled by default; enable only for a trusted operator after reviewing the isolated-container limitations and issuing explicit JWT scopes.


## Computer sandbox and API setup

Use `scripts/generate_env.py` for unique owner, application, worker, JWT, Redis, and sandbox credentials. The sandbox only runs on an internal Docker network, has no external network route, and is disabled at the application policy level by default. Keep it disabled for internet-facing or untrusted multi-tenant workloads; this is not a hardened per-job VM.

For local inference on the Docker host without a paid model API, follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and use the optional Ollama profile. For a third-party model, create the key from that provider's official account dashboard and enter it with `python scripts/configure_provider.py`. The helper does not mint third-party API keys and never echoes the key.

To enable the terminal/workspace editor on a trusted deployment, set `OMEGA_ENABLE_COMPUTER_EXECUTION=true`, rebuild the stack, and issue a short-lived token with only the computer scopes actually needed plus `runs:approve` for write/execute actions.
