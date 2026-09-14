#!/usr/bin/env bash
# Install a nightly `anima.live sleep` so Vera consolidates her memory automatically —
# distilling the day's conversation into her lasting Portrait and growing her LTC weights.
# macOS launchd: survives reboots, runs even if no Terminal is open.
#
#   bash scripts/install-nightly-sleep.sh           # Vera, 3:00 AM
#   bash scripts/install-nightly-sleep.sh Vera 4    # name, hour (0-23)
#
# Uninstall:  launchctl unload ~/Library/LaunchAgents/com.anima.sleep.plist && \
#             rm ~/Library/LaunchAgents/com.anima.sleep.plist
set -euo pipefail

NAME="${1:-Vera}"
HOUR="${2:-3}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"                                   # the python3 on your PATH now
MODEL="${ANIMA_MODEL:-hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF}"
LABEL="com.anima.sleep"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$REPO/.anima/sleep.log"

mkdir -p "$HOME/Library/LaunchAgents" "$REPO/.anima"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict><key>ANIMA_MODEL</key><string>$MODEL</string></dict>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>-m</string><string>anima.live</string>
    <string>sleep</string><string>$NAME</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✅ Installed '$LABEL'."
echo "   $NAME will sleep nightly at ${HOUR}:00 (catches up on next wake if the Mac was asleep)."
echo "   python : $PY"
echo "   model  : $MODEL"
echo "   log    : $LOG"
echo
echo "Test it right now:   launchctl start $LABEL   &&   sleep 20 && tail -n 20 \"$LOG\""
echo "Note: Ollama should be running for the Portrait distillation (the desktop app keeps it up)."
echo "Uninstall:           launchctl unload \"$PLIST\" && rm \"$PLIST\""
