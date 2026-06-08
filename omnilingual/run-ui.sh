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

# The model is fetched from Hugging Face on first use. Use the plain, resumable
# HTTP path (the "xet" backend can hang mid-download), and time out stalls
# instead of hanging forever so a flaky connection retries rather than wedges.
export HF_HUB_DISABLE_XET=1
export HF_HUB_DOWNLOAD_TIMEOUT=60
# To store the ~6 GB model on an external drive instead of your internal disk,
# uncomment and point this at a folder on that drive (it must stay plugged in):
# export HF_HOME="/Volumes/LaCie/hf-cache"

# Flask is the only extra dependency for the UI; install it on first run.
if ! python -c "import flask" >/dev/null 2>&1; then
  echo "Installing Flask (one time)…"
  pip install flask >/dev/null
fi

URL="http://127.0.0.1:5005"
# Open the browser a moment after the server starts.
( sleep 1.5; command -v open >/dev/null 2>&1 && open "$URL" ) &

python webui.py
