# Deployment readiness

## Current Render recovery status (checked 2026-10-22)

Render is the sole production target and is defined by the repository-root `render.yaml`. The workspace already contains the API service, PostgreSQL database, and Key Value store. The API image builds successfully, but deployments currently fail at application startup because the running service does not receive its required database, checkpoint-database, and Redis connection settings. The existing resources must be adopted/synced to the Blueprint so that its connection references and generated secrets reach the service; arbitrary placeholder URLs are not a valid fix.

The Android app and current deployment configuration use `https://omega-x-ascension-api.onrender.com` as the only backend target. Do not add fallback URLs. The service is not production-ready until its missing environment references are applied and the checks below pass.

### Required Render Blueprint setup

1. Open the [Render Dashboard](https://dashboard.render.com) and inspect the **Blueprints** section before changing anything. If a Blueprint already manages these resources, use that Blueprint. If none does, do **not** blindly create a new Blueprint from `render.yaml`: Render may append suffixes and create separate resources when a new Blueprint collides with existing services.
2. Use Render's **Generate Blueprint from existing services** flow (or its explicit add-existing-resource flow) to adopt the existing `omega-x-ascension-api`, `omega-x-ascension-db`, and `omega-x-ascension-kv` resources. Ensure the Blueprint path points to the repository-root `render.yaml` on branch `main`. If the resource preview shows duplicate API/database/Key Value resources, suffixed names, or an unexpected plan/resource replacement, cancel and correct the adoption before deploying.
3. Review the full proposed diff. The intended result is to wire the **existing** PostgreSQL database and Key Value store into the API's `OMEGA_MIGRATION_DATABASE_URL` and `OMEGA_REDIS_URL`, configure the API entrypoint to run migrations and create least-privilege database connection URLs, and add only the separate sandbox service. The sandbox must generate its own `OMEGA_SANDBOX_TOKEN`; the API references that token and the sandbox's `RENDER_EXTERNAL_HOSTNAME`. Do not make the sandbox depend on an API-generated token while the API also depends on the sandbox host, because that creates a circular Blueprint dependency. Do not delete or recreate the current database.
4. Sync the adopted Blueprint. Then manually set the model-provider secrets on the API service: `OMEGA_OPENROUTER_API_KEY`, `OMEGA_HF_INFERENCE_TOKEN`, and/or `OMEGA_GEMINI_API_KEY`. These `sync: false` secrets are not populated by later Blueprint syncs, so add them in the Render Dashboard; never commit or embed them in Android. Configure at least one valid provider.
5. Confirm a successful deploy and check `/health/live`, `/health/ready`, `/health/models`, and `/version`. Then verify a real model completion, a low-risk authenticated workflow with non-empty output, tenant-scoped file operations, and the separate sandbox health endpoint. A successful build alone is not sufficient.
6. After all checks pass, keep `DEFAULT_API_BASE` and the rewrite configuration pointed only at Render, rebuild/install the current Android APK, and verify it on the physical Android device. Retire unused hosting only after a database backup and a verified live cutover.

**Time-sensitive database note:** the existing Render free PostgreSQL resource currently reports an expiry date of **2026-11-09**. Back up any data that matters and confirm a continuation or migration plan before that date. Do not assume the database will be retained indefinitely on its current plan.

## Model provider setup

The Render Blueprint declares OpenRouter, Hugging Face Inference Providers, and optional Gemini settings. The API keys/tokens are deliberately marked `sync: false`; enter only credentials you intend to use in Render's dashboard. Model quotas and free-tier availability can change. Never store a key in GitHub source control, the Android APK, or browser JavaScript.

**A healthy provider check is not proof of successful text generation.** `GET /health/models` checks provider/model-list access; `GET /health/ready` reports whether the app considers itself ready. For real verification, run `python scripts/verify_model_provider.py` in a trusted environment configured with the same provider settings, then submit a low-risk `POST /v1/runs` task using a valid short-lived JWT and verify a `succeeded` run with non-empty output. CI uses a fixture model, so passing CI does not prove the live account can complete inference.

## Local backend

1. Install Docker Engine and Docker Compose on a Linux host.
2. From this directory, run `python3 scripts/generate_env.py`. It creates a private `.env` file and refuses to overwrite one.
3. Edit `.env` and configure `OMEGA_MODEL_PROVIDERS` with your provider's real OpenAI-compatible API URL, API key, model ID, and supported capabilities. The default is deliberately empty; there is no fake AI fallback.
4. Start services: `docker compose up --build -d`.
5. Check: `docker compose ps`, `curl -fsS http://127.0.0.1:8000/health/live`, and `curl -fsS http://127.0.0.1:8000/health/ready`.
6. Check `docker compose logs --tail=150 api worker migrate`. Readiness should report database/Redis status and a nonzero configured model count after a real provider is configured.
7. Run `docker compose exec api python scripts/verify_model_provider.py`. This performs an actual routed chat completion and fails on an unhealthy or empty response; unlike `/health/models`, it verifies generation rather than just the provider's models endpoint.
8. Finally, create a low-risk API task and verify a successful persisted run with non-empty output. The CI fixture-model test validates application flow but is not proof that your live provider account has quota or can serve your chosen model.

## Connect the dashboard

The dashboard requires a reachable API base URL and a valid signed JWT. Use the repository's `scripts/issue_token.py` from inside `omega-x-ascension/` after configuring `.env`. Keep tokens private and short-lived. The default token lifetime is 60 minutes.

Use a private LAN address only on a trusted network, or a properly configured HTTPS domain for remote access. The Compose API port is bound to loopback by default. Do not expose the API directly to the public internet; put it behind a TLS reverse proxy and firewall.

## Webhook and token security

- Configure `OMEGA_GITHUB_WEBHOOK_SECRET` in the Render API service and the matching secret in GitHub's webhook settings before enabling issue or pull-request automation. The endpoint rejects missing or invalid signatures in every environment; it does not run webhook actions without a verified HMAC signature.
- MCP JSON-RPC calls to `POST /mcp` and `POST /v1/mcp` require a signed Bearer JWT. Grant only the needed scopes: `runs:read`, `runs:write`, and `runs:approve`. Use short-lived operator tokens and never place them in the Android APK, client-side JavaScript, or source control.
- Rotate any old credential that may have appeared in historical committed environment files. Removing an environment file from the latest tree does not erase its older Git history.

## Production cautions

- Keep `OMEGA_ENABLE_COMPUTER_EXECUTION=false` on internet-facing or multi-tenant deployments. The built-in command tool is not a hardened per-job sandbox.
- `OMEGA_ENABLE_COMPUTER_FILES=true` enables the authenticated file editor independently; the terminal remains off unless explicitly enabled.
- Do not expose PostgreSQL or Redis publicly.
- Protect backups, provider keys, and the `.env` file. Never commit them.
- A debug APK is for testing. A production Android release needs a privately held signing key and a release build.
- Mark deployment and live inference complete only after testing on the actual host and Android device.


## Isolated computer sandbox

The API and worker do **not** execute shell commands in their own containers. The computer tool is routed to a separate sandbox service on a Docker internal network. The sandbox has a read-only image layer, bounded CPU/RAM/processes/output, no external network route, and a shared credential kept out of command environments.

Set `OMEGA_ENABLE_COMPUTER_FILES=true` to enable file listing, reading and writing independently of command execution. File operations still require the corresponding tenant-bound JWT scopes. Keep `OMEGA_ENABLE_COMPUTER_EXECUTION=false` unless commands are required for a trusted test environment. If enabled, issue a short-lived operator token that explicitly includes `computer:execute` and `runs:approve`; agent workflows cannot run computer commands unless the task requests `execute_code` and the run passes the existing human approval gate.

**Security boundary:** the sandbox is a separate resource-limited container on a private Docker network, but shell processes in it share the same OS identity. Therefore workspace file permissions do not fully isolate one tenant from another when arbitrary shell execution is on. It is suitable for local development and trusted single-operator testing, not untrusted multi-tenant public SaaS. A hardened per-job container/VM or equivalent runtime isolation is required before enabling arbitrary command execution for untrusted users. Workspace contents are ephemeral and clear when the sandbox container is recreated.

## Local model without a paid API

For a local Ollama service on the same Docker host, start the optional profile:

```bash
docker compose --profile local-model up --build -d
docker compose exec ollama ollama pull qwen2.5:0.5b
python scripts/configure_provider.py --name local-ollama --base-url http://ollama:11434/v1 --model qwen2.5:0.5b
docker compose up --build -d api worker
```

The first model download needs storage and CPU/RAM. A Termux model running on the phone powers the Android **Local AI** chat tab only; it does not host PostgreSQL, Redis, the workflow API, or a remotely reachable backend.

## Provider key setup

Run `python scripts/configure_provider.py` inside the backend project. It prompts for the provider endpoint, model ID, capabilities and API key without echoing the key, then writes only to `.env` with restrictive permissions. External endpoints should use HTTPS. This tool cannot create credentials for a third-party account; obtain an API key from that provider's official dashboard. Never commit `.env`.


## Browser and workflow smoke tests

Browser search and page preview require a connected backend with a signed JWT carrying `runs:read`. Each navigation is fetched through the browser proxy, which validates every redirect destination and bounds response size; click navigation in the page preview is sent back to the proxy rather than allowed to bypass its checks. The mobile Personal Assistant submits a real workflow and displays its persisted status/output. It deliberately shows a setup/error state when no model can serve the selected capability instead of returning placeholder text. The `GET /health/models` endpoint reports configured model health separately from database/queue readiness, without exposing provider URLs or API keys. `GET /v1/events` returns only audit records for the authenticated tenant and requires `runs:read`.


The standalone native Android browser is for user-directed browsing only and does not expose the app's native message bridge to websites it visits. Agent research continues to use the authenticated server-side browser proxy and requires a running OMEGA API.


## Signed Android release

The routine Android workflow builds and tests a **debug-signed** APK for development. A separately gated `Android Release` workflow builds `assembleRelease`, verifies the signing block and package identity, then runs the release variant's UI smoke test on an Android 14 emulator.

Before using **Actions → Android Release → Run workflow** or pushing a `v*` tag, add these repository Actions secrets under **Settings → Secrets and variables → Actions**:

- `ANDROID_KEYSTORE_BASE64`: the base64-encoded contents of your private JKS/PKCS12 keystore (one line).
- `ANDROID_KEYSTORE_PASSWORD`: keystore password.
- `ANDROID_KEY_ALIAS`: the release key alias.
- `ANDROID_KEY_PASSWORD`: key password.

Never commit the keystore or these values. The workflow deliberately fails closed when a secret is missing, never falls back to the debug key for a release, and does not print signing material. The signing identity must be backed up securely: replacing it later prevents in-place updates of the installed application. An emulator test cannot replace a final installation check on the target physical device.
