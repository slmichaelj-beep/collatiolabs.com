#!/usr/bin/env bash
# Back up Vera's private vault to an encrypted, restorable bundle on an external drive.
#   ./scripts/backup-anima.sh [/Volumes/LaCie]
#
# Requires ANIMA_KEY or the macOS Keychain item "anima". The bundle carries its
# own public KDF salt, but Collatio never has the key and cannot decrypt it.

set -eu
DRIVE="${1:-/Volumes/LaCie}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ANIMA_STORE:-$ROOT/.anima}"
PY="${PYTHON:-python3}"

if [ ! -d "$SRC" ]; then
  echo "No Vera vault found at $SRC — nothing to back up."; exit 1
fi
if [ ! -d "$DRIVE" ]; then
  echo "Drive not found: $DRIVE"
  echo "Is the LaCie plugged in and mounted? Check the name with:  ls /Volumes"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST_DIR="$DRIVE/anima-backup"
DEST="$DEST_DIR/$STAMP.vera.vab"
mkdir -p "$DEST_DIR"
(cd "$ROOT" && "$PY" -m anima.vault_backup create --store "$SRC" --out "$DEST" --name "${ANIMA_NAME:-Vera}")
echo "Encrypted backup -> $DEST"
echo "Snapshots so far:"
ls -1 "$DEST_DIR" | tail -5
