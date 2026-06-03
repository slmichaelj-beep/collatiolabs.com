#!/usr/bin/env bash
# One-time setup for the Omnilingual ASR (Balinese) transcriber.
# Uses its OWN virtual environment, because Omnilingual's fairseq2 backend must
# match a specific PyTorch version and must not collide with ../balinese/.venv.
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "  Omnilingual ASR (Balinese) — setup"
echo "  ----------------------------------"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed. Get it from https://www.python.org/downloads/ then re-run."
  exit 1
fi
echo "  Python: $($PY --version)"

# System libraries: libsndfile (audio I/O) and ffmpeg (decode/split).
for pkg in libsndfile ffmpeg; do
  bin="$pkg"; [ "$pkg" = "libsndfile" ] && bin="sndfile-info"
  if ! command -v "$bin" >/dev/null 2>&1 && ! ls /opt/homebrew/lib/lib${pkg}* /usr/local/lib/lib${pkg}* >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      echo "  Installing $pkg via Homebrew…"
      brew install "$pkg"
    else
      echo "  Homebrew isn't installed. Install it first:"
      echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
      echo "  then run:  brew install libsndfile ffmpeg   and re-run this setup."
      exit 1
    fi
  fi
done

echo "  Creating virtual environment (.venv) and installing omnilingual-asr…"
echo "  (This pulls PyTorch + fairseq2 — a sizable download. One time only.)"
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install omnilingual-asr

echo ""
echo "  Quick check that Balinese is available:"
python - <<'PY' || echo "  (Couldn't verify now — it will be checked at runtime.)"
from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs
print("    ban_Latn supported:", "ban_Latn" in supported_langs, "| total langs:", len(supported_langs))
PY

echo ""
echo "  Done. To transcribe, run:"
echo "      ./run.sh"
echo ""
echo "  Note: if you hit a fairseq2 segfault/crash, it usually means the"
echo "  fairseq2 build doesn't match the installed torch. Tell me the error."
echo ""
