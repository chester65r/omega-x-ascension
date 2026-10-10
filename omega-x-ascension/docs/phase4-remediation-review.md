# Phase 4 Remediation Review

This increment fixes the blocking production defects found after Phase 3.

## Corrected
- Removed runtime `create_all()` and checkpoint schema setup from API startup.
- Added a real Alembic migration environment and a one-shot migration service.
- Removed committed runtime passwords. Migration provisioning requires non-default external secrets.
- Split owner migration credentials from restricted API credentials.
- Replaced in-process FastAPI background execution with a PostgreSQL durable job table.
- Added atomic `FOR UPDATE SKIP LOCKED` leasing through a locked-down `SECURITY DEFINER` function.
- Added expired-lease recovery, bounded retries, exponential retry delay, and dead-letter state.
- Connected human approval to requested sensitive actions and bound approval to a SHA-256 digest of the immutable request.
- Stopped exposing raw exception messages in run records.
- Removed the unused `api_secret` setting.
- Unified backend package and API version at 0.6.0 for the current dashboard/sandbox integration.

- Added a separate network-isolated computer sandbox service; direct computer features remain disabled unless explicitly enabled and scoped.
- Local provider configuration is written to a mode-0600 .env file by scripts/configure_provider.py; the repository does not contain provider credentials.

## Deliberate limits
- The worker currently processes one job at a time per process. Scale by adding worker replicas after integration tests establish model-server capacity.
- HS256 remains available for local self-hosting. Public deployments should use OIDC/JWKS.
- Checkpoint tables remain on the owner connection because the external package manages its own schema. Production should move them into a separate database credential boundary.
- A live Docker/PostgreSQL integration remains an external deployment test; CI validates the Docker image import and Compose topology, but cannot prove behavior on the user's own host.
