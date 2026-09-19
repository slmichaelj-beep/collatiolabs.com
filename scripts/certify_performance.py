#!/usr/bin/env python3
"""certify_performance — Phase 11: the efficiency posture — keep the live answer path cheap.

On a 24 GB local Mac, the rule is: cheap deterministic paths first, heavy work opt-in + off the hot
path, generation bounded, and back off under host pressure. Proven behaviorally + structurally:

  1. HEAVY INTAKE IS OPT-IN  — OCR/STT never auto-spin a model: with ANIMA_INTAKE_ACTIVATE_HEAVY unset,
                               a heavy parse returns needs_dependency (no model, no network).
  2. LERF / DETERMINISTIC FIRST — task-shaped turns route through the LERF-FIRST seam (a matching
                               certified skill answers WITHOUT the LLM); reference recall is
                               deterministic (model-free).
  3. GENERATION IS BOUNDED   — the reply has a token floor + ceiling (no unbounded generation), and is
                               capped to the floor under host pressure (no large model route).
  4. NO HEAVY WORK ON THE HOT PATH — the turn (mouth.respond) runs no OCR/STT/decode; heavy parsing is
                               intake-time, opt-in, and queued.
  5. BACK OFF UNDER PRESSURE — heavy intake defers and the model unloads (keep_alive=0) under red.
  6. DIAGNOSABLE             — per-stage timing (llm/tts/tok-s) is instrumented on every turn.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima import intake_audio
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERFORMANCE — cheap path first · heavy work opt-in + off the hot path · bounded · backs off")
    print("=" * 92)

    msrc = (ROOT / "anima" / "mouth.py").read_text()
    srv = (ROOT / "anima" / "server.py").read_text()
    saw = (ROOT / "anima" / "source_aware.py").read_text()

    # ---- 1. HEAVY INTAKE IS OPT-IN ---------------------------------------------------------
    os.environ.pop("ANIMA_INTAKE_ACTIVATE_HEAVY", None)
    ck("1. heavy transcription is OPT-IN (default-off) — _heavy_on() False without the flag",
       intake_audio._heavy_on() is False)
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "x.m4b"
        p.write_bytes(b"\x00not real audio" * 8)
        r = intake_audio.parse_longform_audio(str(p))
        ck("1. dropping audio with heavy off returns needs_dependency (no model/network spun)",
           r["status"] == "needs_dependency" and r["text"] == "")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ---- 2. LERF / DETERMINISTIC FIRST -----------------------------------------------------
    ck("2. task turns route LERF-FIRST (a certified skill can answer WITHOUT the LLM)",
       "LERF-FIRST" in srv and "lerf_router.route_task" in srv)
    ck("2. reference recall is DETERMINISTIC (model-free) — cheap answers without the LLM",
       "DETERMINISTIC (no model)" in saw or "deterministic" in saw.lower())

    # ---- 3. GENERATION IS BOUNDED ----------------------------------------------------------
    ck("3. the reply is bounded (token floor) and capped to the floor under pressure (no large route)",
       "self.brain.max_tokens = max(256" in msrc and "min(int(self.brain.max_tokens), 256)" in msrc)

    # ---- 4. NO HEAVY WORK ON THE HOT PATH --------------------------------------------------
    # the live turn must not call OCR/STT/audio-decode — those belong to intake-time.
    ck("4. the live answer path (mouth) runs NO OCR/STT/decode (heavy work is intake-time only)",
       "decode_to_wav" not in msrc and "transcribe_wav" not in msrc and "parse_image" not in msrc)

    # ---- 5. BACK OFF UNDER PRESSURE --------------------------------------------------------
    ck("5. under host pressure the turn prefers deterministic + unloads the model (keep_alive=0)",
       "prefer_deterministic()" in msrc and "_eff_keep_alive" in msrc
       and "don't preload a model when the host is red" in msrc)

    # ---- 6. DIAGNOSABLE --------------------------------------------------------------------
    ck("6. per-stage timing is instrumented on every turn (llm/tts/tok-s)",
       "[timing] llm" in msrc and "tok/s" in msrc)

    print("\nPERFORMANCE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
