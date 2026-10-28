# OMEGA-X web-port review — 28 October 2026

Reviewed original main: 0b7df27c905250f5714c81c9e169d8a98816de9d.

## Verified in the separate Lovable web project
- Real signed-in workspace create, save, reload, download and delete.
- Real JavaScript calculation (15 x 8 = 120), public page reading (example.com), conversation export, and two independently restored chat URLs.
- Usage page loaded without runtime errors.
- 16 automated tests passed and preview build passed.

## Web improvements implemented
- Clear private cache on account identity changes, including direct account switches.
- Download conversation text without hidden reasoning/tool payloads and download workspace files.
- Confirm discarding unsaved edits when changing/creating files, warn on page close, confirm deletion.
- Label inactive incomplete historical tool entries unfinished rather than currently working.

These changes are currently in the separate Lovable project, NOT in this repository's Android source. This document is a review, not a full code sync or Android release.

## Android status
The original Android wrapper packages the static OMEGA dashboard, not the TanStack web frontend. It requires the original reachable FastAPI API and authentication contract. This web hosting does not run the Python/Redis/Docker services.

The published upstream v0.8.6 app-release.apk is a real existing artifact. Download SHA-256 matches the release digest: 3ec566e0da86866877af1f44d694f1abcebaa27d568b8d32b659ab671972e27a. Archive integrity passed. It was NOT installed or device-tested here and does NOT include the new web changes.

## Production release recommendations / remaining work
1. Define the Android backend contract and publish the intended service before claiming mobile compatibility.
2. Build through the original Android pipeline using the owner's existing signing identity; do not silently change signing keys.
3. Test sign-in, streaming, history, files, code and notifications on a real Android device.
4. Bind notification approvals to persisted tool calls and atomically claim delivery to prevent concurrent duplicates.
5. Harden outbound URLs against DNS-resolved private addresses.
6. Make assistant persistence failures visible and complete durable browser-tool reconciliation; incomplete historic entries can remain.
7. Test real notification delivery against the owner's webhook; no notification was sent during this review.

Do not call the migration or Android release complete until these remaining steps are verified. GitHub API writes do not enable automatic two-way Lovable Git sync.
