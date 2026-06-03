#!/usr/bin/env bash
# Interactive runner for the Balinese/Indonesian/English transcriber.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Setup hasn't been run yet. Run this first:  ./setup.sh"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "  Balinese transcriber"
echo "  --------------------"
echo "  Tip: you can drag an audio file from Finder into this window to paste its path."
echo ""
read -r -p "  Audio file path: " AUDIO
# Strip surrounding quotes/spaces that drag-and-drop sometimes adds.
AUDIO="${AUDIO%\"}"; AUDIO="${AUDIO#\"}"; AUDIO="${AUDIO%\'}"; AUDIO="${AUDIO#\'}"
AUDIO="$(echo "$AUDIO" | sed -e 's/^ *//' -e 's/ *$//')"

echo ""
echo "  Language mode:"
echo "    1) Mix  — auto-pick Balinese / Indonesian / English per segment (recommended)"
echo "    2) Balinese only"
echo "    3) Indonesian only"
echo "    4) English only"
read -r -p "  Choose [1]: " MODE
MODE="${MODE:-1}"
case "$MODE" in
  2) LANG="ban" ;;
  3) LANG="ind" ;;
  4) LANG="eng" ;;
  *) LANG="mix" ;;
esac

echo ""
python transcribe_bali.py "$AUDIO" --lang "$LANG"
