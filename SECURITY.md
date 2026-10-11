# Security Deployment Checklist

This project includes security controls, but a passing CI run is not a substitute for a deployment threat model or independent security review.

## Controls currently present

- Browser requests validate every resolved address, reject non-public DNS answers, pin the outbound request to a validated IP, preserve the original host/TLS name, and revalidate redirects.
- Browser responses are size-limited, and dashboard browser content is placed in a sandboxed iframe without same-origin privileges.
- Android automatic backup is disabled, with explicit backup/device-transfer exclusions for modern and legacy Android backup rules.
- Computer command execution now fails closed at the sandbox service with HTTP 503. Directory-per-tenant workspaces share one Unix identity, so shell commands are blocked until a per-tenant OS isolation runtime exists. The sandbox container is also configured with a read-only root filesystem, restricted capabilities, resource limits, and an internal-only network.
- API execution routes require explicit scopes and approval; the command environment is intentionally constructed without application secrets.

## Required deployment safeguards

1. Keep `OMEGA_ENABLE_COMPUTER_EXECUTION=false`. The current sandbox runtime rejects command execution even if that API feature flag is accidentally enabled; do not remove that guard until per-tenant OS isolation is implemented, adversarially tested, and reviewed.
2. Do not treat workspace-directory separation as a strong tenant security boundary. Commands previously shared one Unix identity and could potentially inspect sibling workspace directories; the unsafe shared-identity execution path has been disabled. Restore command capability only through an isolated per-job/per-tenant OS boundary (for example, disposable containers or microVMs with distinct identities, filesystem mounts, and denied network egress), then add adversarial cross-tenant tests.
3. Keep the sandbox on its internal-only network. Never mount the Docker socket, host paths containing secrets, cloud credentials, or production configuration into the sandbox.
4. Use a secret manager or protected deployment environment for database credentials, JWT signing secrets, model-provider API keys, webhook secrets, and the sandbox token. Do not commit real `.env` files. Generate strong unique values and rotate them after any suspected exposure.
5. Expose the API through a TLS-terminating reverse proxy with authentication/rate limiting appropriate to the deployment. The Compose file binds the API to loopback; do not change it to a public bind without an explicit network and access-control plan.
6. Set `OMEGA_CORS_ORIGINS` to only the exact required origins. CORS is not authentication.
7. Use pinned/approved container image versions and an update process; avoid floating tags for production deployments.
8. Treat the CI-produced Android APK as a **debug build**, not a production release. A production release requires a managed private signing key, protected signing credentials, release-mode validation, and a release/install test on supported Android versions.
9. Validate backups, restore procedures, database least-privilege grants, monitoring, and incident response before handling production data.

## Validation status

CI and emulator workflows validate a subset of functionality and security contracts. They do not establish that the system is penetration-tested, that all deployment configurations are secure, or that multi-tenant command execution is isolated. Re-run the repository workflows against the exact commit intended for release and review every failure before deploying.
