#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATIC_SRC="$PROJECT_ROOT/omega-x-ascension/static"
ASSETS_DIR="$SCRIPT_DIR/app/src/main/assets/web"

if [[ ! -f "$STATIC_SRC/index.html" ]]; then
  echo "Dashboard source not found: $STATIC_SRC/index.html" >&2
  exit 1
fi

mkdir -p "$ASSETS_DIR"
cp "$STATIC_SRC/style.css" "$STATIC_SRC/app.js" \
   "$STATIC_SRC/icon-192.png" "$STATIC_SRC/icon-512.png" \
   "$STATIC_SRC/favicon.png" "$STATIC_SRC/apple-touch-icon.png" \
   "$ASSETS_DIR/"

python3 - "$STATIC_SRC/index.html" "$ASSETS_DIR/index.html" <<'PY'
from pathlib import Path
import re
import sys

source, destination = map(Path, sys.argv[1:])
html = source.read_text(encoding="utf-8")
html = html.replace("/static/", "")
html = re.sub(r'\s*<link\s+rel=["\']manifest["\'][^>]*>', "", html, flags=re.I)
html = re.sub(
    r'\s*<script>\s*if\s*\(\s*["\']serviceWorker["\']\s+in\s+navigator\s*\).*?</script>',
    "",
    html,
    flags=re.I | re.S,
)
destination.write_text(html, encoding="utf-8")
print(f"Prepared Android dashboard assets at {destination}")
PY

cd "$SCRIPT_DIR"
if [[ ! -x ./gradlew ]]; then
  chmod +x ./gradlew
fi
./gradlew --version >/dev/null
./gradlew assembleDebug --no-daemon --stacktrace

APK_PATH="$SCRIPT_DIR/app/build/outputs/apk/debug/app-debug.apk"
OUTPUT_PATH="$PROJECT_ROOT/omega-x-ascension-0.5.0-debug.apk"
if [[ ! -s "$APK_PATH" ]]; then
  echo "APK build completed without an APK at $APK_PATH" >&2
  exit 1
fi
cp "$APK_PATH" "$OUTPUT_PATH"
echo "APK created: $OUTPUT_PATH"
