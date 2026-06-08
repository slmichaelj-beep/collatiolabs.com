#!/usr/bin/env python3
"""
Balinese transcriber using Meta's Omnilingual ASR (released Nov 2025),
which supports 1,600+ languages including Balinese (ban_Latn).

Omnilingual only accepts clips under 40 seconds, so this script splits the
input into short chunks with ffmpeg, transcribes each in the chosen language,
and stitches the results back together with timestamps.

Usage:
    python transcribe_omni.py INPUT_AUDIO [--lang ban_Latn] [--model omniASR_LLM_300M_v2]

    --lang ban_Latn     (default) Balinese      | ind_Latn = Indonesian | eng_Latn = English
    --model NAME        omniASR_LLM_300M (default, ~6GB) | _1B | _7B (huge)
    --list-langs        print region-relevant supported language codes and exit
"""

import argparse
import subprocess
import shutil
import sys
import os
import glob
import tempfile

SAMPLE_RATE = 16000
DEFAULT_MODEL = "omniASR_LLM_300M"
REGION_CODES = {"ban", "ind", "jav", "sun", "min", "bug", "mad", "ace", "eng"}


def available_models():
    """Read the model card names bundled with the installed package."""
    import re
    import omnilingual_asr
    base = os.path.dirname(omnilingual_asr.__file__)
    names = set()
    for root, _dirs, files in os.walk(os.path.join(base, "cards")):
        for fn in files:
            if fn.endswith((".yaml", ".yml")):
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r"\s*name:\s*([A-Za-z0-9_./-]+)", line)
                        if m and m.group(1).startswith("omniASR"):
                            names.add(m.group(1))
    return sorted(names)


def as_text(x):
    """Normalise a transcription result into a plain string."""
    if isinstance(x, str):
        return x
    for attr in ("text", "transcription"):
        if hasattr(x, attr):
            return getattr(x, attr)
    if isinstance(x, dict):
        return x.get("text") or x.get("transcription") or str(x)
    return str(x)


def split_audio(path, chunk_sec, tmpdir):
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg is not installed. Install it with:  brew install ffmpeg")
    out = os.path.join(tmpdir, "chunk_%05d.wav")
    cmd = [
        "ffmpeg", "-nostdin", "-i", path,
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "segment", "-segment_time", str(chunk_sec),
        "-reset_timestamps", "1", out,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.exit("ffmpeg could not read/split that file:\n" + r.stderr.decode("utf-8", "ignore")[-800:])
    return sorted(glob.glob(os.path.join(tmpdir, "chunk_*.wav")))


def fmt_ts(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    ap = argparse.ArgumentParser(description="Balinese transcriber (Meta Omnilingual ASR).")
    ap.add_argument("input", nargs="?", help="audio or video file")
    ap.add_argument("--lang", default="ban_Latn", help="language code_script (default ban_Latn)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Omnilingual model card name")
    ap.add_argument("--chunk", type=float, default=30.0, help="chunk length in seconds (<40)")
    ap.add_argument("--batch", type=int, default=4, help="chunks per batch")
    ap.add_argument("--out", help="output .txt path")
    ap.add_argument("--list-langs", action="store_true", help="list region languages and exit")
    ap.add_argument("--list-models", action="store_true", help="list available model cards and exit")
    args = ap.parse_args()

    if args.list_models:
        print("Available model cards (pass with --model):")
        for m in available_models():
            print(f"  {m}")
        return

    if args.chunk >= 40:
        sys.exit("--chunk must be under 40 seconds (Omnilingual's limit).")

    try:
        from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs
    except Exception as e:
        sys.exit(f"Couldn't import omnilingual_asr ({e}). Run ./setup.sh first.")

    if args.list_langs:
        region = sorted(l for l in supported_langs if l.split("_")[0] in REGION_CODES)
        print(f"Total supported languages: {len(supported_langs)}")
        print("Region-relevant codes you can pass to --lang:")
        for l in region:
            print(f"  {l}")
        return

    if not args.input:
        ap.error("please give an audio file (or use --list-langs)")
    if not os.path.exists(args.input):
        sys.exit(f"File not found: {args.input}")
    if args.lang not in supported_langs:
        sys.exit(f"Language '{args.lang}' isn't supported. Run --list-langs to see options.")

    from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
    print(f"Loading model {args.model} (first run downloads from Hugging Face)…", flush=True)
    try:
        pipeline = ASRInferencePipeline(model_card=args.model)
    except Exception as e:
        if "NotKnown" in type(e).__name__ or "not" in str(e).lower():
            models = available_models()
            listing = "\n  ".join(models) if models else "(none found)"
            sys.exit(
                f"Model '{args.model}' isn't registered in your install.\n"
                f"Available models:\n  {listing}\n"
                f"Re-run with, e.g.:  --model omniASR_LLM_300M"
            )
        raise

    with tempfile.TemporaryDirectory() as tmp:
        print("Splitting audio into chunks…", flush=True)
        chunks = split_audio(args.input, args.chunk, tmp)
        if not chunks:
            sys.exit("No audio chunks were produced.")
        print(f"{len(chunks)} chunks. Transcribing as {args.lang}…", flush=True)

        texts = []
        for i in range(0, len(chunks), args.batch):
            part = chunks[i : i + args.batch]
            res = pipeline.transcribe(part, lang=[args.lang] * len(part), batch_size=len(part))
            texts.extend(as_text(r) for r in res)
            print(f"  {min(i + args.batch, len(chunks))}/{len(chunks)} chunks done", flush=True)

    lines = [f"[{fmt_ts(i * args.chunk)}] {t}" for i, t in enumerate(texts) if t.strip()]
    out_path = args.out or os.path.splitext(args.input)[0] + f".omni_{args.lang}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"=== OMNILINGUAL ASR ({args.lang}, model {args.model}) ===\n\n")
        f.write("\n".join(lines) + "\n\n=== FULL TEXT ===\n\n")
        f.write(" ".join(t.strip() for t in texts if t.strip()) + "\n")

    print("\n----- TRANSCRIPT -----\n")
    print("\n".join(lines) if lines else "(no speech recognized)")
    print(f"\nSaved to:\n  {out_path}")


if __name__ == "__main__":
    main()
