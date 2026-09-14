"""intake_audio — Universal Knowledge Intake for AUDIOBOOK / long-form audio sources.

WHAT THIS HANDLES — open, unencrypted formats only:

  Audiobook / long-form audio: .m4b (the open audiobook container) plus ordinary audio
  (.mp3, .m4a, .wav, .aac, .flac, .ogg, .aiff). Vera reads SAFE container metadata — title,
  author, duration, codec/container, chapters — via ffprobe (headers only, never decoding),
  converts a decodable file to a 16 kHz mono wav with ffmpeg, and transcribes it with the
  approved LOCAL STT (faster-whisper) into timestamped, chapter-aware chunks, to be stored as a
  citable reference and answered with source labels by the intake spine.

DELIBERATELY OUT OF SCOPE — NO DRM, NO PROTECTED FORMATS:

  This module supports ONLY files that ffmpeg can already read WITHOUT a key. It contains NO
  DRM-handling code of any kind — no keys, no key-recovery, no decryption flags — and it does not
  support DRM-protected stores. If a file cannot be decoded (corrupt, or an unsupported/encrypted
  encoding), Vera says so HONESTLY and NEVER fabricates a transcript; it asks for a standard audio
  file or a text transcript instead. scripts/certify_audiobook_intake.py greps this module and
  fails if any DRM/decrypt/key token ever appears, so the "open formats only" posture is enforced.

  Transcription is HEAVY and therefore opt-in (ANIMA_INTAKE_ACTIVATE_HEAVY=1), same as every other
  heavy parser — dropping in audio never silently spins a model or the network. Cloud STT is used
  ONLY on an explicit opt-in (ANIMA_AUDIO_ALLOW_CLOUD=1) and is not implemented here by default.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# Open audiobook / long-form audio containers this pipeline transcribes. .m4b is the open audiobook
# container; the rest are ordinary unencrypted audio. Protected formats are intentionally NOT here.
LONGFORM_AUDIO_EXTS = {".m4b", ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".aiff", ".aif"}

_DEFAULT_STT_MODEL = os.environ.get("ANIMA_AUDIO_STT_MODEL", "base.en")


def is_longform_audio(path_or_url: str) -> bool:
    return Path(str(path_or_url)).suffix.lower() in LONGFORM_AUDIO_EXTS


# Back-compat alias (an audiobook is just long-form audio); keeps existing importers working.
is_audiobook = is_longform_audio


def _tool(name: str) -> Optional[str]:
    return shutil.which(name)


def _heavy_on() -> bool:
    """Transcription is heavy (a model) — opt-in only, mirroring intake_parsers' heavy seam."""
    return os.environ.get("ANIMA_INTAKE_ACTIVATE_HEAVY") == "1"


def _run(cmd: list, timeout: float = 120.0) -> tuple:
    """Run a tool, return (returncode, stdout, stderr). Never raises out."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # pragma: no cover - tool missing / timeout
        return 255, "", repr(e)


# ---------------------------------------------------------------------------
# 1. SAFE METADATA — ffprobe reads headers only: container, codec, duration, title/author, chapters.
#    No decode, no key. Returns {} when ffprobe is absent or the file is opaque.
# ---------------------------------------------------------------------------
def media_probe(path: str) -> dict:
    ffprobe = _tool("ffprobe")
    out = {"container": "", "audio_codec": "", "duration_s": None, "title": "", "author": "",
           "chapters": [], "probe_tool": "ffprobe" if ffprobe else None}
    if not ffprobe or not Path(path).exists():
        return out
    rc, so, se = _run([ffprobe, "-v", "quiet", "-print_format", "json",
                       "-show_format", "-show_streams", "-show_chapters", str(path)], timeout=30)
    try:
        data = json.loads(so) if so.strip() else {}
    except Exception:
        data = {}
    fmt = data.get("format", {}) or {}
    tags = {k.lower(): v for k, v in (fmt.get("tags", {}) or {}).items()}
    streams = data.get("streams", []) or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    out["container"] = fmt.get("format_name", "")
    out["audio_codec"] = audio.get("codec_name", "")
    try:
        out["duration_s"] = round(float(fmt.get("duration")), 1) if fmt.get("duration") else None
    except Exception:
        out["duration_s"] = None
    out["title"] = tags.get("title", "") or tags.get("album", "")
    out["author"] = tags.get("artist", "") or tags.get("author", "") or tags.get("album_artist", "")
    out["chapters"] = [
        {"title": (c.get("tags", {}) or {}).get("title", ""),
         "start_s": _f(c.get("start_time")), "end_s": _f(c.get("end_time"))}
        for c in (data.get("chapters", []) or [])
    ]
    return out


def _f(x):
    try:
        return round(float(x), 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. DECODE — ffmpeg to a 16 kHz mono wav, with NO key and NO decryption flag of any kind. An
#    unreadable file (corrupt / unsupported / encrypted) simply fails here — the honest outcome.
# ---------------------------------------------------------------------------
def is_decodable(path: str, probe: Optional[dict] = None) -> tuple:
    """(bool, reason). ffmpeg is asked to decode the first 0.2s to a null sink; success means the
    audio is readable as-is, WITHOUT any key. A file ffmpeg cannot read returns (False, why)."""
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg not available"
    rc, so, se = _run([ffmpeg, "-v", "error", "-t", "0.2", "-i", str(path),
                       "-f", "null", "-"], timeout=30)
    if rc == 0:
        return True, "decodable through the local ffmpeg path (no key needed)"
    return False, ("not decodable by the local ffmpeg path" + (": " + se.strip()[:120] if se else ""))


def decode_to_wav(path: str, out_wav: str) -> tuple:
    """Convert to 16 kHz mono wav for STT. NO decryption flag, NO key. Returns (out_wav_or_None, why)."""
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        return None, "ffmpeg not available"
    # NOTE: deliberately only safe, standard transcode args. This command reads already-readable audio.
    rc, so, se = _run([ffmpeg, "-v", "error", "-y", "-i", str(path),
                       "-ac", "1", "-ar", "16000", str(out_wav)], timeout=600)
    if rc == 0 and Path(out_wav).exists() and Path(out_wav).stat().st_size > 0:
        return out_wav, "decoded"
    return None, ("decode failed" + (": " + se.strip()[:160] if se else ""))


# ---------------------------------------------------------------------------
# 3. TRANSCRIBE — approved LOCAL STT (faster-whisper). Returns timestamped segments. Cloud only with
#    an explicit opt-in (ANIMA_AUDIO_ALLOW_CLOUD=1), which this module does not implement by default.
# ---------------------------------------------------------------------------
def transcribe_wav(wav: str, *, model: str = _DEFAULT_STT_MODEL, allow_cloud: bool = False) -> tuple:
    """(segments, engine, error). segments = [{start, end, text}]. Local-first; never silently cloud."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        if allow_cloud and os.environ.get("ANIMA_AUDIO_ALLOW_CLOUD") == "1":
            return None, None, "local STT absent and cloud STT not implemented (opt-in seam only)"
        return None, None, ("local STT (faster-whisper) not available: %r" % (e,))[:160]
    try:
        m = WhisperModel(model, device="cpu", compute_type="int8")
        segs, _info = m.transcribe(str(wav), vad_filter=False)
        out = [{"start": round(float(s.start), 2), "end": round(float(s.end), 2),
                "text": (s.text or "").strip()} for s in segs if (s.text or "").strip()]
        return out, "faster-whisper:" + model, None
    except Exception as e:  # pragma: no cover - model/runtime failure
        return None, None, ("transcription failed: %r" % (e,))[:160]


# ---------------------------------------------------------------------------
# 4. CHUNKING — chapter-aware: group transcript segments under the ffprobe chapter they fall in
#    (else a single "transcript" section), every chunk carrying [start_s, end_s] for citation.
# ---------------------------------------------------------------------------
def chunks_from_segments(segments: list, chapters: Optional[list] = None) -> list:
    chunks = []
    chapters = [c for c in (chapters or []) if c.get("start_s") is not None]
    for seg in segments or []:
        sec = "transcript"
        if chapters:
            st = seg.get("start", 0.0)
            ch = None
            for c in chapters:
                if c["start_s"] <= st and (c.get("end_s") is None or st < c["end_s"]):
                    ch = c
                    break
            sec = (ch.get("title") or "chapter") if ch else "transcript"
        chunks.append({"page": None, "section": sec, "text": seg.get("text", ""),
                       "start_s": seg.get("start"), "end_s": seg.get("end")})
    return chunks


def _ts(sec) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    return f"{sec // 3600:d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


# ---------------------------------------------------------------------------
# 5. THE PARSER — the normalized intake parse dict (same contract as intake_parsers' parsers). It
#    NEVER fabricates: undecodable -> needs_dependency with an honest message; decodable + STT ->
#    a real transcript with timestamped chunks; the per-stage pipeline status rides in meta for the MRI.
# ---------------------------------------------------------------------------
def parse_longform_audio(path_or_url: str, *, fmt: Optional[str] = None,
                         allow_cloud: bool = False) -> dict:
    path = str(path_or_url)
    is_book = (Path(path).suffix.lower() == ".m4b") or (fmt == "audiobook")
    kind = "audiobook" if is_book else "audio"
    pipeline = {"detected": True, "metadata": "pending", "decode": "pending",
                "transcription": "pending"}
    meta = {"format": fmt or kind, "subkind": kind, "source_ref": path,
            "title_hint": Path(path).name, "audio_pipeline": pipeline}

    probe = media_probe(path)
    meta.update({"container": probe.get("container"), "audio_codec": probe.get("audio_codec"),
                 "duration_s": probe.get("duration_s"), "audio_title": probe.get("title"),
                 "audio_author": probe.get("author"), "chapters": len(probe.get("chapters") or [])})
    pipeline["metadata"] = "read" if probe.get("probe_tool") else "ffprobe_absent"

    decodable, reason = is_decodable(path, probe)
    pipeline["decode"] = "decodable" if decodable else "undecodable"
    if not decodable:
        pipeline["transcription"] = "skipped (undecodable)"
        need = ("a decodable audio file (.mp3/.m4a/.m4b/.wav/.aac) or a text transcript — I couldn't "
                "read this one (" + reason + ")")
        return _result(status="needs_dependency", need=need, text="", chunks=[], meta=meta,
                       decode_reason=reason)

    if not _heavy_on():
        pipeline["transcription"] = "off (opt-in: ANIMA_INTAKE_ACTIVATE_HEAVY=1)"
        return _result(status="needs_dependency",
                       need="local transcription (set ANIMA_INTAKE_ACTIVATE_HEAVY=1 to allow the "
                            "approved local STT to run)",
                       text="", chunks=[], meta=meta, decode_reason=reason)

    tmp = tempfile.mkdtemp(prefix="audio-")
    wav = str(Path(tmp) / "audio.wav")
    try:
        out, dreason = decode_to_wav(path, wav)
        if not out:
            pipeline["decode"] = "undecodable"
            pipeline["transcription"] = "skipped (decode failed)"
            return _result(status="needs_dependency",
                           need="a decodable audio file (.mp3/.m4a/.m4b/.wav/.aac) — I couldn't read "
                                "this one (" + dreason + ")",
                           text="", chunks=[], meta=meta, decode_reason=dreason)
        segments, engine, terr = transcribe_wav(wav, allow_cloud=allow_cloud)
        if segments is None:
            pipeline["transcription"] = "unavailable"
            return _result(status="needs_dependency",
                           need="local STT (faster-whisper): " + (terr or "unavailable"),
                           text="", chunks=[], meta=meta, decode_reason=dreason)
        chunks = chunks_from_segments(segments, probe.get("chapters"))
        text = "\n".join(c["text"] for c in chunks if c["text"]).strip()
        pipeline["transcription"] = "transcribed (%d segments, %s)" % (len(segments), engine)
        meta.update({"stt_engine": engine, "transcript_segments": len(segments),
                     "provenance": "%s transcript (local STT, %s)" % (kind, engine)})
        return _result(status="ok", text=text, chunks=chunks, meta=meta, decode_reason=dreason)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Canonical name is parse_longform_audio; keep parse_audiobook as the back-compat entry point.
parse_audiobook = parse_longform_audio


def _result(*, status, text="", chunks=None, figures=None, meta=None, need="",
            decode_reason="") -> dict:
    m = dict(meta or {})
    if decode_reason:
        m["decode_reason"] = decode_reason
    return {"status": status, "text": text, "chunks": list(chunks or []),
            "figures": list(figures or []), "tables": [], "meta": m, "need": need}


# A human one-liner the intake classifier surfaces when audio is detected vs transcribed.
def product_message(parsed: dict) -> str:
    if parsed.get("status") == "ok":
        return ("I transcribed this audio and stored it as a reference source. You can ask "
                "questions from it, and I'll cite the section/timestamp where possible.")
    return ("I can transcribe audiobooks and long-form audio (.mp3, .m4a, .m4b, .wav, .aac) on a "
            "local, on-device speech-to-text path. I couldn't decode this file — send a standard "
            "audio file or a text transcript and I'll ingest it.")


def _selftest() -> int:
    """Light, dependency-free checks: detection of open formats + honest-on-undecodable + no DRM
    surface. The full real-transcription end-to-end proof is scripts/certify_audiobook_intake.py."""
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    ok("detects .m4b/.mp3/.m4a/.wav/.aac as long-form audio",
       is_longform_audio("x.m4b") and is_longform_audio("y.mp3") and is_longform_audio("z.wav")
       and not is_longform_audio("z.txt"))
    ok("DRM-protected stores are NOT claimed (.aax/.aaxc/.aa unsupported by design)",
       not is_longform_audio("book.aax") and not is_longform_audio("book.aaxc")
       and not is_longform_audio("book.aa"))
    # an obviously-undecodable file (random bytes) must NOT pretend success
    import tempfile as _t
    d = _t.mkdtemp()
    p = Path(d) / "fake.m4b"
    p.write_bytes(b"\x00\x01not a real audio file\x02\x03" * 8)
    r = parse_longform_audio(str(p))
    ok("an undecodable file does NOT pretend success (needs_dependency, empty transcript, honest need)",
       r["status"] == "needs_dependency" and not r["text"] and bool(r["need"]))
    ok("the detected-audio MRI pipeline is recorded in meta",
       set(("detected", "metadata", "decode", "transcription"))
       <= set((r["meta"].get("audio_pipeline") or {}).keys()))
    shutil.rmtree(d, ignore_errors=True)
    print("\nINTAKE-AUDIO: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("intake_audio — honest audiobook / long-form audio intake (open formats only). "
          "Use --selftest, or parse_longform_audio(path).")
