#!/usr/bin/env bash
# Launches the local transcription tool: starts a tiny web server in this
# folder and opens it in your default browser. Press Ctrl+C to stop.
set -euo pipefail

# Work from the folder this script lives in (so it serves index.html + worker.js).
cd "$(dirname "$0")"

# Find Python.
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed. Options:"
  echo "  • Install it from https://www.python.org/downloads/  then re-run this script"
  echo "  • Or, if you have Node.js:   npx serve -l 8000   then open http://localhost:8000/"
  exit 1
fi

# Pick the first free port starting at 8000.
PORT=8000
while command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" >/dev/null 2>&1; do
  PORT=$((PORT + 1))
done
URL="http://localhost:$PORT/"

echo ""
echo "  Audio Transcription tool"
echo "  ------------------------"
echo "  Opening:  $URL"
echo "  Stop:     press Ctrl+C in this window"
echo ""

# Open the browser shortly after the server comes up.
(
  sleep 1.5
  if command -v open >/dev/null 2>&1; then open "$URL"            # macOS
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"  # Linux
  elif command -v start >/dev/null 2>&1; then start "" "$URL"     # Git Bash on Windows
  else echo "  (Couldn't auto-open a browser — just go to $URL manually.)"
  fi
) &

# Replace this shell with the server so Ctrl+C stops it cleanly.
exec "$PY" -m http.server "$PORT"
