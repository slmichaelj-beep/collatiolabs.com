#!/usr/bin/env bash
# Interactive runner for the Omnilingual ASR (Balinese) transcriber.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Setup hasn't been run yet. Run this first:  ./setup.sh"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "  Omnilingual ASR — Balinese transcriber"
echo "  --------------------------------------"

if [ "$#" -ge 1 ]; then
  AUDIO="$1"
else
  echo "  Tip: drag an audio file from Finder into this window, then press Enter."
  echo ""
  read -r -p "  Audio file path: " AUDIO
fi

# Clean the path: trim, strip quotes, un-escape Finder drag backslashes.
AUDIO="${AUDIO#"${AUDIO%%[![:space:]]*}"}"
AUDIO="${AUDIO%"${AUDIO##*[![:space:]]}"}"
AUDIO="${AUDIO%\"}"; AUDIO="${AUDIO#\"}"; AUDIO="${AUDIO%\'}"; AUDIO="${AUDIO#\'}"
AUDIO="$(printf '%s' "$AUDIO" | sed 's/\\\(.\)/\1/g')"

if [ ! -f "$AUDIO" ]; then
  echo ""
  echo "  Can't find that file:"
  echo "    $AUDIO"
  echo "  Easiest fix: run './run.sh ' and DRAG the file in after the space."
  exit 1
fi

echo ""
echo "  Language:"
echo "    1) Balinese   (ban_Latn)  [default]"
echo "    2) Indonesian (ind_Latn)"
echo "    3) English    (eng_Latn)"
read -r -p "  Choose [1]: " MODE
case "${MODE:-1}" in
  2) LANG="ind_Latn" ;;
  3) LANG="eng_Latn" ;;
  *) LANG="ban_Latn" ;;
esac

echo ""
python transcribe_omni.py "$AUDIO" --lang "$LANG"
