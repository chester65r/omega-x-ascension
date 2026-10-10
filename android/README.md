# OMEGA-X Ascension Android app

The Android app packages the dashboard in a WebView using AndroidX WebKit's secure asset loader. The dashboard includes Overview, Personal Assistant, Runs, Browser, Local AI, Workspace, Logs, About, an isolated computer terminal, and a sandbox workspace file editor; the app does not host the API or model by itself.

## Build a debug APK

From the repository root, with Java 17 and Android SDK platform/build-tools 34 installed:

```bash
./android/build-apk.sh
```

The installable, debug-signed APK is written to `omega-x-ascension-0.7.0-debug.apk`. The CI workflow builds it and validates the signing block and package ID before publishing a temporary workflow artifact. It is a debug build, not a Play Store release.

For Docker, build from the repository root and export the APK:

```bash
docker build --target apk --output type=local,dest=dist -f android/Dockerfile .
```

## Run local AI chat without a cloud account

See [LOCAL_AI_ANDROID.md](LOCAL_AI_ANDROID.md) for the on-device Termux + llama.cpp setup. This provides local chat only; workflow automation still requires the OMEGA API backend.

## Connect the app

1. Deploy the FastAPI service and make it reachable from the phone.
2. Open the app and save the API server URL (prefer HTTPS for public servers).
3. Paste a signed JWT with the scopes required by the features you use, then tap **Connect**.
4. The URL and dashboard preferences are stored on the device; the JWT is kept for the current WebView session.

The Android asset origin is allowed by default for cross-origin API calls. Add other trusted dashboard origins as a comma-separated `OMEGA_CORS_ORIGINS` environment variable. Do not enable computer execution on an untrusted public deployment.


## Automated Android smoke test

The Android APK workflow starts an API 34 emulator and runs an instrumentation test that opens the bundled WebView dashboard, checks critical screens, verifies tab-to-section consistency, and exercises Home-to-About, Assistant, and Browser tab navigation. The test uses the bundled UI and does not require a live API server or provider key; browser network requests and real agent inference are covered separately by mocked backend tests and still require a deployed, configured backend for an end-to-end live test.
