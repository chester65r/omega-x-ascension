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
