# Phase 2 Security and Durability Review

## Authentication
The API is a JWT resource server. It validates signature, algorithm allowlist, issuer, audience, expiry, issued-at time, subject, tenant ID, and scopes. It does not store passwords or issue user tokens. HS256 supports self-hosting; OIDC/JWKS is the next hardening step.

## Tenant isolation
Tenant identity comes only from a verified token. Every run and audit query includes `tenant_id`; writes reject mismatched tenant objects; cross-tenant lookup returns 404. PostgreSQL row-level security remains recommended before public multi-tenant exposure.

## Durable graph state
The graph is compiled with `AsyncPostgresSaver`. Each invocation uses the run UUID as `thread_id` and the verified tenant UUID as `checkpoint_ns`. Startup initializes checkpoint tables and enables strict MessagePack deserialization.

## Phase 1 findings corrected
- No authentication.
- Global run lookup without tenant predicates.
- No durable graph checkpoints.
- No existing-database upgrade path. The one-time migration is `deploy/migrations/002_auth_tenancy.sql`.

## Remaining risks
- `BackgroundTasks` is not a durable dispatcher. Checkpoints survive a crash, but incomplete runs are not automatically leased and resumed.
- HS256 distributes one verification secret to API instances. Prefer asymmetric OIDC/JWKS at larger scale.
- Infrastructure administrators remain privileged across tenants.
