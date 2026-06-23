#!/usr/bin/env bash
# Restore Vera's private local state and generated evidence from the 2026-06-23 LBackup package.
# Run this from ~/Developer/collatiolabs.com on the new Mac after cloning the repo.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP="${1:-$HOME/Desktop/LBackup/2026-06-23-vera-new-mac-handoff}"

cd "$REPO"

if [ ! -d "$BACKUP" ]; then
  echo "Backup folder not found: $BACKUP" >&2
  echo "Pass the backup path explicitly:" >&2
  echo "  bash scripts/restore_new_mac_from_lbackup.sh /path/to/2026-06-23-vera-new-mac-handoff" >&2
  exit 1
fi

echo "Restoring from: $BACKUP"

if [ -d "$BACKUP/anima-private-state" ]; then
  mkdir -p .anima
  rsync -a --delete "$BACKUP/anima-private-state/" ".anima/"
  echo "Restored private .anima state."
else
  echo "No anima-private-state folder found; skipping .anima restore."
fi

if [ -d "$BACKUP/reports" ]; then
  mkdir -p reports
  rsync -a --delete "$BACKUP/reports/" "reports/"
  echo "Restored generated reports."
else
  echo "No reports folder found; skipping reports restore."
fi

if [ -f "$BACKUP/verified_venv_freeze_2026_06_23.txt" ]; then
  echo "Verified source-machine package freeze is available at:"
  echo "  $BACKUP/verified_venv_freeze_2026_06_23.txt"
fi

echo
echo "Next:"
echo "  python3.12 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  python -m pip install --upgrade pip setuptools wheel"
echo "  python -m pip install -r requirements.txt"
echo "  python -m pip install cryptography requests openpyxl pdfplumber pypdf pillow playwright rich pyyaml httpx"
echo "  python -m playwright install chromium"
echo "  python -m anima.server --name Vera --port 8765"
