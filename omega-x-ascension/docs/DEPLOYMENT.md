# Deployment readiness

## Production hosting and verification

The live dashboard and API are served together by the existing Railway service at `https://omega-api-production-e4ed.up.railway.app`. Do not create a second deployment of this FastAPI application on Vercel: it duplicates the current runtime and has been producing failed deployment checks.

The repository uses GitHub Actions for source validation and a separate `.github/workflows/production-smoke.yml` to check the live dashboard, static assets, API liveness/readiness, configured and healthy model-provider counts, version endpoint, and the Android authenticated-file-write CORS preflight. Railway continues to deploy the connected `main` branch. The live site is already available at the Railway URL above; the GitHub Actions workflow replaces Vercel's health-check role, not the API runtime.

GitHub Actions usage for this public repository does not require a separate hosting subscription. This does **not** guarantee that Railway runtime resources or hosted model inference are unlimited or cost-free; check the current account usage and provider allowance. This configuration adds no new runtime service, database, or paid integration.

This repository can be built, but live AI inference requires an actual provider endpoint and credentials. Do not commit secrets or paste them into chat.

## Optional additional hosted model providers

The API supports several optional model backends with server-side API keys. To enable one, add its key in Railway `Omega API` service Variables and keep the matching model/base URL/priority values as needed. Restart/redeploy the API so the API and embedded worker read the same configuration:

- `OMEGA_GEMINI_API_KEY` — direct Google Gemini API; default model `gemini-3.8-flash`.
- `OMEGA_OPENROUTER_API_KEY` — OpenRouter's OpenAI-compatible API; default model `google/gemini-3.8-flash`.
- `OMEGA_DEEPSEEK_API_KEY` — DeepSeek's OpenAI-compatible API; default model `deepseek-flash`.
- `OMEGA_GROQ_API_KEY` — Groq's OpenAI-compatible API; default model `qwen/qwen3.8-27b`.
- Existing optional keys: `OMEGA_OPENAI_API_KEY` and `OMEGA_HF_INFERENCE_TOKEN`.

Missing or blank keys do not create fake providers. Provider keys are never sent to Android or displayed in the dashboard. Verify live provider status with `GET /health/models`, then run an actual low-risk generation test; a passing health check alone does not prove inference works. Models and availability can change at each provider, so override the model setting when needed.

## Hosted Hugging Face model on Railway

The current cloud API is deployed on Railway. Configure the API service with `OMEGA_HF_INFERENCE_BASE_URL`, `OMEGA_HF_INFERENCE_MODEL`, `OMEGA_HF_INFERENCE_PRIORITY`, and the secret `OMEGA_HF_INFERENCE_TOKEN`. The current project configuration uses `https://router.huggingface.co/v1` and `Qwen/Qwen3-4B:featherless-ai`. Store the token only in Railway Variables, give it only the inference permission it needs, and never commit or paste it into chat.

**A healthy provider check is not proof of successful text generation.** `GET /health/models` checks provider/model-list access; `GET /health/ready` reports whether the app considers itself ready. For a real verification, run `python scripts/verify_model_provider.py` in a trusted environment configured with the same provider settings, then submit a low-risk `POST /v1/runs` task using a valid short-lived JWT and verify a `succeeded` run with non-empty output. CI uses a fixture model, so passing CI does not prove the production account can complete inference.

Hugging Face hosted inference is not unlimited free hosting. Free allowance and provider availability can change, and model calls may fail when the allowance is exhausted. Do not add a payment method or purchase credits when a zero-cost setup is required. Keep provider secrets server-side; never expose them in the Android app or browser dashboard.

## Local backend

1. Install Docker Engine and Docker Compose on a Linux host.
2. From this directory, run `python3 scripts/generate_env.py`. It creates a private `.env` file and refuses to overwrite one.
3. Edit `.env` and configure `OMEGA_MODEL_PROVIDERS` with your provider's real OpenAI-compatible API URL, API key, model ID, and supported capabilities. The default is deliberately empty; there is no fake AI fallback.
4. Start services: `docker compose up --build -d`.
5. Check: `docker compose ps`, `curl -fsS http://127.0.0.1:8000/health/live`, and `curl -fsS http://127.0.0.1:8000/health/ready`.
6. Check `docker compose logs --tail=150 api worker migrate`. Readiness should report database/Redis status and a nonzero configured model count after a real provider is configured.
7. Run `docker compose exec api python scripts/verify_model_provider.py`. This performs an actual routed chat completion and fails on an unhealthy or empty response; unlike `/health/models`, it verifies generation rather than just the provider's models endpoint.
8. Finally, create a low-risk API task and verify a successful persisted run with non-empty output. The CI fixture-model test validates application flow but is not proof that your live provider account has quota or can serve your chosen model.

## Automatic Android cloud session

The installed Android app is preconfigured to use the production Railway API origin. It automatically looks for the device refresh credential in Android Keystore, exchanges it for a short-lived access token, and refreshes that access token before expiry. The access token stays in memory; the long-lived refresh credential is encrypted with an Android Keystore key. The app UI does not ask users to enter an API URL or JWT.

A device that already completed secure enrollment reconnects automatically after each app launch. If Android secure storage has no enrolled credential or the refresh credential has expired or been revoked, cloud tasks remain disabled until an owner-authorized enrollment is completed. Do not embed `OMEGA_TOKEN_BOOTSTRAP_SECRET`, a JWT signing secret, a provider key, or a long-lived token into the APK. Do not weaken the bootstrap check to anonymous enrollment: the API is multi-tenant and anonymous enrollment would grant unauthorized access.

The browser dashboard still performs read-only public health checks against the configured endpoint, but it does not accept or persist a manually supplied JWT. Cloud agent actions require the enrolled Android device session.

## Webhook and token security

- Configure `OMEGA_GITHUB_WEBHOOK_SECRET` in Railway and the matching secret in GitHub's webhook settings before enabling issue or pull-request automation. The endpoint rejects missing or invalid signatures in every environment; it does not run webhook actions without a verified HMAC signature.
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
