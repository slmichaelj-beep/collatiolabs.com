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

# Accept the file as an argument (best: drag the file after './run.sh ' so the
# shell handles spaces), otherwise ask for it.
if [ "$#" -ge 1 ]; then
  AUDIO="$1"
else
  echo "  Tip: drag an audio file from Finder into this window, then press Enter."
  echo ""
  read -r -p "  Audio file path: " AUDIO
fi

# Clean up the path: strip surrounding quotes and leading/trailing spaces, then
# un-escape the backslashes Finder adds when you drag a file (\  \: \& \~ etc.).
AUDIO="${AUDIO#"${AUDIO%%[![:space:]]*}"}"   # trim leading whitespace
AUDIO="${AUDIO%"${AUDIO##*[![:space:]]}"}"   # trim trailing whitespace
AUDIO="${AUDIO%\"}"; AUDIO="${AUDIO#\"}"; AUDIO="${AUDIO%\'}"; AUDIO="${AUDIO#\'}"
AUDIO="$(printf '%s' "$AUDIO" | sed 's/\\\(.\)/\1/g')"

if [ ! -f "$AUDIO" ]; then
  echo ""
  echo "  Still can't find that file:"
  echo "    $AUDIO"
  echo "  Easiest fix: run it like this and DRAG the file in after the space:"
  echo "    ./run.sh "
  exit 1
fi

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
