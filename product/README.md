# Omega X Ascension — greenfield product foundation

This is an isolated implementation under `product/` in the selected repository. The repository already contained unrelated code and a Render configuration; this implementation does **not** use, import, modify, or deploy that material. No Render service is used.

## Implemented vertical slice

- **Backend:** FastAPI/Pydantic API, SQLAlchemy persistence, Alembic migration, Argon2 passwords, expiring HS256 bearer tokens, server-side all-session logout/revocation, account-scoped conversations, OpenAI-compatible provider adapter, and provider-reported usage-token totals.
- **Android client:** Expo SDK 57, React Native, and TypeScript chat UI with secure token storage, conversation actions, compact-width navigation, loading/error/retry states, usage visibility, English/Arabic RTL handling, and light/dark themes.
- **Data/deployment:** SQLite for local tests; PostgreSQL/`asyncpg` support, a production Dockerfile, and Railway setup notes are present. No PostgreSQL or Railway service was created.
- **APK configuration:** Expo EAS profiles explicitly request APK output. A Metro Android bundle is verified, but it is not an installable APK.

The app never includes a model-provider key. Provider failures return an error, not fabricated text. There is deliberately no guessed free-model default: live chat requires both a server-side key and an exact model ID confirmed for the operator's provider account.

## Local development and checks

Backend (Python 3.12+):

```sh
cd product/backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
alembic upgrade head
alembic check
uvicorn omega_api.main:app --app-dir src --reload
```

Mobile (Node 24+):

```sh
cd product/mobile
npm ci
npx expo install --check
npm run typecheck
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000 npx expo start
```

`10.0.2.2` is Android Emulator host loopback; use an actual reachable HTTPS API URL for release builds and a reachable LAN address for a physical-device development session. FastAPI exposes OpenAPI at `/openapi.json` and interactive API docs at `/docs`.

For a hosted API, set `DATABASE_URL` using the actual private Railway PostgreSQL reference; never invent/copy a fake URL. See [`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md) and [`mobile/README.md`](mobile/README.md). Required server variables are documented in `.env.example`; all real secrets must be configured through the host's encrypted environment settings. Production startup rejects placeholder secrets, non-PostgreSQL URLs, missing provider credentials/models, and non-HTTPS provider endpoints.

## Actual verification and blockers

The backend suite passed **14 tests**; a fresh SQLite migration applied and `alembic check` reported no model/schema drift. Expo dependency compatibility, TypeScript, app-config resolution, and Android JavaScript bundling passed. The API was launched on localhost and returned liveness, database-connected/degraded readiness (provider not configured), and generated OpenAPI with 9 paths. These checks do not establish PostgreSQL, a real provider response, an installed Android app, or an APK.

A live AI request is blocked because no server-side `OPENAI_COMPATIBLE_API_KEY` or account-verified `AI_MODEL` is configured. A Railway token/connector is unavailable, so no hosted service or PostgreSQL database was created. `npx eas-cli whoami` reports **Not logged in**; `adb` and `ANDROID_HOME` are absent, so an EAS APK build and Android installation were not attempted. No deployment or APK URL exists.

**Security release blocker:** after a targeted `uuid@11.1.1` override, `npm audit` reports 15 high-severity transitive Expo/Metro advisories and no moderate findings. Current registry versions for `braces` and `node-forge` remained within the advisory ranges; npm's `--force` fix would downgrade Expo to 44.0.6, and that major downgrade was not applied. Do not deploy a production APK until patched dependency versions are available and the audit is clean or the findings have been formally assessed. See [`docs/EXTERNAL_FINDINGS.md`](docs/EXTERNAL_FINDINGS.md).

This is **not the complete requested platform**. Agent orchestration, tool execution, coding projects, isolated terminal, real browser/research, user file/object workflows, document/image/audio processing, configurable memory, account export/deletion/recovery, rate limits/quotas, production monitoring, backups, and rollback are not implemented. The exact feature-by-feature status is in [`docs/STATUS.md`](docs/STATUS.md) and [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md).
