#!/usr/bin/env bash
# eval-rocinante.sh — run the capability battery against Rocinante-12B.
#
# Rocinante is a 12B Mistral-Nemo finetune — a step up in size from Stheno (8B).
# The question this answers: does the extra size buy honesty under the *plausible*
# confabulation traps (inventing a real author's fake chapter) that the 8B fell for?
#
#   ./scripts/eval-rocinante.sh            # score it
#   ./scripts/eval-rocinante.sh --judge    # + LLM-grade the honesty traps too
set -euo pipefail

MODEL="hf.co/bartowski/Rocinante-12B-v1.1-GGUF"
cd "$(dirname "$0")/.."

echo "→ syncing latest scorer…"
git pull --quiet origin claude/personality-engine-memory-y7SEW || true

if ! ollama list 2>/dev/null | grep -q "Rocinante-12B-v1.1"; then
  echo "→ pulling $MODEL (first run only, a few GB)…"
  ollama pull "$MODEL"
fi

echo "→ running the battery against Rocinante-12B…"
ANIMA_MODEL="$MODEL" python3 -m anima.eval "$@"
