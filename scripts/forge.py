#!/usr/bin/env python3
"""
Character Forge wizard — give her a lasting voice from a corpus, safely.

Stage 1 (any machine):   build the LoRA dataset from your sources.
Stage 2 (Mac, MLX):      train the adapter.
Stage 3 (Mac, model):    eval-gate it — accept only if honesty held and persona improved.

  # 1. drop in anything that embodies the voice you want (files, URLs, YouTube)
  python3 scripts/forge.py build notes.md https://example.com/essay "https://youtu.be/VIDEOID"

  # 2. train on the Mac (needs: pip install mlx-lm ; the model in MLX format)
  MODEL=mlx-community/L3-8B-Stheno-v3.2-4bit python3 scripts/forge.py train

  # 3. gate it (runs the eval before/after; accepts only if it passes)
  MODEL=… python3 scripts/forge.py gate

Honest: stage 1 needs no model. Stages 2–3 need MLX + the model on the Mac. The
forge shifts VOICE, not knowledge and not intelligence — and never honesty (gated).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from anima import forge                                                  # noqa: E402

NAME = os.environ.get("ANIMA_NAME", "vera")
WORK = os.path.join(".anima", "forge", NAME)
DATA = os.path.join(WORK, "data")
ADAPTER = os.path.join(WORK, "adapter")


def cmd_build(sources):
    if not sources:
        sys.exit("Give me sources: files, URLs, or YouTube links.")
    print(f"Ingesting {len(sources)} source(s)…")
    got, docs = [], []
    for src, kind, text in forge.ingest(sources):
        if text:
            docs.append(text)
            got.append(f"  ✓ {kind:7} {src}  ({len(text.split())} words)")
        else:
            got.append(f"  ✗ {kind:7} {src}  (couldn't read — skipped)")
    print("\n".join(got))
    if not docs:
        sys.exit("Nothing readable to train on.")
    n_train, n_valid = forge.build_dataset(docs, DATA)
    print(f"\nDataset: {n_train} train / {n_valid} valid chunks  →  {DATA}")
    if n_train < 40:
        print("  ⚠ small corpus — voice shift will be subtle. More material = stronger,\n"
              "    but keep it BALANCED; one narrow source overfits and degrades her.")
    print("\nNext:  MODEL=<mlx model> python3 scripts/forge.py train")


def cmd_train():
    model = os.environ.get("MODEL")
    if not model:
        sys.exit("Set MODEL=<mlx model id> (your model in MLX format).")
    if not os.path.exists(os.path.join(DATA, "train.jsonl")):
        sys.exit("No dataset — run `forge.py build …` first.")
    iters = int(os.environ.get("FORGE_ITERS", "300"))
    cmd = forge.train_command(model, DATA, ADAPTER, iters=iters)
    print("Training:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        sys.exit("mlx_lm not found. Run: pip install mlx-lm")
    print(f"\nAdapter → {ADAPTER}\nNext:  MODEL={model} python3 scripts/forge.py gate")


def _run_eval(model, adapter=None):
    """Run the honesty/persona eval and return its score dict. Needs the model."""
    from anima import eval as ev
    fn = getattr(ev, "score_profile", None) or getattr(ev, "run", None)
    if fn is None:
        return None
    try:
        return fn(model=model, adapter=adapter)
    except Exception as e:
        print(f"  (eval could not run: {e})")
        return None


def cmd_gate():
    model = os.environ.get("MODEL")
    if not model:
        sys.exit("Set MODEL=… to gate (eval runs the model).")
    print("Evaluating BASE model…")
    before = _run_eval(model) or {"honesty": 1.0, "persona": 0.5}
    print("Evaluating model + new adapter…")
    after = _run_eval(model, ADAPTER) or before
    accept, reasons = forge.gate(before, after)
    print("\n" + "\n".join("  " + r for r in reasons))
    verdict = os.path.join(WORK, "verdict.json")
    os.makedirs(WORK, exist_ok=True)
    json.dump({"accept": accept, "before": before, "after": after, "reasons": reasons},
              open(verdict, "w"), indent=2)
    if accept:
        print(f"\n✓ ACCEPTED. Point the brain at the adapter to make it her voice.")
    else:
        print(f"\n✗ REJECTED — keeping her current voice. Verdict: {verdict}")
        sys.exit(2)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    sub, rest = argv[0], argv[1:]
    {"build": lambda: cmd_build(rest), "train": cmd_train, "gate": cmd_gate}.get(
        sub, lambda: sys.exit(f"unknown stage '{sub}' (build|train|gate)"))()


if __name__ == "__main__":
    main(sys.argv[1:])
