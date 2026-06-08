#!/usr/bin/env bash
# Double-click this file in Finder to launch the Transcriber.
# It updates itself, sets up on first run, silences playback into the recorder,
# starts the web app, and opens your browser — all in one step.
cd "$(dirname "$0")"

echo "  Starting the Transcriber…"

# 1. Get the latest version (best effort; skip silently if offline).
git pull --quiet 2>/dev/null || true

# 2. First-run setup (installs everything; only happens once).
if [ ! -d ".venv" ]; then
  echo "  First run — installing everything. This takes a few minutes…"
  if ! ./setup.sh; then
    echo "  Setup failed (see above)."
    read -r -p "  Press Enter to close." _
    exit 1
  fi
fi

# 3. Silence playback into the recorder by routing output to BlackHole.
#    (Install the tiny switcher if it's missing; harmless if BlackHole isn't set up.)
if ! command -v SwitchAudioSource >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
  brew install switchaudio-osx >/dev/null 2>&1 || true
fi
PREV_OUT=""
if command -v SwitchAudioSource >/dev/null 2>&1; then
  PREV_OUT="$(SwitchAudioSource -c -t output 2>/dev/null || true)"
  if SwitchAudioSource -t output -s "BlackHole 2ch" >/dev/null 2>&1; then
    echo "  Audio routed to BlackHole — you won't hear playback (that's intended)."
  else
    echo "  Note: set Sound Output to 'BlackHole 2ch' yourself if you'll record audiobooks."
  fi
fi
# Restore your normal speakers when you quit (Ctrl-C).
restore_audio() {
  [ -n "$PREV_OUT" ] && command -v SwitchAudioSource >/dev/null 2>&1 \
    && SwitchAudioSource -t output -s "$PREV_OUT" >/dev/null 2>&1 || true
}
trap restore_audio EXIT

# 4. Launch the web app (installs Flask if needed, opens the browser).
./run-ui.sh
