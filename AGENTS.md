# OMEGA-X ASCENSION — Project Operations Guide

## Architecture
- Source backend: `omega-x-ascension/` — FastAPI API, PostgreSQL/pgvector persistence, Redis-backed durable workflow queue, LangGraph worker, static dashboard assets, and separate sandbox client.
- Android wrapper: `android/` — WebView-based dashboard, standalone browser activity, local-model mode, and APK build/signing workflows.
- The intended replacement deployment is Render, defined in the root `render.yaml`: API, PostgreSQL, Key Value, and a separate sandbox service. As of 2026-10-21 the existing Render API service's builds succeed but startup fails because the service has not received the Blueprint's database/queue environment references. Do not switch the Android API URL or remove the previous Railway endpoint until the Blueprint is synced and live inference, authenticated workflows, and sandbox checks pass. The Android dashboard still defaults to the Railway endpoint as a rollback path.
- The API and worker use separate database roles and tenant-scoped PostgreSQL row-level security. Workflow jobs use an atomic lease/claim function to support recovery after worker restarts.

## Secrets and environment configuration
- `omega-x-ascension/.env.example` is a template, not a production configuration. Generate a private local `.env` and do not commit it.
- Never store passwords, JWT signing keys, provider tokens, webhook secrets, or signing keystores in source control, APK assets, dashboard JavaScript, or chat.
- Historical commits may contain legacy local-development configuration files. Removing them from the current tree does not remove Git history. Do not reuse their values; rotate any value that was reused for a live service.
- For the Render target, provider tokens and service secrets belong in Render's service environment and must never be committed. GitHub Actions secrets are reserved for release signing and workflows. Keep the old host only as a temporary rollback until Render passes verification; do not copy production credentials between providers just to duplicate the backend.
- Model configuration is server-side. A healthy provider health check does not prove successful inference; verify a real, low-risk generation before reporting live AI as validated.

## Health and verification
- `GET /health/live` — process liveness.
- `GET /health/ready` — database/queue connectivity and whether at least one configured model provider is considered healthy.
- `GET /health/models` — provider health and capability information; not a generation test.
- `GET /version` — service and API version.
- `GET /metrics` — Prometheus metrics.
- CI runs Python tests, JavaScript syntax and dashboard checks, Docker image import, and an isolated API-to-worker integration stack with a fixture model.
- Production smoke tests check dashboard/assets, health/readiness, model-provider status, version, and Android CORS preflight.
- Use the test result for the exact commit under review. An older green run does not validate a newer commit.

## Authentication and tenant isolation
- REST workflow endpoints require a signed Bearer JWT with `sub`, `tenant_id`, `scope`, `iss`, `aud`, `iat`, and `exp` claims.
- Grant only required scopes: `runs:read`, `runs:write`, `runs:approve`, and additional `computer:read`, `computer:write`, or `computer:execute` scopes where explicitly justified.
- Use `scripts/issue_token.py` only in a trusted environment to issue short-lived operator tokens. Do not put a signing key or operator token in the Android app.
- MCP JSON-RPC calls require a verified Bearer JWT and scopes; the token, not user-supplied tool arguments, provides the tenant and actor.
- Approvals must be checked against the saved request digest and queued through the repository's atomic approval method.
- GitHub webhooks require `OMEGA_GITHUB_WEBHOOK_SECRET` to match the configured repository webhook secret. Missing or invalid signatures must be rejected.
- User-controlled content sent to Slack/Telegram must be escaped or represented as plain text.

## Browser and computer safety
- The server-side browser blocks non-public IP targets, pins validated connections, revalidates redirects, and limits response size. Preserve these guarantees in browser changes.
- The standalone Android browser disables file/content access, disallows mixed content, and does not expose a JavaScript bridge.
- The dashboard WebView contains a constrained local-app bridge and must preserve trusted-origin/main-frame checks. Its loopback local-AI mode uses localhost; do not tighten mixed-content/network policy without retesting this flow.
- Keep `OMEGA_ENABLE_COMPUTER_EXECUTION=false` on internet-facing or multi-tenant deployments. The shell/command route is intentionally disabled until proper per-job OS isolation and its tests are complete.
- Tenant workspace file operations are separately gated by server policy and token scopes. Preserve tenant-bound workspace IDs and path-traversal protections.

## Android release
- `./android/build-apk.sh` builds the debug APK and packages the current dashboard assets.
- Debug APKs are for testing. The signed release workflow requires a privately held keystore and GitHub Actions secrets; it deliberately does not fall back to the debug key.
- Emulator tests do not replace installation and sign-in testing on a physical device.
- Keep `android:allowBackup="false"` and the explicit backup exclusions.

## Local development and tests
From `omega-x-ascension/`:
```bash
python3 scripts/generate_env.py
# Configure the private .env with local database/Redis URLs and an actual model provider if testing inference.
python -m pip install -e ".[dev]"
python -m compileall -q src scripts tests
pytest -q
```
For local container testing, use `omega-x-ascension/docker-compose.yml` and its documented integration overlay; inspect `omega-x-ascension/docs/DEPLOYMENT.md` for setup and live-validation steps. The local-model profile is optional and separate from the Railway production provider.
