# Architecture — greenfield product slice

## Implemented topology

- **Expo Android client (`mobile/`)**: React Native/TypeScript chat, Expo SecureStore bearer token storage, persisted language/theme preferences, responsive conversation navigation, and request/loading/error states. The app receives only an API base URL and short-lived access token; provider credentials remain server-only.
- **FastAPI (`backend/`)**: JSON API with Pydantic validation, Argon2id password hashing, HS256 expiring bearer tokens, per-user token-version revocation, account-scoped database queries, an OpenAI-compatible provider adapter, and usage token totals.
- **SQLAlchemy storage**: SQLite for local development/tests and PostgreSQL through `asyncpg` for hosting. Alembic's initial revision upgrades fresh SQLite and has no schema drift against models; PostgreSQL behavior is not verified.
- **Model API**: provider base URL, secret, and model ID are configured server-side. There is deliberately no default model; the operator must select an ID confirmed for their provider account. The OpenRouter catalog listed free routes at lookup time, but probes failed (429/no usable text). Adapter tests used local HTTPX mocks only.
- **Deployment**: Railway is the documented target; the Dockerfile migrates then starts Uvicorn on its assigned `PORT`. No Railway project, PostgreSQL service, deployment, or public API URL exists.

## Request flow

1. Registration/login uses HTTPS in production. Argon2id password hashing runs off the async event loop.
2. The API issues a signed token with an expiry and the user's token version. Logout increments that version, invalidating all existing account tokens.
3. The app stores its token in Expo SecureStore and passes it to authenticated API requests.
4. Conversation/message queries scope records to the authenticated `user_id`; another user's read/rename/delete receives 404.
5. Chat sends the newest 80 persisted messages in chronological order to the explicitly configured OpenAI-compatible model provider.
6. Only successful provider output is persisted: user/assistant messages and provider-reported token counts commit together. Failures return explicit errors and save no fabricated answer.

## Security boundaries and current limitations

- Production configuration rejects sample/short JWT secrets, automatic schema creation, missing provider key/model, non-PostgreSQL URLs, and non-HTTPS provider endpoints.
- Provider failures are sanitized; prompts, bearer headers, and upstream response bodies are not logged or returned.
- SQLite foreign keys are enabled; conversation deletion removes associated messages and usage rows. PostgreSQL cascades are defined in migration metadata.
- Per-user authorization and server-side session revocation are tested. Rate limits/quotas, account recovery/export/deletion, audit logging, and row-level security are not implemented.
- The provider adapter currently uses a fixed response-token budget. Streaming/cancellation are not implemented. Usage tokens are tracked, but cost estimates are withheld because provider pricing metadata and account rates are not configured.
- No arbitrary commands run in the API. No isolated execution provider is available/configured. Browser service, agent tasks, files/object storage, multimodal features, and durable background jobs are not implemented.
- The mobile app was type-checked and Android-bundled, but not run on a device/emulator. Production security review, clean dependency audit, Railway/PostgreSQL verification, and a live provider response remain required.

## API surface

FastAPI publishes OpenAPI at `/openapi.json` and interactive docs at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database reachability and explicit provider configuration status |
| `POST /api/v1/auth/register` | Account creation and token issue |
| `POST /api/v1/auth/login` | Session issue |
| `POST /api/v1/auth/logout` | Revoke all account sessions issued before logout |
| `GET/POST /api/v1/conversations` | Search/list and create conversations |
| `GET/PATCH/DELETE /api/v1/conversations/{id}` | Read, rename, or delete owned conversation |
| `POST /api/v1/conversations/{id}/messages` | Call configured provider and persist successful output |
| `GET /api/v1/usage` | Per-account request/token totals; dollar estimate unknown |
