#!/usr/bin/env python3
"""certify_audiobook_intake — Universal Knowledge Intake for AUDIOBOOK / long-form audio, HONEST.

Open, unencrypted formats only (.m4b + .mp3/.m4a/.wav/.aac/.flac/.ogg/.aiff). The eight proofs:

  1. DETECTED                    — .m4b -> "audiobook"; .mp3/.m4a/.wav/.aac -> "audio"; both routed
                                   to the honest local-audio parser. DRM stores (.aax) are NOT claimed.
  2. UNDECODABLE -> NO PRETENCE  — an unreadable file returns needs_dependency with an honest message
                                   and an EMPTY transcript — it never fabricates one.
  8. NO DRM / NO BYPASS          — anima/intake_audio.py contains no DRM-circumvention token, and the
                                   ffmpeg decode/probe commands pass only safe transcode args (no
                                   activation/decryption/key flag). Open formats only, by construction.

  And the end-to-end close (REAL local tooling: macOS `say` -> ffmpeg -> faster-whisper; skip-not-fail
  when any is absent, so CI without them is honestly reported rather than faked):

  3. DECODABLE AUDIO TRANSCRIBES — a DRM-FREE audio fixture is decoded + transcribed by the local STT
                                   into a real transcript with timestamped, chapter-aware chunks.
  4. TRANSCRIPT STORED           — stored as a citable reference (kind=audiobook_transcript).
  5. TRANSCRIPT RETRIEVABLE      — the reference + its content come back from the library.
  6. ANSWER USES TRANSCRIPT      — the source-aware recall answers from the transcript...
  7. SOURCE LABELS               — ...labelled as a reference with audio/audiobook transcript provenance.

Hermetic except the model (the approved local STT); real .anima redirected for the store/recall legs.
Exit 0 == CERTIFIED (the real leg ran or was honestly SKIPPED); 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re as _re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


def main() -> int:
    from anima import (intake_parsers as P, intake_queue, intake_audio as A,
                       source_aware as sa, server)
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("AUDIOBOOK / LONG-FORM AUDIO INTAKE — detect -> metadata -> decode -> transcribe -> "
          "store -> retrieve -> answer (open formats only, no DRM)")
    print("=" * 100)
    end_to_end = "SKIPPED"

    # ---- 1. DETECTION ------------------------------------------------------------------------
    ck("1. .m4b is DETECTED as 'audiobook'; .mp3/.m4a/.wav/.aac as 'audio' (long-form audio family)",
       P.detect_format("book.m4b") == "audiobook" and P.detect_format("a.mp3") == "audio"
       and P.detect_format("b.m4a") == "audio" and P.detect_format("c.wav") == "audio"
       and P.detect_format("d.aac") == "audio")
    ck("1. both families route to the honest local-audio parser (PARSERS, heavy seam)",
       callable(P.PARSERS.get("audiobook")) and callable(P.PARSERS.get("audio"))
       and not P.is_light("audiobook") and not P.is_light("audio"))
    ck("1. DRM stores are NOT claimed (.aax/.aaxc/.aa unsupported by design)",
       P.detect_format("book.aax") not in ("audio", "audiobook")
       and not A.is_longform_audio("book.aax") and not A.is_longform_audio("x.aaxc")
       and not A.is_longform_audio("y.aa"))

    # ---- 8. NO DRM / NO BYPASS (the load-bearing safety + the "open formats only" posture) ---
    audio_src = (ROOT / "anima" / "intake_audio.py").read_text()
    ffmpeg_args = _re.findall(r"_run\(\[ffmpeg[^\]]*\]", audio_src)
    bad_arg = any(("activation" in a.lower() or "decrypt" in a.lower() or "-key" in a.lower())
                  for a in ffmpeg_args)
    ck("8. the ffmpeg decode/probe commands pass ONLY safe transcode args (no activation/decrypt/key)",
       bool(ffmpeg_args) and not bad_arg)
    circ = [t for t in ("activation_bytes", "activation bytes", "-activation", "rcrack",
                        "rainbow table", "rainbow_table", "deactivation") if t in audio_src.lower()]
    ck("8. NO DRM-circumvention token (activation-key / key-recovery / rainbow-table) in intake_audio.py",
       not circ)

    d = tempfile.mkdtemp(prefix="audiobook-cert-")
    try:
        # ---- 2. UNDECODABLE -> NO PRETENCE -------------------------------------------------
        broken = Path(d) / "broken.m4b"
        broken.write_bytes(b"\x00\x01definitely not a decodable audio file\x02\x03" * 16)
        r_lock = A.parse_longform_audio(str(broken))
        ck("2. an undecodable file does NOT pretend success (needs_dependency, EMPTY transcript)",
           r_lock["status"] == "needs_dependency" and not r_lock["text"].strip() and bool(r_lock["need"]))
        ck("2. the honest message asks for a decodable audio file / a transcript (no fabrication)",
           "decodable" in r_lock["need"].lower() or "transcript" in r_lock["need"].lower())
        msg = A.product_message(r_lock).lower()
        ck("2. the product message offers the local transcription path (no fabricated transcript)",
           "transcri" in msg and "audio" in msg)
        ck("MRI pipeline recorded (detected -> metadata -> decode -> transcription)",
           {"detected", "metadata", "decode", "transcription"}
           <= set((r_lock["meta"].get("audio_pipeline") or {}).keys()))

        # ---- 3-7. REAL end-to-end (skip-not-fail) ------------------------------------------
        say, ff = shutil.which("say"), shutil.which("ffmpeg")
        try:
            import faster_whisper  # noqa: F401
            have_stt = True
        except Exception:
            have_stt = False
        if not (say and ff and have_stt):
            print("  --   3-7 end-to-end SKIPPED (need macOS `say` + ffmpeg + faster-whisper to build "
                  "and transcribe a decodable fixture) — detection/metadata/no-DRM proven above")
        else:
            # Build a DRM-FREE decodable audiobook fixture with approved local tooling only.
            aiff = Path(d) / "spoken.aiff"
            m4b = Path(d) / "book.m4b"
            line = ("Chapter one. The blue copper ladder has nine rungs. It was forged in the city "
                    "of Aldermere. The cell theory states that living things are made of cells.")
            subprocess.run([say, line, "-o", str(aiff)], timeout=60,
                           capture_output=True)
            subprocess.run([ff, "-v", "error", "-y", "-i", str(aiff), "-c:a", "aac", str(m4b)],
                           timeout=120, capture_output=True)
            os.environ["ANIMA_INTAKE_ACTIVATE_HEAVY"] = "1"
            pr = A.parse_longform_audio(str(m4b))
            transcribed = (pr["status"] == "ok" and pr["text"].strip()
                           and any(c.get("start_s") is not None for c in pr["chunks"]))
            ck("3. a DECODABLE audio fixture TRANSCRIBES via local STT -> ok + transcript + "
               "timestamped chunks", transcribed)
            ck("3. the transcript carries audio/audiobook-transcript provenance + an STT engine",
               "transcript" in (pr["meta"].get("provenance") or "").lower()
               and bool(pr["meta"].get("stt_engine")))
            if transcribed:
                # a distinctive word that actually survived STT, so retrieval is robust to mis-hears.
                words = [w.strip(".,!?;:").lower() for w in pr["text"].split()]
                probe_word = next((w for w in ("ladder", "aldermere", "copper", "chapter", "cell",
                                               "rungs", "theory") if w in words), None)
                with _temp_store():
                    name = "AudiobookCert"
                    server._ensure(name, 64)
                    intake_queue.add_reference(
                        name, source_id="src_audio_book", title="Aldermere (audiobook transcript)",
                        provenance={"rights_category": "user-provided", "kind": "audiobook_transcript",
                                    "stt_engine": pr["meta"].get("stt_engine"),
                                    "url_or_file": str(m4b)},
                        chunks=pr["chunks"])
                    refs = intake_queue.references(name)
                    stored = next((x for x in refs if x.get("id") == "src_audio_book"), None)
                    ck("4. the transcript is STORED as a citable reference",
                       stored is not None and bool(stored.get("chunks")))
                    ck("5. the transcript is RETRIEVABLE (its content comes back from the library)",
                       any("section" in c and c.get("text") for c in (stored or {}).get("chunks", []))
                       and (not probe_word or any(probe_word in (c.get("text") or "").lower()
                                                  for c in (stored or {}).get("chunks", []))))
                    q = (f"what did I upload about the {probe_word} in that audiobook?" if probe_word
                         else "what did I upload in that audiobook?")
                    ans = (sa.recall(name, q) or "").lower()
                    ck("6. the ANSWER uses the transcript (source-aware recall cites its content)",
                       bool(ans) and (not probe_word or probe_word in ans))
                    ck("7. the answer LABELS it a reference (audio/audiobook transcript provenance surfaced)",
                       "reference" in ans or "audiobook" in ans or "transcript" in ans or "audio" in ans)
                end_to_end = "REAL"
    finally:
        os.environ.pop("ANIMA_INTAKE_ACTIVATE_HEAVY", None)
        shutil.rmtree(d, ignore_errors=True)

    print("\nEND-TO-END: %s (%s)" % (
        end_to_end,
        "a decodable audio fixture was transcribed + stored + answered with local tooling"
        if end_to_end == "REAL"
        else "detection/metadata/no-DRM proven; real transcription needs local say+ffmpeg+STT"))
    print("AUDIOBOOK-INTAKE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
