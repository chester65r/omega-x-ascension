# Implementation checklist

## Stage 1 — Foundation
- [x] Create an isolated greenfield product directory and avoid legacy/Render configuration.
- [x] Add FastAPI/Expo structure, environment examples, OpenAPI routes, migration infrastructure, deployment notes, and project documentation.
- [x] Run backend unit/API tests and fix the failures found.
- [x] Generate the initial Alembic migration, upgrade a fresh SQLite database, and verify model/schema parity.
- [x] Add backend/mobile CI workflow configuration; remote GitHub Actions execution remains unverified.

## Stage 2 — First vertical slice
- [x] Implement Argon2 registration/login, expiring bearer tokens, and server-side revocation of all account sessions on logout.
- [x] Implement account-scoped conversation creation/list/search/read/rename/delete, message persistence, and provider-reported token usage.
- [x] Implement the OpenAI-compatible provider adapter with safe failure handling; verify request shape using an HTTPX mock transport.
- [x] Leave `AI_MODEL` blank by default; require an operator-confirmed model whenever a provider key is configured.
- [x] Implement mobile login/register, secure token storage, responsive chat history, loading/error/retry behavior, usage display, and English/Arabic plus light/dark preferences.
- [x] Verify history survives a fresh API app instance using the same SQLite database.
- [ ] Configure a real provider key and verify an actual model response end to end.

## Stage 3 — Account and production foundation
- [x] Reject development JWT secrets, schema auto-creation, and plain-HTTP provider endpoints in production configuration.
- [x] Prepare Railway Dockerfile and migration-on-start procedure; Docker image has not been built.
- [ ] Verify PostgreSQL behavior and deploy API/PostgreSQL on Railway.
- [ ] Verify public HTTPS health/readiness, authentication, account isolation, provider response, and production persistence.

## Stage 4 — Agent orchestration
- [ ] Durable task/events, bounded runs, cancellation/retry, tool permissions, optional approvals, and outcome verification.

## Stage 5 — Coding workspace
- [ ] Project files, editor, safe diffs/checkpoints, Git workflows, and isolated command execution.

## Stage 6 — Browser/research
- [ ] Real browser service, safe navigation/SSRF handling, screenshots/extraction, citations, and prompt-injection-resistant tool policy.

## Stage 7 — Files, memory, and multimodal
- [ ] Authorized file/object delivery, documents/images/voice, user-controlled memory, export/deletion.

## Stage 8 — Android completion
- [x] Validate Expo SDK dependencies, strict TypeScript compilation, app config, and Android JS bundle.
- [x] Configure explicit EAS APK-producing preview and production-apk profiles.
- [ ] Submit an authenticated EAS build, obtain the actual APK, install and test it on Android.
- [ ] Add remaining feature screens only when their backend capabilities are implemented and tested.

## Stage 9 — Production verification
- [ ] Resolve the 15-high npm audit blocker without a forced major SDK downgrade, then rerun the audit.
- [ ] Execute CI, PostgreSQL migration/persistence, genuine provider, Railway health, and EAS build/device checks.
- [ ] Publish deployment, cost, test, and defect evidence without asserting unverified capabilities.
