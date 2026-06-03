#!/usr/bin/env python3
"""
Local Balinese / Indonesian / English transcriber, built on Meta's MMS model
(facebook/mms-1b-all), which supports 1,100+ languages including Balinese (ban).

Unlike Whisper, MMS actually knows Balinese. It transcribes one language at a
time (lowercase, no punctuation), so for a mixed recording this script runs
several candidate languages and, for each short chunk of audio, keeps the one
the model is most confident about — giving you a single readable transcript
that switches language as the speaker does.

Usage:
    python transcribe_bali.py INPUT_AUDIO [--lang mix] [--out FILE.txt]

    --lang mix          (default) try Balinese + Indonesian + English per chunk
    --lang ban          force Balinese
    --lang ind          force Indonesian
    --lang eng          force English
    --lang ban,ind      try just these two
    --list-langs        print supported language codes (for the region) and exit
"""

import argparse
import subprocess
import shutil
import sys
import os

SAMPLE_RATE = 16000
MODEL_ID = "facebook/mms-1b-all"

# Codes spoken around Bali / Indonesia, shown by --list-langs for convenience.
REGION_HINTS = {
    "ban": "Balinese",
    "ind": "Indonesian",
    "jav": "Javanese",
    "sun": "Sundanese",
    "min": "Minangkabau",
    "bug": "Buginese",
    "mad": "Madurese",
    "ace": "Acehnese",
    "eng": "English",
}

LANG_PRESETS = {"mix": ["ban", "ind", "eng"]}


def read_audio(path):
    """Decode any audio/video file to mono 16 kHz float32 using ffmpeg."""
    if shutil.which("ffmpeg") is None:
        sys.exit(
            "ffmpeg is not installed. Install it first:\n"
            "  macOS:  brew install ffmpeg\n"
            "  (no Homebrew? install it from https://brew.sh first)"
        )
    if not os.path.exists(path):
        sys.exit(f"File not found: {path}")

    import numpy as np

    cmd = [
        "ffmpeg", "-nostdin", "-threads", "0", "-i", path,
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.exit("ffmpeg could not read that file:\n" + proc.stderr.decode("utf-8", "ignore")[-800:])
    audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        sys.exit("No audio decoded from that file.")
    return audio


def pick_device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(device):
    from transformers import Wav2Vec2ForCTC, AutoProcessor
    print(f"Loading {MODEL_ID} (first run downloads ~3.8 GB, then it's cached)…", flush=True)
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID).to(device)
    model.eval()
    return processor, model


def available_langs(processor):
    """Return the set of language codes the model has, or empty if we can't tell.

    MMS stores a nested vocab {lang: {token: id}}. If we instead see a flat
    {token: id} we can't enumerate languages here, so we return empty and let
    load_adapter() validate at runtime rather than risk skipping a valid one.
    """
    try:
        vocab = processor.tokenizer.vocab
    except Exception:
        return set()
    if isinstance(vocab, dict) and vocab and all(isinstance(v, dict) for v in vocab.values()):
        return set(vocab.keys())
    return set()


def transcribe_pass(processor, model, device, audio, lang, chunk_sec):
    """Transcribe the whole file in one language. Returns list of (text, confidence) per chunk."""
    import torch
    processor.tokenizer.set_target_lang(lang)
    model.load_adapter(lang)

    step = int(chunk_sec * SAMPLE_RATE)
    results = []
    n_chunks = max(1, (len(audio) + step - 1) // step)
    for i in range(n_chunks):
        chunk = audio[i * step : (i + 1) * step]
        if chunk.size < SAMPLE_RATE // 4:  # skip < 0.25s tail
            results.append(("", 0.0))
            continue
        inputs = processor(chunk, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        conf = probs.max(dim=-1).values.mean().item()
        ids = torch.argmax(logits, dim=-1)[0]
        text = processor.decode(ids).strip()
        results.append((text, conf))
        print(f"  [{lang}] chunk {i+1}/{n_chunks}  conf={conf:.2f}", flush=True)
    return results


def fmt_ts(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    ap = argparse.ArgumentParser(description="Local Balinese/Indonesian/English transcriber (Meta MMS).")
    ap.add_argument("input", nargs="?", help="audio or video file")
    ap.add_argument("--lang", default="mix", help="mix | ban | ind | eng | comma-separated codes")
    ap.add_argument("--out", help="output .txt path (default: alongside the input file)")
    ap.add_argument("--chunk", type=float, default=20.0, help="chunk length in seconds (default 20)")
    ap.add_argument("--list-langs", action="store_true", help="list supported languages and exit")
    args = ap.parse_args()

    if not args.input and not args.list_langs:
        ap.error("please give an audio file (or use --list-langs)")
    if args.input and not os.path.exists(args.input):
        sys.exit(f"File not found: {args.input}")

    device = pick_device()
    processor, model = load_model(device)
    avail = available_langs(processor)

    if args.list_langs:
        if not avail:
            print("\nCouldn't enumerate the language list from the tokenizer in this version,")
            print("but the model validates each code when it loads. Region codes to try:")
            for code, name in REGION_HINTS.items():
                print(f"  {code}  {name}")
            return
        print(f"\nModel supports {len(avail)} languages. Region-relevant ones:")
        for code, name in REGION_HINTS.items():
            mark = "yes" if code in avail else "NO (not in this model)"
            print(f"  {code}  {name:<14} {mark}")
        return

    # Resolve requested languages.
    langs = LANG_PRESETS.get(args.lang, [c.strip() for c in args.lang.split(",") if c.strip()])
    missing = [l for l in langs if avail and l not in avail]
    if missing:
        print(f"Warning: these codes aren't in the model and will be skipped: {missing}")
        langs = [l for l in langs if l in avail]
    if not langs:
        sys.exit("No usable languages requested. Try --list-langs to see what's available.")

    print(f"Device: {device}  |  Languages to try: {', '.join(langs)}")
    audio = read_audio(args.input)
    dur = len(audio) / SAMPLE_RATE
    print(f"Audio length: {fmt_ts(dur)}  ({dur:.0f}s)\n")

    # One full pass per language.
    passes = {}
    for lang in langs:
        print(f"Transcribing pass: {lang}")
        try:
            passes[lang] = transcribe_pass(processor, model, device, audio, lang, args.chunk)
        except Exception as e:
            print(f"  Skipping '{lang}' — the model couldn't load this language: {e}")
    langs = [l for l in langs if l in passes]
    if not passes:
        sys.exit("None of the requested languages could be loaded. Run with --list-langs to see options.")

    n_chunks = max(len(v) for v in passes.values())
    merged_lines = []
    per_lang_text = {lang: [] for lang in langs}

    for i in range(n_chunks):
        # Pick the most confident language for this chunk.
        best_lang, best_conf, best_text = None, -1.0, ""
        for lang in langs:
            if i < len(passes[lang]):
                text, conf = passes[lang][i]
                per_lang_text[lang].append(text)
                if text and conf > best_conf:
                    best_lang, best_conf, best_text = lang, conf, text
        ts = fmt_ts(i * args.chunk)
        if best_text:
            merged_lines.append(f"[{ts}] ({best_lang}) {best_text}")

    out_path = args.out or os.path.splitext(args.input)[0] + ".transcript.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=== BEST-PER-SEGMENT TRANSCRIPT (auto language) ===\n\n")
        f.write("\n".join(merged_lines) + "\n\n")
        for lang in langs:
            f.write(f"\n=== FULL {lang.upper()} PASS ===\n\n")
            f.write(" ".join(t for t in per_lang_text[lang] if t).strip() + "\n")

    print("\n----- BEST-PER-SEGMENT TRANSCRIPT -----\n")
    print("\n".join(merged_lines) if merged_lines else "(no speech recognized)")
    print(f"\nSaved full results (including per-language passes) to:\n  {out_path}")


if __name__ == "__main__":
    main()
