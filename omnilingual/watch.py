#!/usr/bin/env python3
"""
Folder-watch transcriber.

Drop audio/video files into the Inbox folder. Each one is transcribed and a PDF
appears in the output folder you choose. Progress shows live in this window.
The program does the rest — no browser, no buttons.
"""
import os
import sys
import glob
import time
import shutil
import tempfile

from transcribe_omni import split_audio, as_text, fmt_ts, DEFAULT_MODEL
from pdfutil import write_pdf

CHUNK = 30.0
BATCH = 4
AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".wav", ".mp4", ".mov", ".aac", ".flac",
             ".ogg", ".oga", ".opus", ".aiff", ".aif", ".wma", ".webm", ".mkv", ".aax"}

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        print("  Loading speech model (first run downloads ~6 GB)…", flush=True)
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        _pipeline = ASRInferencePipeline(model_card=DEFAULT_MODEL)
        print("  Model ready.\n", flush=True)
    return _pipeline


def _bar(done, total):
    pct = int(100 * done / total) if total else 0
    fill = pct // 5
    return f"[{'#' * fill}{'-' * (20 - fill)}] {pct:3d}%  ({done}/{total} chunks)"


def transcribe_to_pdf(path, outdir, lang="eng_Latn", progress=None):
    name = os.path.basename(path)
    with tempfile.TemporaryDirectory() as tmp:
        chunks = split_audio(path, CHUNK, tmp)          # raises SystemExit if unreadable
        total = len(chunks)
        if total == 0:
            raise RuntimeError("no audio found in file")
        p = get_pipeline()
        texts = []
        for i in range(0, total, BATCH):
            part = chunks[i:i + BATCH]
            res = p.transcribe(part, lang=[lang] * len(part), batch_size=len(part))
            texts.extend(as_text(r) for r in res)
            if progress:
                progress(min(i + BATCH, total), total)
    lines = [f"[{fmt_ts(i * CHUNK)}] {t}" for i, t in enumerate(texts) if t.strip()]
    body = " ".join(t.strip() for t in texts if t.strip())
    base = os.path.splitext(name)[0]
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, base + ".txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n=== FULL TEXT ===\n\n" + body + "\n")
    pdf = os.path.join(outdir, base + ".pdf")
    write_pdf("\n".join(lines) + "\n\n" + body, pdf)
    return pdf


def _set_aside(path, skipped_dir, reason):
    name = os.path.basename(path)
    shutil.move(path, os.path.join(skipped_dir, name))
    with open(os.path.join(skipped_dir, name + " - WHY.txt"), "w", encoding="utf-8") as f:
        f.write(reason + "\n")


def process_file(path, outdir, done_dir, skipped_dir):
    name = os.path.basename(path)
    if path.lower().endswith(".aax"):
        _set_aside(path, skipped_dir, "DRM-protected Audible (.aax) file — can't be read directly.")
        print(f"  set aside (DRM-locked): {name}\n", flush=True)
        return
    print(f"  ► {name}", flush=True)

    def progress(done, total):
        sys.stdout.write("\r    " + _bar(done, total))
        sys.stdout.flush()

    try:
        pdf = transcribe_to_pdf(path, outdir, progress=progress)
    except SystemExit as e:
        print()
        _set_aside(path, skipped_dir, str(e))
        print(f"  could not read: {name}\n", flush=True)
        return
    except Exception as e:
        print()
        _set_aside(path, skipped_dir, str(e))
        print(f"  failed: {name} ({e})\n", flush=True)
        return
    print()
    shutil.move(path, os.path.join(done_dir, name))
    print(f"  ✓ PDF saved: {pdf}\n", flush=True)


def _stable(path):
    try:
        a = os.path.getsize(path)
        time.sleep(1.0)
        return a > 0 and a == os.path.getsize(path)
    except OSError:
        return False


def main():
    home = os.path.expanduser("~")
    base = os.path.join(home, "Transcribe")
    inbox = os.path.join(base, "Inbox")
    done = os.path.join(base, "Done")
    skipped = os.path.join(base, "Skipped")
    default_out = os.path.join(base, "PDFs")
    for d in (inbox, done, skipped, default_out):
        os.makedirs(d, exist_ok=True)

    print("\n  Folder Transcriber")
    print("  ------------------")
    try:
        ans = input(f"  Where should PDFs go? [{default_out}]: ").strip()
    except EOFError:
        ans = ""
    outdir = os.path.expanduser(ans) if ans else default_out
    os.makedirs(outdir, exist_ok=True)

    os.system(f'open "{inbox}" >/dev/null 2>&1')
    print(f"\n  ▸ Drop audio/video files into:  {inbox}")
    print(f"  ▸ PDFs appear in:               {outdir}")
    print("  ▸ Leave this window open. Ctrl-C to stop.\n", flush=True)

    seen = set()
    while True:
        for path in sorted(glob.glob(os.path.join(inbox, "*"))):
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in AUDIO_EXT:
                continue
            if path in seen or not _stable(path):
                continue
            seen.add(path)
            process_file(path, outdir, done, skipped)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
