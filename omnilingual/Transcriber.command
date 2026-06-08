#!/usr/bin/env bash
# Double-click this in Finder to launch the Folder Transcriber.
# It updates itself, sets up on first run, and starts watching your Inbox folder.
# It does NOT touch your sound settings.
cd "$(dirname "$0")"

echo "  Starting the Transcriber…"

# Get the latest version (best effort; skip silently if offline).
git pull --quiet 2>/dev/null || true

# First-run setup (installs everything; only happens once).
if [ ! -d ".venv" ]; then
  echo "  First run — installing everything. This takes a few minutes…"
  if ! ./setup.sh; then
    echo "  Setup failed (see above)."
    read -r -p "  Press Enter to close." _
    exit 1
  fi
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python watch.py
