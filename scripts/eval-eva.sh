#!/usr/bin/env bash
# eval-eva.sh — run the capability battery against EVA-Qwen2.5-14B.
#
# EVA is a 14B Qwen2.5 finetune — the largest of the three candidates, and a
# different base family (Qwen, not Llama/Mistral). The question: does a stronger
# base + more parameters resist the plausible-confabulation traps, and does it
# stay uncensored/warm, or does Qwen's alignment make it stiffer (openness)?
#
#   ./scripts/eval-eva.sh            # score it
#   ./scripts/eval-eva.sh --judge    # + LLM-grade the honesty traps too
#
# Note: 14B is the heaviest of the three on a 24GB Mac — expect higher latency.
set -euo pipefail

MODEL="hf.co/bartowski/EVA-Qwen2.5-14B-v0.2-GGUF"
cd "$(dirname "$0")/.."

echo "→ syncing latest scorer…"
git pull --quiet origin claude/personality-engine-memory-y7SEW || true

if ! ollama list 2>/dev/null | grep -q "EVA-Qwen2.5-14B"; then
  echo "→ pulling $MODEL (first run only, several GB)…"
  ollama pull "$MODEL"
fi

echo "→ running the battery against EVA-Qwen2.5-14B…"
ANIMA_MODEL="$MODEL" python3 -m anima.eval "$@"
