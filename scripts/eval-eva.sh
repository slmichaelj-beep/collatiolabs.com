#!/usr/bin/env bash
# eval-eva.sh — run the capability battery against EVA-Qwen2.5-14B.
#
# EVA is a 14B Qwen2.5 finetune — the largest of the three candidates, and a
# different base family (Qwen, not Llama/Mistral). The question: does a stronger
# base + more parameters resist the plausible-confabulation traps, and does it
# stay uncensored/warm, or does Qwen's alignment make it stiffer (openness)?
#
#   ./scripts/eval-eva.sh            run it
#   ./scripts/eval-eva.sh --judge    + LLM-grade the honesty traps too
#
# Note: 14B is the heaviest of the three on a 24GB Mac — expect higher latency.
set -euo pipefail

cd "$(dirname "$0")/.."

# drop a pasted shell comment ("# EVA-…"), keep real flags like --judge.
# plain string (not an array) so it's safe on macOS's bash 3.2 under set -u.
FLAGS=""
for a in "$@"; do case "$a" in "#"*) break ;; esac; FLAGS="$FLAGS $a"; done

echo "→ syncing latest scorer…"
git pull --quiet origin claude/personality-engine-memory-y7SEW || true

# EVA's GGUF doesn't reliably resolve through ollama's HF puller — bartowski's
# repo trips "Repository is not GGUF / sharded GGUF not supported" (ollama#8326).
# I can't pull-test from my side, so the script does: try known references in
# order and use the FIRST that actually pulls. Whichever works, wins.
CANDIDATES="
hf.co/bartowski/EVA-Qwen2.5-14B-v0.2-GGUF:Q4_K_M
hf.co/mradermacher/EVA-Qwen2.5-14B-v0.2-GGUF:Q4_K_M
hf.co/mradermacher/EVA-Qwen2.5-14B-v0.2-i1-GGUF:Q4_K_M
type32/eva-qwen-2.5-14b
"

MODEL=""
if ollama list 2>/dev/null | grep -qi "eva-qwen"; then
  MODEL="$(ollama list | awk 'tolower($1) ~ /eva-qwen/ {print $1; exit}')"
  echo "→ found already-pulled EVA: $MODEL"
else
  for c in $CANDIDATES; do
    echo "→ trying $c …"
    if ollama pull "$c"; then MODEL="$c"; break; fi
    echo "  ✗ that reference didn't pull — trying the next…"
  done
fi

if [ -z "$MODEL" ]; then
  echo ""
  echo "✗ none of the known EVA references pulled. To find one that exists:"
  echo "    https://huggingface.co/models?search=EVA-Qwen2.5-14B+GGUF"
  echo "  pick a repo, then:"
  echo "    ollama pull hf.co/<user>/<repo>:Q4_K_M"
  echo "    ANIMA_MODEL=hf.co/<user>/<repo>:Q4_K_M python3 -m anima.eval"
  exit 1
fi

echo "→ running the battery against $MODEL …"
ANIMA_MODEL="$MODEL" python3 -m anima.eval $FLAGS
