# Android app

This is an Expo SDK 57 / React Native / TypeScript Android client. `EXPO_PUBLIC_API_BASE_URL` sets the backend URL; provider credentials never enter the mobile bundle. Android package ID: `com.omegaxascension.app`.

## Local development and checks

```sh
npm ci
npx expo install --check
npm run typecheck
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000 npx expo start
```

`10.0.2.2` is Android Emulator host-loopback. On a physical device, use a backend reachable over the LAN or HTTPS. Without a configured API URL, the app displays a configuration error instead of pretending a backend is connected.

## APK profile

The `preview` and `production-apk` EAS profiles set `android.buildType` to `apk`, following [Expo's APK guide](https://docs.expo.dev/build-reference/apk/). Expo EAS CLI reported `Not logged in`; no Android SDK/ADB is installed here. Therefore no EAS build was submitted and there is no APK artifact. Once the account, build credentials/quota, a verified HTTPS backend URL, and security-review blocker are addressed, run:

```sh
npx eas-cli build --platform android --profile preview
```

The verified Android JavaScript bundle is **not** an installable APK. Do not distribute it as one.
