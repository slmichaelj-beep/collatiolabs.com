#!/usr/bin/env bash
# Record audio that is playing on this Mac (captured from a virtual audio input
# such as BlackHole) and transcribe it to text.
#
# Intended for personal accessibility use: reading content you own and can
# legally play but cannot hear. It records normal playback output — it does NOT
# decrypt or break any protected file.
#
# One-time setup:
#   1. brew install blackhole-2ch
#   2. System Settings > Sound > Output  ->  "BlackHole 2ch"
#   3. Play your audiobook in the Audible app, output going to BlackHole.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Setup hasn't been run yet. Run this first:  ./setup.sh"
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is missing.  Install it with:  brew install ffmpeg"
  exit 1
fi

echo ""
echo "  Record & Transcribe"
echo "  -------------------"
echo "  Audio input devices on this Mac:"
echo ""
# avfoundation prints the device list to stderr; show the audio section.
ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 \
  | sed -n '/AVFoundation audio devices/,$p' || true
echo ""
echo "  Find 'BlackHole 2ch' above and note its [index] number."
read -r -p "  Audio device index to record from: " DEV
[ -z "${DEV:-}" ] && { echo "No device chosen."; exit 1; }

DEFAULT_OUT="$HOME/Transcripts/recording_$(date +%Y%m%d_%H%M%S).wav"
mkdir -p "$HOME/Transcripts"
read -r -p "  Save recording to [$DEFAULT_OUT]: " OUT
OUT="${OUT:-$DEFAULT_OUT}"

echo ""
echo "  Language:  1) English [default]   2) Indonesian   3) Balinese"
read -r -p "  Choose [1]: " L
case "${L:-1}" in 2) LANG="ind_Latn";; 3) LANG="ban_Latn";; *) LANG="eng_Latn";; esac

echo ""
echo "  >>> Start playback in the Audible app NOW, then come back here. <<<"
echo "  Recording will capture everything until you stop it."
echo "  To STOP: press  q  then Enter (or Ctrl-C)."
echo ""
read -r -p "  Press Enter to begin recording… " _

# Record mono 16 kHz (what the transcriber wants). ':DEV' = no video, audio only.
ffmpeg -hide_banner -f avfoundation -i ":${DEV}" -ac 1 -ar 16000 "$OUT" || true

if [ ! -s "$OUT" ]; then
  echo "  No audio was recorded. Check that output is set to BlackHole and the index was right."
  exit 1
fi

echo ""
echo "  Recorded:  $OUT"
echo "  Transcribing…"
python transcribe_omni.py "$OUT" --lang "$LANG"
