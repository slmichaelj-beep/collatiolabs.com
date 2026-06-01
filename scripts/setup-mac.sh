#!/usr/bin/env bash
# anima — bring it to life on an Apple Silicon Mac, in one step.
#   ./scripts/setup-mac.sh [name] [neurons]
# Idempotent and non-destructive: safe to re-run.

set -u
NAME="${1:-Vera}"
NEURONS="${2:-48}"
MODEL="qwen2.5:7b-instruct"

say() { printf "\n\033[1m• %s\033[0m\n" "$1"; }
cd "$(dirname "$0")/.." || exit 1

say "Creature deps (numpy) + Mac GPU training (mlx)"
python3 -m pip install --quiet --upgrade numpy || { echo "  numpy install failed"; exit 1; }
python3 -m pip install --quiet --upgrade mlx 2>/dev/null \
  || echo "  (mlx is Apple-Silicon only — numpy alone runs everything, just on CPU)"

say "Voice + ears (optional, recommended): Kokoro TTS, faster-whisper"
python3 -m pip install --quiet -r anima/requirements-voice.txt 2>/dev/null \
  || echo "  (voice is optional; skipped — it will fall back to browser speech)"

say "Language brain: Ollama + $MODEL"
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then brew install ollama
  else echo "  Install Ollama from https://ollama.com (or Homebrew), then re-run."; fi
fi
if command -v ollama >/dev/null 2>&1; then
  ollama list 2>/dev/null | grep -q "qwen2.5:7b" || ollama pull "$MODEL"
fi

say "Birth $NAME ($NEURONS neurons)"
python3 -m anima.live birth "$NAME" --neurons "$NEURONS" 2>/dev/null \
  || echo "  ($NAME already exists — keeping who they've become)"

say "Nightly auto-sleep at 3:00 (it consolidates each day on its own)"
python3 -m anima.nightly install --name "$NAME" --hour 3 || true

say "Ready."
echo "  Talk in the terminal:   python3 -m anima.live chat $NAME"
echo "  Phone server (private): python3 -m anima.server --name $NAME --neurons $NEURONS --voice"
echo "    then front it with Tailscale and open it in your phone's browser."
