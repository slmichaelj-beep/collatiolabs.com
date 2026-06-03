#!/usr/bin/env bash
# One-time setup for the local Balinese/Indonesian/English transcriber.
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "  Balinese transcriber — setup"
echo "  ----------------------------"

# 1. Python check
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed. Get it from https://www.python.org/downloads/ then re-run."
  exit 1
fi
echo "  Python: $($PY --version)"

# 2. ffmpeg check (needed to read .m4a and most audio)
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "  ffmpeg is missing — it's needed to read audio files."
  if command -v brew >/dev/null 2>&1; then
    echo "  Installing it with Homebrew…"
    brew install ffmpeg
  else
    echo "  Homebrew isn't installed. Please install it first:"
    echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo "  then run:  brew install ffmpeg"
    echo "  …and re-run this setup."
    exit 1
  fi
else
  echo "  ffmpeg: found"
fi

# 3. Virtual environment + dependencies
echo "  Creating virtual environment (.venv) and installing packages…"
echo "  (This downloads PyTorch — a few hundred MB. One time only.)"
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo ""
echo "  Done. To transcribe a file, run:"
echo "      ./run.sh"
echo ""
