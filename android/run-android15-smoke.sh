#!/usr/bin/env bash
set -euo pipefail

PACKAGE="com.omega.ascension.android15test"
ACTIVITY="$PACKAGE/com.omega.ascension.MainActivity"
APK="android/app/build/outputs/apk/debug/app-debug.apk"
OUT="android/app/build/ci-android15-smoke.txt"

mkdir -p "$(dirname "$OUT")"
{
  echo "OMEGA-X Android 15 launch smoke test"
  echo "Package: $PACKAGE"
  echo "UTC: $(date -u +%FT%TZ)"
  [[ -s "$APK" ]]
  adb wait-for-device
  for attempt in $(seq 1 60); do
    boot="$(adb shell getprop sys.boot_completed | tr -d '\r')"
    if [[ "$boot" == "1" ]]; then break; fi
    sleep 2
  done
  [[ "$(adb shell getprop sys.boot_completed | tr -d '\r')" == "1" ]] || {
    echo "Android emulator did not finish booting." >&2
    exit 1
  }

  adb logcat -c
  adb install -r "$APK"
  start_output="$(adb shell am start -W -n "$ACTIVITY" 2>&1)"
  printf '%s\n' "$start_output"
  grep -q 'Status: ok' <<< "$start_output"
  grep -Fq "$ACTIVITY" <<< "$start_output"

  # Allow the native activity and bundled WebView dashboard to finish startup.
  sleep 8
  pid="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
  [[ -n "$pid" ]] || {
    echo "OMEGA-X process exited after launch." >&2
    adb logcat -d -v threadtime | tail -n 400
    exit 1
  }

  activities="$(adb shell dumpsys activity activities | tr -d '\r')"
  if ! grep -Fq "$ACTIVITY" <<< "$activities"; then
    echo "MainActivity is not present in Android's active activity state." >&2
    echo "$activities" | grep -E 'ResumedActivity|topResumedActivity|mResumedActivity' || true
    adb logcat -d -v threadtime | tail -n 400
    exit 1
  fi

  logcat="$(adb logcat -d -v threadtime)"
  if grep -E 'ANR in com\.omega\.ascension\.android15test|Process: com\.omega\.ascension\.android15test,' <<< "$logcat" | grep -q .; then
    echo "Android 15 reported an app ANR or crash marker." >&2
    printf '%s\n' "$logcat" | tail -n 600
    exit 1
  fi
  echo "PASS: Android 15 installed the APK and kept MainActivity running."
} 2>&1 | tee "$OUT"
