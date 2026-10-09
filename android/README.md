# OMEGA-X Ascension Android app

The Android app packages the dashboard in a WebView using AndroidX WebKit's secure asset loader. The workflow dashboard includes Overview, Runs, Browser, and Agents; the app does not host the API or model by itself.

## Build a debug APK

From the repository root, with Java 17 and Android SDK platform/build-tools 34 installed:

```bash
./android/build-apk.sh
```

The installable, debug-signed APK is written to `omega-x-ascension-0.5.0-debug.apk`. You can also run the **Android APK** GitHub Actions workflow; it uploads the APK as a downloadable workflow artifact.

For Docker, build from the repository root and export the APK:

```bash
docker build --target apk --output type=local,dest=dist -f android/Dockerfile .
```

## Connect the app

1. Deploy the FastAPI service and make it reachable from the phone.
2. Open the app and save the API server URL (prefer HTTPS for public servers).
3. Paste a signed JWT with the scopes required by the features you use, then tap **Connect**.
4. The URL and dashboard preferences are stored on the device; the JWT is kept for the current WebView session.

The Android asset origin is allowed by default for cross-origin API calls. Add other trusted dashboard origins as a comma-separated `OMEGA_CORS_ORIGINS` environment variable. Do not enable computer execution on an untrusted public deployment.
