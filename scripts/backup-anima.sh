#!/usr/bin/env bash
# Back up the creature — her weights, memory, and Portrait — to an external drive.
# Everything that *is* her lives in .anima/; this is her life insurance.
#   ./scripts/backup-anima.sh [/Volumes/LaCie]
#
# Makes a timestamped snapshot (keeps history, so a bad day can't overwrite a good
# backup). If ANIMA_KEY encryption is on, the backed-up files are encrypted too.

set -u
DRIVE="${1:-/Volumes/LaCie}"
SRC="$HOME/collatiolabs.com/.anima"

if [ ! -d "$SRC" ]; then
  echo "No creature found at $SRC — nothing to back up."; exit 1
fi
if [ ! -d "$DRIVE" ]; then
  echo "Drive not found: $DRIVE"
  echo "Is the LaCie plugged in and mounted? Check the name with:  ls /Volumes"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$DRIVE/anima-backup/$STAMP"
mkdir -p "$DEST"
rsync -a "$SRC/" "$DEST/"
echo "Backed up -> $DEST"
echo "Snapshots so far:"
ls -1 "$DRIVE/anima-backup" | tail -5
