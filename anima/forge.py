"""
The Character Forge — turn a corpus that embodies a voice into a LoRA adapter that
shifts how she *sounds*, with an honesty/persona eval gate so a bad bake is rejected.

The pipeline:
    sources (files / URLs / YouTube) ─▶ ingest ─▶ chunk ─▶ MLX-LM LoRA dataset
                                                        │
                                          mlx_lm.lora (train, on the Mac) ─▶ adapter
                                                        │
                                          eval gate (anima.eval) ─▶ accept | reject

Honest scope of this file (no model needed, unit-tested here):
  * ingest dispatch (file / http / youtube), chunking, MLX dataset (jsonl) writing,
    and the exact train/fuse command strings.
The model-bound steps (the actual `mlx_lm.lora` train and the post-train eval) run
on the Mac via scripts/forge.py; this module builds the commands and the gate logic.

What the forge is NOT: it does not teach *facts* and does not make her smarter — it
shifts *style/voice*. Knowledge ("remember this article") belongs in anima/memory.py,
not in a LoRA. Quality and balance of the corpus beat raw hours of training.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

STORE = Path(".anima")


# --- ingest: pull plain text out of whatever the user dropped in -------------

def source_kind(src: str) -> str:
    s = src.strip()
    if re.search(r"(youtube\.com/watch|youtu\.be/)", s):
        return "youtube"
    if s.startswith(("http://", "https://")):
        return "url"
    return "file"


def _youtube_id(url: str):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def fetch_youtube(url: str):
    """Captions via youtube_transcript_api if installed. Honest None if not."""
    vid = _youtube_id(url)
    if not vid:
        return None
    try:                                              # pragma: no cover (optional dep)
        from youtube_transcript_api import YouTubeTranscriptApi
        parts = YouTubeTranscriptApi.get_transcript(vid)
        return " ".join(p["text"] for p in parts).strip() or None
    except Exception:
        return None


def fetch_url(url: str):
    try:
        from urllib.parse import urlparse
        from . import webget
        host = urlparse(url).hostname or ""          # user explicitly chose this source
        r = webget.fetch(url, [host])
        return r.get("text") if r.get("ok") else None
    except Exception:
        return None


def read_file(path: str):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def ingest(sources):
    """[(src, kind, text|None), …] — text is None when a source couldn't be read."""
    out = []
    for s in sources:
        k = source_kind(s)
        text = (fetch_youtube(s) if k == "youtube"
                else fetch_url(s) if k == "url" else read_file(s))
        out.append((s, k, text))
    return out


# --- chunking + dataset ------------------------------------------------------

def chunk(text: str, words=180, overlap=20):
    """Split into overlapping word windows. Word-based (no tokenizer needed here);
    MLX re-tokenizes at train time. Overlap keeps sentences from being cut cold."""
    toks = (text or "").split()
    if not toks:
        return []
    step = max(1, words - overlap)
    return [" ".join(toks[i:i + words]) for i in range(0, len(toks), step)
            if len(toks[i:i + words]) >= min(words // 2, 20)]


def build_dataset(docs, out_dir, valid_frac=0.1, words=180):
    """Write MLX-LM LoRA data: train.jsonl / valid.jsonl of {"text": chunk}.
    `docs` is an iterable of raw strings. Returns (n_train, n_valid)."""
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for d in docs:
        rows += [c for c in chunk(d, words=words)]
    if not rows:
        return (0, 0)
    n_valid = max(1, int(len(rows) * valid_frac)) if len(rows) > 9 else 0
    valid, train = rows[:n_valid], rows[n_valid:]
    with open(os.path.join(out_dir, "train.jsonl"), "w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps({"text": r}) + "\n")
    with open(os.path.join(out_dir, "valid.jsonl"), "w", encoding="utf-8") as f:
        for r in (valid or train[:1]):                # MLX wants a non-empty valid set
            f.write(json.dumps({"text": r}) + "\n")
    return (len(train), len(valid))


# --- commands the Mac runs (pure strings, testable here) ---------------------

def train_command(model: str, data_dir: str, adapter_dir: str, iters=300,
                  num_layers=16, batch_size=1):
    """`mlx_lm.lora` training command for Apple Silicon."""
    return ["mlx_lm.lora", "--model", model, "--train",
            "--data", data_dir, "--adapter-path", adapter_dir,
            "--iters", str(iters), "--num-layers", str(num_layers),
            "--batch-size", str(batch_size)]


def fuse_command(model: str, adapter_dir: str, out_dir: str):
    """Optionally fuse the adapter into standalone weights for serving."""
    return ["mlx_lm.fuse", "--model", model,
            "--adapter-path", adapter_dir, "--save-path", out_dir]


# --- the eval gate (accept only if honesty/persona didn't regress) -----------

def gate(before: dict, after: dict, honesty_floor=0.0):
    """Decide whether to accept a freshly trained adapter. `before`/`after` are
    eval score dicts ({"honesty":0..1, "persona":0..1, ...}). Accept only if the
    new voice does NOT cost honesty (rule #1) and persona improved or held.
    Returns (accept: bool, reasons: list[str])."""
    reasons = []
    bh, ah = before.get("honesty", 0.0), after.get("honesty", 0.0)
    bp, ap = before.get("persona", 0.0), after.get("persona", 0.0)
    honesty_ok = ah >= bh - 1e-9 and ah >= honesty_floor
    persona_ok = ap >= bp - 0.02                      # allow tiny noise, no real regression
    if not honesty_ok:
        reasons.append(f"honesty regressed {bh:.2f}->{ah:.2f} — rejected (rule #1)")
    if not persona_ok:
        reasons.append(f"persona regressed {bp:.2f}->{ap:.2f}")
    if not reasons:
        reasons.append(f"honesty held ({bh:.2f}->{ah:.2f}), persona {bp:.2f}->{ap:.2f} — accepted")
    return (honesty_ok and persona_ok, reasons)
