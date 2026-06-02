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

# pin the quant: this repo also ships deprecated Q4_0_4_8 ARM quants that newer
# llama.cpp rejects, so ollama's default auto-pick fails ("not compatible with
# llama.cpp"). Q4_K_M is the standard, always-present, compatible choice (~9 GB).
MODEL="hf.co/bartowski/EVA-Qwen2.5-14B-v0.2-GGUF:Q4_K_M"
cd "$(dirname "$0")/.."

# drop any pasted shell comment ("# EVA-…") — interactive zsh forwards it as an arg
args=(); for a in "$@"; do [[ "$a" == \#* ]] && break; args+=("$a"); done

echo "→ syncing latest scorer…"
git pull --quiet origin claude/personality-engine-memory-y7SEW || true

if ! ollama list 2>/dev/null | grep -q "EVA-Qwen2.5-14B"; then
  echo "→ pulling $MODEL (first run only, ~9 GB)…"
  ollama pull "$MODEL"
fi

echo "→ running the battery against EVA-Qwen2.5-14B…"
ANIMA_MODEL="$MODEL" python3 -m anima.eval "${args[@]}"
