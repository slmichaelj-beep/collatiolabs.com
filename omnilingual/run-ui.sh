#!/usr/bin/env bash
# Launch the drag-and-drop web UI for the transcriber.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Setup hasn't been run yet. Run this first:  ./setup.sh"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Flask is the only extra dependency for the UI; install it on first run.
if ! python -c "import flask" >/dev/null 2>&1; then
  echo "Installing Flask (one time)…"
  pip install flask >/dev/null
fi

URL="http://127.0.0.1:5005"
# Open the browser a moment after the server starts.
( sleep 1.5; command -v open >/dev/null 2>&1 && open "$URL" ) &

python webui.py
