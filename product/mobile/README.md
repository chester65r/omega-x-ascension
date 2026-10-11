# Android app

This is an Expo SDK 57 / React Native / TypeScript Android client. `EXPO_PUBLIC_API_BASE_URL` selects the backend; provider, database, and JWT credentials must remain server-side. Android package ID: `com.omegaxascension.app`.

## Personal test backend

The test API is available at:

`https://omega-x-ascension-test-api-git-feature-greenfie-141922-chester4.vercel.app`

Verified over HTTPS on 2026-10-11: `/health/live` returned 200; `/health/ready` returned 200 with the database connected; `/openapi.json` returned 200; and `GET /api/v1/conversations` returned 401 without authentication. The readiness payload is degraded because no AI provider/model is configured; AI features are intentionally unavailable and no provider usage is incurred.

This is a personal, non-commercial test deployment on Vercel Hobby + Neon Free. Do not use it for sensitive data or as a production service. The backend source currently has 15 high-severity dependency advisories and lacks rate limiting; resolve those and complete a security review before any production use.

## Local development and checks

```sh
npm ci
npx expo install --check
npm run typecheck
EXPO_PUBLIC_API_BASE_URL=https://omega-x-ascension-test-api-git-feature-greenfie-141922-chester4.vercel.app npx expo start
```

For a local backend on the Android Emulator, use `http://10.0.2.2:8000`. On a physical device, use a reachable HTTPS or LAN URL. Without a configured API URL, the app displays a configuration error rather than pretending it is connected.

## Build an installable test APK locally

With Node.js, JDK 21, and an Android SDK installed, run from this directory:

```sh
export EXPO_PUBLIC_API_BASE_URL=https://omega-x-ascension-test-api-git-feature-greenfie-141922-chester4.vercel.app
export NODE_ENV=production
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease
```

The self-contained test APK is written to `android/app/build/outputs/apk/release/app-release.apk`. The generated project signs this release variant with the debug key for testing; it is not a Play Store release. The Expo EAS `preview` and `production-apk` profiles also use `android.buildType: "apk"`, but require an EAS login and configured signing credentials.
