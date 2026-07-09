#!/bin/bash
# Capture a product screenshot of the MoM Generator landing page for the release
# notes. Starts the app if needed, renders it with headless Chrome, and writes
#   screenshots/app-ready.png  (+ an archived screenshots/app-<version>.png)
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHOTS="$APP_DIR/screenshots"
PORT="${MOM_PORT:-8765}"
URL="http://127.0.0.1:$PORT/"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Version string from the top of RELEASE_NOTES.md (e.g. "v1.1"), else a date.
VERSION="$(grep -m1 -oE 'v[0-9]+\.[0-9]+' "$APP_DIR/RELEASE_NOTES.md" 2>/dev/null || true)"
[ -n "$VERSION" ] || VERSION="$(date +%Y%m%d)"

[ -x "$CHROME" ] || { echo "❌ Google Chrome not found at $CHROME"; exit 1; }

# Start the app if the port isn't already serving.
STARTED_PID=""
if ! curl -sf "$URL" >/dev/null 2>&1; then
  echo "▶ Starting the app on port $PORT…"
  ( cd "$APP_DIR" && MOM_PORT="$PORT" python3 server.py >/tmp/mom_capture.log 2>&1 ) &
  STARTED_PID=$!
  for _ in $(seq 1 30); do curl -sf "$URL" >/dev/null 2>&1 && break; sleep 1; done
fi

mkdir -p "$SHOTS"
echo "📸 Rendering $URL…"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=820,900 \
  --screenshot="$SHOTS/app-ready.png" "$URL"

cp "$SHOTS/app-ready.png" "$SHOTS/app-$VERSION.png"
echo "✓ Saved screenshots/app-ready.png and screenshots/app-$VERSION.png"

# Leave the app running only if it was already up before we started.
[ -n "$STARTED_PID" ] && kill "$STARTED_PID" 2>/dev/null || true
