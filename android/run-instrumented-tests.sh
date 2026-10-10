#!/usr/bin/env bash
set -uo pipefail

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ANDROID_DIR="$ROOT/android"
BUILD_DIR="$ANDROID_DIR/app/build"
mkdir -p "$BUILD_DIR"

cd "$ANDROID_DIR"
set +e
./gradlew connectedDebugAndroidTest --no-daemon --stacktrace
test_status=$?
set -e

# Capture diagnostics before the emulator action tears down the device.
adb logcat -d -v threadtime > "$BUILD_DIR/ci-logcat.txt" 2>&1 || true
adb shell dumpsys activity exit-info com.omega.ascension > "$BUILD_DIR/ci-exit-info.txt" 2>&1 || true
adb exec-out screencap -p > "$BUILD_DIR/ci-final-screen.png" 2>/dev/null || true
if [[ -d "$BUILD_DIR/reports/androidTests/connected/debug" ]]; then
  find "$BUILD_DIR/reports/androidTests/connected/debug" -type f -maxdepth 4 -print || true
fi
exit "$test_status"
