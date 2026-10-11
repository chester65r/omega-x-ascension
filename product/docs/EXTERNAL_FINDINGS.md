# External findings consulted

Collected during implementation on 2026-10-11. These are documentation/tool-query findings, not evidence that external services are configured.

## Expo Android APK builds

- [Expo APK guide](https://docs.expo.dev/build-reference/apk/): EAS Android builds default to AAB; an installable APK can be requested in a profile with `android.buildType: "apk"`. The project uses this explicit setting.
- [Expo EAS JSON reference](https://docs.expo.dev/build/eas-json/): build profiles live under `build`, with platform-specific options under `android`/`ios`.

## Railway deployment

- [Railway FastAPI guide](https://docs.railway.com/guides/fastapi): services can deploy from a GitHub repository or Dockerfile; public networking is configured separately, and the source directory must be selected for a repository deployment.
- [Railway Infrastructure as Code](https://docs.railway.com/infrastructure-as-code): current guidance says `railway.json`/`railway.toml` Config as Code is deprecated and points to `.railway/railway.ts`; no legacy config or infrastructure apply was created.

## Model availability

- OpenRouter's live model catalog listed `google/gemma-4-26b-a4b-it:free` and `cohere/north-mini-code:free` at $0/M listed input/output at query time. The Google route returned upstream HTTP 429; the Cohere probe returned no usable text. Prices/access are not guaranteed.
- [OpenRouter API documentation](https://openrouter.ai/docs/api-reference) describes the provider-neutral API shape. A server API key remains required for an app-to-provider request.

## JavaScript dependency advisories

- [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm): braces stack-exhaustion denial of service; local npm audit flags `braces <=3.0.3`. Registry latest observed: `3.0.3`, still flagged.
- [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv): node-forge signature-verification parsing issue; local audit flags `node-forge <=1.4.0`. Registry latest observed: `1.4.0`, still flagged.
- [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq): UUID v3/v5/v6 output-buffer bounds issue; npm audit flags versions `<11.1.1`. The Xcode dependency expected `^7.0.3`; a narrow Xcode-only override to `11.1.1` removed the moderate UUID advisory and passed `require('xcode')`, TypeScript, and Android bundle checks.
- After that override, `npm audit` reported **15 high, 0 moderate**. The suggested `npm audit fix --force` path would downgrade Expo to 44.0.6; that incompatible major downgrade was deliberately not applied. The remaining findings are a security/release blocker pending patched upstream packages and re-audit.

## No-cost backend hosting: Vercel + Neon (checked 2026-10-11)

- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby): Hobby is free, with monthly quotas (including 1,000,000 function invocations and 4 active CPU-hours). Vercel says Hobby is for personal projects and restricts use to **personal, non-commercial use only**. Some exceeded limits pause until a later period; the plan is not a commercial production tier.
- [Vercel FastAPI deployment guide](https://vercel.com/docs/frameworks/backend/fastapi): official instructions for deploying FastAPI on Vercel’s Python runtime.
- [Neon pricing](https://neon.com/pricing): the Free plan currently lists up to 100 projects, 100 CU-hours per project/month, 1 GB database storage per project, up to 2 CU, and compute scaling to zero after five minutes idle. Public network transfer includes 5 GB per project. Limits and product terms can change.
- [Neon plan documentation](https://neon.com/docs/introduction/plans): additional plan and quota details.
- This task provisioned the database on Neon Free and the API project on Vercel Hobby without adding a payment method, upgrading, or activating an AI provider. The user approved disabling Vercel deployment SSO for this test project.
- Current status at 2026-10-11 05:47 +03: the newest Vercel preview is still building. An earlier preview failed at database startup because SQLAlchemy passed Neon’s `channel_binding`/`sslmode` URL options to asyncpg as unsupported keywords. Commit `0bcf46b6cc31631b11059cca5fbd654a12a3b503` removes `channel_binding` and maps `sslmode=require` to `ssl=require`, preserving mandatory TLS; local tests pass, but the fix has not yet been verified live. No APK has been built or delivered.
- **Use constraint:** before using Vercel Hobby for this app, confirm the work is strictly personal/non-commercial. If this is commercial product testing, do not continue on Hobby; select another provider whose free tier explicitly permits that use, without entering a card or provisioning billable resources.


## Personal-use confirmation and live verification

- The user confirmed on 2026-10-11 that Omega X Ascension is a personal, non-commercial test, so the Vercel Hobby restriction is satisfied for this limited test deployment.
- On 2026-10-11 05:50 +03, the latest preview from commit `0bcf46b6cc31631b11059cca5fbd654a12a3b503` passed live HTTPS checks: `/health/live` 200, `/health/ready` 200 with Neon connected, `/openapi.json` 200 with 9 paths, and an unauthenticated `/api/v1/conversations` request returned 401. Health reports the AI provider is unconfigured; no provider key or AI call was used.
- Public branch API URL: https://omega-x-ascension-test-api-git-feature-greenfie-141922-chester4.vercel.app . The local Android debug APK build was started against this URL; its final artifact and security checks remain to be recorded after completion.


## Final API and Android test build verification (2026-10-11 06:03 +03)

The API still returns `/health/live` 200 and `/health/ready` 200 with Neon connected; `model_provider_configured` remains false by design. The standalone release-variant APK was built as `artifacts/omega-x-ascension-test-release.apk`, package `com.omegaxascension.app` version `0.1.0`, SHA-256 `24957f58634b7c1e548608bfdcb461a2e0c668f54f9ca70cb041db1f4c1d5568`, size 69,589,390 bytes. `apksigner` verified v2 signing; the generated test build uses the Android debug key and is not a Play Store release. `assets/index.android.bundle` and `assets/app.config` are present, the verified HTTPS API URL is embedded, and the scan found no database URL, provider key, or JWT-like candidate. The APK was not installed on a physical device or emulator during this task. The discarded debug variant lacked a bundled JS app; the delivered artifact is the standalone release variant.
