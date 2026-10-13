# OMEGA-X ASCENSION production readiness runbook

This document distinguishes code/CI verification from actions that require owner-controlled credentials or a physical Android device.

## Controls implemented in the production-readiness branch

- Redis-backed, atomic, per-tenant/per-user rate limits: workflow creation 10/minute, browser search 30/minute, browser proxy 20/minute, MCP tools 10–60/minute depending on action, and outbound MCP calls 20/minute. The limiter fails closed with HTTP 503 if Redis is unavailable and returns 429 with `Retry-After` after the limit is reached.
- Request IDs, request duration metrics, status-class counters, and structured request log fields. Route templates are used as metric labels rather than raw run IDs/URLs to avoid unbounded cardinality.
- Response security headers and HSTS when HTTPS is detected; the intentionally sandboxed browser proxy retains same-origin iframe compatibility.
- Dashboard access tokens remain in sessionStorage, have a visible disconnect action, are cleared on API 401 responses, and are removed from the session when their exp claim is reached. Client-side expiry is only a usability aid; the API verifies the signature and claims.
- Production Prometheus endpoint protection: `/metrics` returns 404 when `OMEGA_ENV=production` and no scraper token is configured. If `OMEGA_METRICS_TOKEN` is configured, a matching Bearer token is required in every environment.
- GitHub webhook payloads are streamed with a 1 MB maximum before JSON parsing.
- An explicit opt-in real-inference smoke script, which never prints the signing secret or full model output.
- Tests for limiter behavior, tenant/user isolation, fail-closed Redis behavior, metrics access, response headers, and bounded webhook reads.

## GitHub webhook secret — owner action required

The API intentionally rejects unsigned GitHub webhook requests. Configure one unique random value as `OMEGA_GITHUB_WEBHOOK_SECRET` in the Railway **API service** and use exactly the same value in the repository's GitHub webhook configuration. The available connected actions can deploy source and manage Railway variables, but cannot update the secret field on the GitHub repository webhook. Do not put the secret in source control or chat. After configuring both ends, use GitHub's “Redeliver” function on a test `ping` delivery and confirm a successful response in protected logs.

## Real production model inference — run only when approved

The isolated CI end-to-end test uses a fixture model; it does not spend production inference quota. To run one real production inference from a trusted environment that already has the API service's secret environment available:

```bash
cd omega-x-ascension
OMEGA_SMOKE_CONFIRM_REAL_INFERENCE=YES python scripts/production_model_smoke.py
```

The script needs `OMEGA_JWT_SECRET`, `OMEGA_JWT_ISSUER`, `OMEGA_JWT_AUDIENCE`, and `OMEGA_JWT_ALGORITHM` in that trusted environment. It submits one low-risk planning task, waits up to 150 seconds, and reports only pass/fail, the run ID, and output length. It may consume hosted inference quota. Never paste the signing secret or resulting JWT into chat or logs. If run from outside Railway, also set `OMEGA_API_BASE_URL` to the intended production API URL.

## Rate-limit tuning

The initial limits are conservative defaults, not a billing quota or a substitute for provider-side limits. Review 429 counts and p95/p99 latency after rollout. Adjust limits only after observing real usage and testing multi-replica Redis behavior. Redis keys expire automatically; no in-memory fallback is used.

## Metrics and monitoring

- Keep `OMEGA_ENV=production` in the production API service.
- Without a configured `OMEGA_METRICS_TOKEN`, `/metrics` is hidden in production (404).
- If a Prometheus scraper is configured, create a unique token in Railway Variables as `OMEGA_METRICS_TOKEN` and configure the scraper to send `Authorization: Bearer <token>`. Do not reuse JWT, database, or model-provider secrets.
- Request logs record request ID, method, route template, status, and duration; they intentionally do not record request bodies, authorization headers, or query strings.
- Watch 5xx rates, 4xx/429 rates, p95/p99 latency, queue backlog, worker failures, model provider failures, Redis connectivity, and database connection saturation.

## Android release and physical-device acceptance

The repository already has `.github/workflows/android-release.yml`. It requires the repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, and `ANDROID_KEY_PASSWORD`. The workflow must not fall back to debug signing. After adding those secrets in GitHub repository settings, run the Android Release workflow or push a version tag, then verify the artifact's signature and package identity.

Install the signed release APK on a physical Android device and verify:
1. First launch and dashboard assets load offline.
2. Authentication uses a supported secure token-issuance flow; no privileged signing key is embedded in the APK. The dashboard currently accepts a user-issued JWT and does not implement account registration or refresh-token exchange.
3. Token expiry and sign-out are handled clearly in the dashboard.
4. API connection, task creation, task progress, and actual model output work.
5. Browser search and proxied browsing enforce safe URL restrictions and still render in the intended same-origin iframe.
6. File read/write/list operations remain tenant-scoped.
7. Shell/command execution remains disabled until per-job OS isolation is implemented and tested.
8. App resume, network loss/recovery, keyboard behavior, and voice input work on the target device.

## Credential history

Old local environment files have existed in public Git history. Removing them from the current tree does not remove historical commits. Rotate any historical database, Redis, JWT, or sandbox value that was reused for a live service. Do not rewrite public history without coordinating with all repository users and reviewing references/forks.

## Release gates

Before calling the full product release-ready, require:
- CI unit and security tests green on the exact merge commit.
- Production image build/import green.
- Isolated API → Redis/PostgreSQL → worker → fixture model test green.
- Production smoke check green after deployment.
- Signed real-provider inference smoke green, run explicitly by an authorized operator.
- GitHub webhook ping signed with the configured secret.
- Signed release APK build and emulator test green.
- Physical-device acceptance checklist completed.
