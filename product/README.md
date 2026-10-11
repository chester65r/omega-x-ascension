# Omega X Ascension — greenfield product foundation

This is an isolated implementation under `product/` in the selected repository. The repository already contained unrelated code and a Render configuration; this implementation does **not** use, import, modify, or deploy that material. No Render service is used.

## Implemented vertical slice

- **Backend:** FastAPI/Pydantic API, SQLAlchemy persistence, Alembic migrations, Argon2 passwords, expiring HS256 bearer tokens, server-side session revocation, HMAC-keyed DB-backed authentication throttling, dummy-hash verification for unknown accounts, privacy/security headers, pseudonymous audit events, account-scoped conversations and project workspaces, bounded project files/checkpoints/diffs, streaming NDJSON account export, password-confirmed account deletion, an OpenAI-compatible provider adapter, and usage reporting.
- **Android client:** Expo SDK 57, React Native, and TypeScript with chat, searchable conversations, a database-backed project/file editor, checkpoints/diffs, secure token storage, native transcript/data sharing, capability-gated controls, top-level navigation, loading/error/retry states, usage visibility, live backend diagnostics, English/Arabic RTL, and light/dark themes. Agent tasks, browser automation, isolated terminal execution, and general file/artifact workflows are shown as unavailable rather than simulated.
- **Data/deployment:** SQLite for local tests; PostgreSQL/`asyncpg` support, a production Dockerfile, and Railway setup notes are present. The existing user-owned Vercel Hobby Preview API uses a Neon Free test database; no new paid service or Railway resource was created.
- **APK configuration:** Expo EAS profiles explicitly request APK output. A current local release-variant test APK is available at [`artifacts/omega-x-ascension-workspace-test.apk`](artifacts/omega-x-ascension-workspace-test.apk) (67 MB). It is V2-signed with the Android debug key for testing—not production—uses package `com.omegaxascension.app`, disables Android backup, and packages only network access plus Android's internal not-exported receiver permission; external-storage, overlay, haptics, and biometric permissions were removed. The packaged JS/XML scan found no Google API-key-shaped value. It points to the earlier Preview URL and does not automatically follow this branch's deployment; workspace actions remain capability-gated on the API URL it contains. No Android device was connected for installation testing.

The app does not include a model-provider key. Provider failures return an error, not fabricated text. There is deliberately no guessed free-model default: live chat requires a server-side key and an exact model ID confirmed for the operator's provider account.

Project content is stored in the application's database—not in a host directory. Writes require an expected revision to replace existing files, paths and content are size-bounded, and checkpoints keep at most three snapshots per project. The complete limits and route contract are in [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md). The API does not execute project code. Each response style is validated by the backend and changes the system instruction sent to the selected provider. The mobile app only displays server-dependent actions when `/health/ready` advertises their corresponding capability flags. Native share uses Android's built-in share sheet and only opens after the user taps a share action. Mobile sharing requests a server-side 500,000-byte preflight cap; oversized exports are rejected before any NDJSON body is sent, while full exports remain streamed to other clients.

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
For a hosted API, set `DATABASE_URL` using the actual private database reference; never invent/copy a fake URL. See [`docs/RAILWAY_DEPLOYMENT.md`](docs/RAILWAY_DEPLOYMENT.md) and [`mobile/README.md`](mobile/README.md). Required server variables are documented in `.env.example`; all real secrets must be configured through the host's encrypted environment settings. Production startup rejects placeholder secrets, non-PostgreSQL URLs, missing provider credentials/models, and non-HTTPS provider endpoints.

Selected hosted-model free tiers, current source-backed quotas, and caveats are documented in [`docs/FREE_MODEL_OPTIONS.md`](docs/FREE_MODEL_OPTIONS.md). The user-owned Gemini key is configured only as a sensitive Vercel Preview environment variable for `feature/security-capability-completion`; the non-secret settings select `gemini-3.8-flash` and Google's OpenAI-compatible endpoint. The user confirmed that Cloud Billing is not linked and accepted Google's Free Tier data terms. No Production variable or APK provider key was added.

## Actual verification and blockers

The backend suite passed **25 tests**, with one upstream Starlette/httpx deprecation warning. Fresh SQLite migrations applied through `9a2f3c6d7e81` and `alembic check` reported no schema drift; the Neon Free test database also has the additive migrations through that revision, with five new tables, five indexes, and the file-path constraint verified. Mobile TypeScript compilation and Android Metro export passed; the exported Android JS bundle is about 1.6 MB. Tests include project ownership, path validation, revision conflicts, checkpoints/diffs, export inclusion, deletion cascades, quotas, and bounded export preflight/termination. A current local Gradle APK was built and its V2 signature, package, permissions, and key-pattern scan verified. No Android device installation test was performed. The branch's Vercel Preview is [READY](https://omega-x-ascension-test-api-git-feature-security-2821f4-chester4.vercel.app): `/health/live`, `/health/ready`, and `/openapi.json` returned HTTP 200; readiness reported the Neon database connected and project workspace capabilities enabled. Unauthenticated project and usage GET routes returned HTTP 401 as expected. Exactly one earlier authenticated live chat request returned **`GEMINI_OK`**; no new provider request was made for this branch deployment. The disposable test account was deleted previously.

This verifies local code and tests plus the Neon test schema—not production readiness, unlimited free capacity, a device-tested Android app, or the full platform. The existing user-owned Preview is a personal Vercel Hobby + Neon Free test deployment; only `feature/security-capability-completion` was deployed, and Production is unchanged. At the user's direction, the test project's Root Directory is now `product/backend` (a shared project setting affecting future branch builds). Previously built APKs still point to the earlier Preview URL and need a rebuild to use this branch's API. No Railway project/CLI/token, EAS cloud build, device installation, or remote CI run is configured in this session.

**Security release blocker:** `npm audit` still reports 15 high-severity transitive Expo/Metro advisories and no moderate findings. Current registry results still show vulnerable `braces@3.0.3` and `node-forge@1.4.0`; npm's suggested `--force` downgrade to Expo 44.0.6 was not applied. Do not deploy a production APK until patched compatible versions are available and the audit is clean or findings are formally assessed. See [`docs/EXTERNAL_FINDINGS.md`](docs/EXTERNAL_FINDINGS.md).

This is **not the complete requested platform**. Durable agent orchestration/tool execution, Git-integrated code workflows, isolated terminal, real browser/research, general file/object workflows, document/image/audio processing, configurable memory, password recovery, global quotas, production monitoring, backups, and rollback are not implemented or verified. A database-backed project editor exists but is not an isolated runtime. Local auth throttling and account export/deletion are implemented, but not verified on production PostgreSQL or an Android device. The exact feature-by-feature status is in [`docs/STATUS.md`](docs/STATUS.md) and [`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md).
