# Implementation checklist

## Stage 1 — Foundation
- [x] Create an isolated greenfield product directory and avoid legacy/Render configuration.
- [x] Add FastAPI/Expo structure, environment examples, OpenAPI routes, migration infrastructure, deployment notes, and project documentation.
- [x] Run backend unit/API tests and fix the failures found.
- [x] Generate the initial Alembic migration, upgrade a fresh SQLite database, and verify model/schema parity.
- [x] Add backend/mobile CI workflow configuration; remote GitHub Actions execution remains unverified.

## Stage 2 — First vertical slice
- [x] Implement Argon2 registration/login, expiring bearer tokens, and server-side revocation of all account sessions on logout.
- [x] Add HMAC-keyed DB-backed authentication limits, dummy-hash login verification, privacy/security headers, and pseudonymous audit events for logout/account deletion; local API tests pass, production PostgreSQL behavior remains unverified.
- [x] Implement account-scoped conversation creation/list/search/read/rename/delete, message persistence, title/message-content search, and provider-reported token usage.
- [x] Implement the OpenAI-compatible provider adapter with safe failure handling; verify request shape using an HTTPX mock transport.
- [x] Leave `AI_MODEL` blank by default; require an operator-confirmed model whenever a provider key is configured.
- [x] Implement mobile login/register, secure token storage, responsive chat history, loading/error/retry behavior, usage display, native transcript sharing, backend-applied response styles, and English/Arabic plus light/dark preferences.
- [x] Verify history survives a fresh API app instance using the same SQLite database.
- [x] Configure the user-owned Gemini Free Tier key only in the Vercel Preview environment; one authenticated end-to-end request returned `GEMINI_OK`, and the disposable test account/data were removed.

## Stage 3 — Account and production foundation
- [x] Reject development JWT secrets, schema auto-creation, and plain-HTTP provider endpoints in production configuration.
- [x] Prepare Railway Dockerfile and migration-on-start procedure; Docker image has not been built.
- [ ] Verify PostgreSQL behavior and deploy API/PostgreSQL on Railway.
- [x] Verify public HTTPS health/readiness and one authenticated provider response on the personal Vercel Preview only.
- [ ] Verify Production PostgreSQL persistence, account isolation, monitoring, and rollback.

## Stage 4 — Agent orchestration
- [ ] Durable task/events, bounded runs, cancellation/retry, tool permissions, optional approvals, and outcome verification.

## Stage 5 — Coding workspace
- [x] Account-scoped project records, bounded text/code files, revision-checked editor operations, retained checkpoints, unified diffs, mobile project UI, export and deletion cascades; local API tests and TypeScript/Android bundle pass.
- [ ] Git workflows, code-agent edits, command execution in a separately isolated provider, checkpoint restore, general artifact delivery, and device interaction. The API intentionally never executes project files.

## Stage 6 — Browser/research
- [ ] Real browser service, safe navigation/SSRF handling, screenshots/extraction, citations, and prompt-injection-resistant tool policy.

## Stage 7 — Files, memory, and multimodal
- [x] Add authenticated streaming NDJSON account export including projects/files/checkpoints and password-confirmed deletion with cascades; backend tests pass.
- [ ] Authorized general file/object delivery, documents/images/voice, and user-controlled long-term memory.

## Stage 8 — Android completion
- [x] Validate Expo SDK dependencies, strict TypeScript compilation, app config, and Android JS bundle.
- [x] Configure explicit EAS APK-producing preview and production-apk profiles.
- [x] Build a current local standalone test APK with the project/navigation/privacy UI and Preview URL; verify V2 signature, package, archive, permissions, disabled backup, and zero Google API-key-shaped strings. It is debug-signed, not a production release.
- [ ] Install the APK and test authenticated chat, project editing/checkpoints, export/deletion limits, navigation, and Arabic RTL on an Android device/emulator; no device journey has been run.
- [x] Surface account-scoped conversation search, rename, delete, native sharing, and capability-gated response styles; diagnostics show server-side setup guidance only when no provider is configured.
- [x] Add capability-gated mobile account data sharing and password-confirmed account deletion; TypeScript passes, but Android device testing remains open.
- [x] Add bilingual top-level navigation, working database-backed project/file editor and checkpoint diff views, usage/diagnostics sections, and honest unavailable states for agent/browser/terminal/general uploads; TypeScript and Android Metro export pass.
- [x] Verify the current test APK contains only Internet access plus an internal not-exported receiver permission, disables backup, and embeds no key-shaped Google API value.
- [x] Deploy the updated backend contract to the existing personal Vercel test Preview for `feature/security-capability-completion`; verify READY, HTTP 200 health/readiness/OpenAPI, Neon connectivity, and project workspace routes. No `main`/Production deploy or new model inference request was made.

## Stage 9 — Production verification
- [ ] Resolve the 15-high npm audit blocker without a forced major SDK downgrade. Both the configured and public npm registries still report affected latest `braces@3.0.3`/`node-forge@1.4.0`; no safe patched release was available in this check.
- [ ] Execute CI, Production PostgreSQL migration/persistence, Railway health, and EAS build/device checks; the personal Preview provider smoke test is complete.
- [ ] Publish deployment, cost, test, and defect evidence without asserting unverified capabilities.
