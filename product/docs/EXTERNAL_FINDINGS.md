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
