#!/bin/bash
set -euo pipefail

# ── Build APK for OMEGA-X Ascension ──
# Copies the static dashboard into the Android assets, then builds a debug APK.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATIC_SRC="$PROJECT_ROOT/omega-x-ascension/static"
ASSETS_DIR="$SCRIPT_DIR/app/src/main/assets/web"

echo "=== Copying static dashboard to Android assets ==="
mkdir -p "$ASSETS_DIR"
cp "$STATIC_SRC/style.css" "$ASSETS_DIR/"
cp "$STATIC_SRC/app.js" "$ASSETS_DIR/"
cp "$STATIC_SRC/icon-192.png" "$ASSETS_DIR/"
cp "$STATIC_SRC/icon-512.png" "$ASSETS_DIR/"
cp "$STATIC_SRC/favicon.png" "$ASSETS_DIR/"
cp "$STATIC_SRC/apple-touch-icon.png" "$ASSETS_DIR/"

# Create a modified index.html with relative paths (no /static/ prefix, no service worker)
python3 -c "
import re
with open('$STATIC_SRC/index.html') as f:
    html = f.read()
# Fix static asset paths to relative
html = html.replace('/static/', '')
# Remove manifest link (not needed in WebView)
html = re.sub(r'<link rel=\"manifest\"[^>]*>\n?', '', html)
# Remove service worker registration
html = re.sub(r'<script>\s*if \(.serviceWorker..*?\}</script>', '', html, flags=re.DOTALL)
with open('$ASSETS_DIR/index.html', 'w') as f:
    f.write(html)
print('Created modified index.html for Android assets')
"

echo "=== Building APK ==="
cd "$SCRIPT_DIR"

# Generate Gradle wrapper if not present
if [ ! -f gradlew ]; then
    echo "Generating Gradle wrapper..."
    gradle wrapper --gradle-version 8.1
fi

# Build debug APK
./gradlew assembleDebug --no-daemon --stacktrace

APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
if [ -f "$APK_PATH" ]; then
    echo ""
    echo "=== APK BUILD SUCCESSFUL ==="
    echo "APK location: $SCRIPT_DIR/$APK_PATH"
    cp "$APK_PATH" "$PROJECT_ROOT/omega-x-ascension-0.4.0.apk"
    echo "Copied to: $PROJECT_ROOT/omega-x-ascension-0.4.0.apk"
else
    echo "ERROR: APK not found at $APK_PATH"
    exit 1
fi
