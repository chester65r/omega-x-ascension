# Deployment readiness

This repository can be built, but live AI inference requires an actual provider endpoint and credentials. Do not commit secrets or paste them into chat.

## Local backend

1. Install Docker Engine and Docker Compose on a Linux host.
2. From this directory, run `python3 scripts/generate_env.py`. It creates a private `.env` file and refuses to overwrite one.
3. Edit `.env` and configure `OMEGA_MODEL_PROVIDERS` with your provider's real OpenAI-compatible API URL, API key, model ID, and supported capabilities. The default is deliberately empty; there is no fake AI fallback.
4. Start services: `docker compose up --build -d`.
5. Check: `docker compose ps`, `curl -fsS http://127.0.0.1:8000/health/live`, and `curl -fsS http://127.0.0.1:8000/health/ready`.
6. Check `docker compose logs --tail=150 api worker migrate`. Readiness should report database/Redis status and a nonzero configured model count after a real provider is configured. Successful readiness alone does not prove inference; create a low-risk test task and verify a successful run with non-empty output.

## Connect the dashboard

The dashboard requires a reachable API base URL and a valid signed JWT. Use the repository's `scripts/issue_token.py` from inside `omega-x-ascension/` after configuring `.env`. Keep tokens private and short-lived. The default token lifetime is 60 minutes.

Use a private LAN address only on a trusted network, or a properly configured HTTPS domain for remote access. The Compose API port is bound to loopback by default. Do not expose the API directly to the public internet; put it behind a TLS reverse proxy and firewall.

## Production cautions

- Keep `OMEGA_ENABLE_COMPUTER_EXECUTION=false` on internet-facing or multi-tenant deployments. The built-in command tool is not a hardened sandbox.
- Do not expose PostgreSQL or Redis publicly.
- Protect backups, provider keys, and the `.env` file. Never commit them.
- A debug APK is for testing. A production Android release needs a privately held signing key and a release build.
- Mark deployment and live inference complete only after testing on the actual host and Android device.


## Isolated computer sandbox

The API and worker do **not** execute shell commands in their own containers. The computer tool is routed to a separate sandbox service on a Docker internal network. The sandbox has a read-only image layer, bounded CPU/RAM/processes/output, no external network route, and a shared credential kept out of command environments.

Start with `OMEGA_ENABLE_COMPUTER_EXECUTION=false`. Only after reviewing your deployment, change it to `true`, rebuild/restart the stack, and issue a short-lived operator token that explicitly includes `computer:execute`, `computer:read`, and/or `computer:write`. The interactive terminal also requires `runs:approve`. Agent workflows cannot run computer commands unless the task requests `execute_code` and the run passes the existing human approval gate.

**Security boundary:** this container sandbox is intended for a trusted single-operator deployment and development tasks. It is not a replacement for a hardened per-job VM, gVisor, or Firecracker boundary for untrusted multi-tenant public SaaS. Leave computer execution off on public-facing deployments. Workspace contents are ephemeral and clear when the sandbox container is recreated.

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
