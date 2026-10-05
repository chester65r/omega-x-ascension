# Architecture

## Boundaries
- **Domain:** run lifecycle, roles, task types, approval policy.
- **Application:** workflow and model-routing use cases.
- **Ports:** model gateway, run repository, event sink.
- **Adapters:** OpenAI-compatible HTTP, SQLAlchemy/PostgreSQL, Redis, FastAPI.

## Runtime flow
1. API validates the goal and creates a run.
2. Router filters healthy providers by required capability and ranks priority and historical quality.
3. LangGraph executes CEO, Planner, selected specialist, Critic, and Judge nodes.
4. Repository persists status, output, and audit events.
5. Risk policy interrupts deployment-class actions until explicit approval.

## Consistency
PostgreSQL is authoritative. Audit events are append-only. Redis is disposable and must not contain the only copy of business state. External model calls are bounded by timeouts and retries. Idempotency keys will be added before background execution is enabled.

## Security boundaries
Model output is untrusted data. Tool execution is not part of Phase 1. Future tools must use allowlisted schemas, scoped credentials, policy checks, and immutable audit records. API secrets are environment-injected; production should use a secret manager.
