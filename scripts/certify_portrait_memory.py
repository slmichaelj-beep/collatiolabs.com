#!/usr/bin/env python3
"""
certify_portrait_memory — the transient turn log + the Portrait, and the privacy posture that
WITHHOLDS her personal memory of you the instant a cloud brain is active (same as the inbox).

Vera keeps two on-device memories of the person: a SHORT-LIVED working log of recent turns (so she
remembers what was just said this session) and a durable distilled PORTRAIT (a small profile she
injects whole into every reply so she simply knows you). This certifies that contract through the
SAME functions the mouth's respond() and the route privacy guard call:

  A. THE TRANSIENT LOG IS REAL + RETRIEVABLE + DURABLE. portrait.log_turn appends one exchange to the
     working log (name.chat.jsonl); portrait.read_transcript reads it back VERBATIM (the user line AND
     Vera's reply), a second turn is ORDERED after the first, and a FRESH read_transcript re-read from
     disk still returns both — the recent-turn context survives reload (it is on disk, not in memory).
  B. THE PORTRAIT ROUND-TRIPS. portrait.save/load round-trips the durable Portrait text — the prose the
     mouth loads as `mem` and injects whole.
  C. WITHHELD UNDER A CLOUD BRAIN (the inbox posture). We replay the EXACT mouth.respond seam —
     `mem = portrait.load(name)` then `if cloud.is_cloud(): mem = ""` — with the production functions:
     on a LOCAL brain `mem` CARRIES the Portrait; after save_cfg('openai', model, key) flips is_cloud()
     True the SAME seam BLANKS `mem` to "" (her concentrated PII never rides the cloud stream), the same
     posture as route.route(a reminders read) returning the honest PAUSED note. A never-keyed cloud
     provider stays local (is_cloud False) and does NOT blank — the guard can't be tricked into
     withholding a truly-local session.
  D. ISOLATION + ANIMA LAW 001. The transient log path (name.chat.jsonl) is DISTINCT from the durable
     Portrait path (name.portrait.md); clear_log APPENDS the raw turns to the append-only chat archive
     (name.chat.archive.jsonl) BEFORE unlinking the log, and the archive survives the clear — the
     working log is cleared but the source is never destroyed (Compressed > Forgotten).

Hermetic + offline (no model, no network): portrait.STORE is redirected by _temp_store and cloud.STORE
is redirected to the same temp dir by this cert; the real .anima is fingerprinted before/after and
asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint

_FAKE_KEY = "sk-FAKE-DUMMY-portrait-cert-not-a-real-key-000"


def _mouth_mem(portrait, cloud, name):
    """Replay the EXACT mouth.respond() personal-memory seam (anima/mouth.py): load the Portrait as the
    injected `mem`, then the cloud privacy gate blanks the whole bundle the instant a cloud brain is
    active. Deterministic, model-free — the SAME two production calls the mouth makes before it ever
    assembles the prompt. Returns the `mem` string that WOULD be injected into this turn's prompt."""
    mem = portrait.load(name)                # lasting memory (prose USER profile), injected whole
    if cloud.is_cloud():                     # her personal memory of you is concentrated PII —
        mem = ""                             # never send it to a cloud brain (mouth.py L866-869)
    return mem


def main() -> int:
    from anima import portrait, cloud, route
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PORTRAIT MEMORY — the transient turn log + the Portrait, withheld under a cloud brain")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        saved_cloud_store = getattr(cloud, "STORE", None)
        cloud.STORE = tp                                  # redirect brain.json into the temp dir
        try:
            N = "PortraitCert"

            # ---- A. THE TRANSIENT LOG IS REAL + RETRIEVABLE + DURABLE --------------------
            ck("A0: a fresh creature has an EMPTY transient log (nothing logged yet)",
               portrait.read_transcript(N) == "")
            portrait.log_turn(N, "my sister Mara is moving to Denver in March", "that's a big move")
            t1 = portrait.read_transcript(N)
            ck("A1: a logged turn is retrievable — the user line is read back verbatim",
               "my sister Mara is moving to Denver in March" in t1)
            ck("A2: the logged turn carries Vera's reply too (the full exchange)",
               "that's a big move" in t1)
            portrait.log_turn(N, "and my birthday is September 14", "noted — September 14")
            t2 = portrait.read_transcript(N)
            ck("A3: a second turn is ORDERED after the first (recent-turn context, in sequence)",
               "Mara is moving" in t2 and "September 14" in t2
               and t2.index("Mara is moving") < t2.index("September 14"))
            # DURABLE: re-read fresh from disk — the recent-turn context is on disk, not in memory.
            fresh = portrait.read_transcript(N)
            ck("A4: a FRESH read_transcript (re-read from disk) still returns both turns (durable)",
               "Mara is moving" in fresh and "September 14" in fresh)
            ck("A5: the log file is the transient working log name.chat.jsonl (on disk)",
               portrait.log_path(N).exists() and portrait.log_path(N).name == f"{N}.chat.jsonl")

            # ---- B. THE PORTRAIT ROUND-TRIPS (the durable injected memory) ---------------
            PORT = ("- close companion to the user\n- sister Mara is moving to Denver in March\n"
                    "- the user's birthday is September 14")
            portrait.save(N, PORT)
            ck("B1: portrait.save/load round-trips the durable Portrait text (injected whole)",
               portrait.load(N) == PORT)
            ck("B2: the Portrait file is the durable name.portrait.md (NOT the transient log)",
               portrait.portrait_path(N).exists()
               and portrait.portrait_path(N).name == f"{N}.portrait.md")

            # ---- C. WITHHELD UNDER A CLOUD BRAIN — the inbox posture ---------------------
            cloud.save_cfg("local", "", "")               # ensure we start on the LOCAL brain
            ck("C0: brain is LOCAL by default (is_cloud False)", cloud.is_cloud() is False)
            mem_local = _mouth_mem(portrait, cloud, N)
            ck("C1: on a LOCAL brain the mouth's `mem` CARRIES the Portrait (she knows you)",
               mem_local == PORT and "September 14" in mem_local)
            # flip to a real cloud brain WITH a key — the privacy gate must engage
            cloud.save_cfg("openai", "gpt-4o-mini", _FAKE_KEY, budget=1.0)
            ck("C2: saving a cloud provider WITH a key flips is_cloud() True", cloud.is_cloud() is True)
            mem_cloud = _mouth_mem(portrait, cloud, N)
            ck("C3: PRIVACY — under a cloud brain the Portrait is BLANKED to '' (withheld, not streamed)",
               mem_cloud == "")
            ck("C4: the Portrait on disk is UNTOUCHED by the blanking (only the egressed copy is withheld)",
               portrait.load(N) == PORT)
            # the inbox mirror: route.route PAUSES a private read under the SAME cloud gate
            r = route.route(N, "what are my reminders?")
            ck("C5: same posture as the inbox — route.route(a private read) is PAUSED under the cloud brain",
               "PAUSED" in (r or {}).get("note", ""))
            # a never-keyed cloud provider stays local — the guard can't be tricked into withholding
            cloud.save_cfg("deepseek", "deepseek-chat", "")
            ck("C6: a never-keyed cloud provider stays LOCAL (is_cloud False) — no false withhold",
               cloud.is_cloud() is False)
            ck("C7: with the truly-local session the Portrait is injected again (mem not blanked)",
               _mouth_mem(portrait, cloud, N) == PORT)
            cloud.save_cfg("local", "", "")               # leave the brain local

            # ---- D. ISOLATION + ANIMA LAW 001 (archive-then-clear) -----------------------
            ck("D1: the transient log path and the durable Portrait path are DISTINCT files",
               portrait.log_path(N) != portrait.portrait_path(N)
               and portrait.log_path(N).name.endswith(".chat.jsonl")
               and portrait.portrait_path(N).name.endswith(".portrait.md"))
            archive = portrait._archive_path(N)
            ck("D2: precondition — no chat archive exists before the first clear", not archive.exists())
            portrait.clear_log(N)
            ck("D3: clear_log CLEARS the transient working log (working set freed)",
               not portrait.log_path(N).exists() and portrait.read_transcript(N) == "")
            ck("D4: LAW 001 — clear_log first APPENDED the raw turns to the append-only chat archive",
               archive.exists() and archive.stat().st_size > 0)
            arc = archive.read_text()
            ck("D5: the archived source still holds both turns (Compressed > Forgotten — nothing destroyed)",
               "Mara is moving" in arc and "September 14" in arc)
            ck("D6: the durable Portrait survives the log clear (the distilled memory is kept)",
               portrait.load(N) == PORT)
        finally:
            if saved_cloud_store is not None:
                cloud.STORE = saved_cloud_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPORTRAIT-MEMORY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
