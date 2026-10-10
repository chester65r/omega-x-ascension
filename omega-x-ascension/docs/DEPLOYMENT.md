# Deployment readiness

This repository can be built, but live AI inference requires an actual provider endpoint and credentials. Do not commit secrets or paste them into chat.

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

## Hosted model with a free-credit allowance (optional)

The Render blueprint now supports Hugging Face Inference Providers through the OpenAI-compatible router. The default model ID is `Qwen/Qwen3-4B:featherless-ai`, which pins routing to Featherless rather than depending on automatic provider selection. A narrowly scoped Hugging Face access token must be stored as the Render secret `OMEGA_HF_INFERENCE_TOKEN`; it is never committed to GitHub or printed by the application. Only enable the "Inference Providers" permission for that token, not repository write or account-management permissions.

**This is not unlimited free hosting.** Hugging Face currently documents a small monthly free allowance for free accounts (listed as $0.10 and subject to change). If that allowance runs out, live inference may stop until the allowance refreshes or additional credits are added. Do not add a payment method or purchase credits when you require a zero-cost setup. The API reports provider health separately; it never substitutes fake model output for a failed provider.

After storing the token in Render, deploy the service and check `/health/models` for at least one healthy model and `/health/ready` for a 200 response. If no model is healthy, readiness returns 503 and workflow creation rejects the task rather than pretending it ran.

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
