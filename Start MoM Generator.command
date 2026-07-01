#!/bin/bash
# Double-click this to start MoM Generator. It opens the tool in your browser.
# Keep this window open while you use it; close it to stop.

cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.cache/mom-generator/venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Find a python3.
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 "$(command -v python3)"; do
  [ -x "$c" ] && { PY="$c"; break; }
done
if [ -z "$PY" ]; then
  echo "Python 3 was not found. Please run ./setup.sh first."
  echo "Press any key to close."; read -r -n 1; exit 1
fi

clear
echo "════════════════════════════════════════════════"
echo "  📝  MoM Generator is starting…"
echo "════════════════════════════════════════════════"
echo
echo "  • Your browser will open automatically in a moment."
echo "  • Keep THIS window open while you use the tool."
echo "  • To stop: just close this window."
echo
echo "  (Starting up — first launch can take a few seconds.)"
echo

# Run the server in the foreground; logs go to a file to keep this window clean.
exec "$PY" server.py >/tmp/mom_server.log 2>&1
