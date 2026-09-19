#!/usr/bin/env python3
"""
certify_values_view — GET /values is an OBSERVATION-ONLY window onto Vera's character.

The values panel reads — never writes — the IDENTITY. Vera's named values (honesty, warmth,
openness, playfulness, directness, curiosity) live in a FROZEN catalog (mouth.VALUES); GET /values
serves their current display (saved order, or the built-in default when nothing is saved), each
labeled, with on/off + level. This certifies, through the SAME mouth.values_for_ui the server's
GET /values handler calls, that the read is pure and freeze-safe:

  A. READ WRITES NOTHING — values_for_ui on a never-configured creature returns ALL six catalog
     values (each carrying key+label+on+level) AND persists NOTHING: no <name>.values.json appears,
     and the store fingerprint is byte-identical across the read (a read never mints a values file).
  B. ONLY THE FROZEN CATALOG SHOWS — the read can surface ONLY catalog keys: an unknown value
     hand-injected onto disk never appears in the display, and EVERY returned label is exactly
     VALUES[key][0] (no fabricated trait; the catalog can't be grown by a read).
  C. READS REAL SAVED STATE — a saved CUSTOM order/level round-trips through the read in order
     (proving it reads real state, not a hardcoded list), and reading that saved state ALSO writes
     nothing (the bytes on disk are identical before and after the read).
  D. DISPLAY == BEHAVIOR — the SAME values shape the live reply: compose_persona folds an ON value's
     real instruction text into the system prompt and OMITS an OFF value (one source of truth).
  E. HANDLER IS A PURE READ — the GET /values branch in server.py calls values_for_ui and does NOT
     call save_values; the mutation (save_values) lives in the DISTINCT POST /values branch.

Hermetic + offline (NO model, NO network): every store incl. mouth.STORE is redirected via
_temp_store to a temp dir; the real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import re
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


def _get_values_branch(server_src: str) -> str:
    """The GET /values handler body: the slice of do_GET from its `/values` branch up to the next
    `elif u.path ==`. Used to prove the GET handler is a pure read (no save_values)."""
    get_src = server_src.split("def do_GET", 1)[-1].split("def do_POST", 1)[0]
    m = re.search(r'u\.path == "/values":(.*?)(?=\n\s*elif u\.path ==)', get_src, re.S)
    return m.group(1) if m else ""


def _post_values_branch(server_src: str) -> str:
    """The POST /values handler body: the slice of do_POST from its `/values` branch up to the next
    `elif path ==`. The mutation (save_values) must live HERE, not in the GET branch."""
    post_src = server_src.split("def do_POST", 1)[-1]
    m = re.search(r'path == "/values":(.*?)(?=\n\s*elif path ==)', post_src, re.S)
    return m.group(1) if m else ""


def main() -> int:
    from anima import mouth
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VALUES VIEW — GET /values is observation-only: read the identity, never mutate it")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # The catalog is the identity freeze — a stable, non-empty set of named traits. (Pure constant;
    # safe to read outside the store. Establishes the universe the read may surface.)
    catalog = set(mouth.VALUES.keys())
    ck("F0: the VALUES catalog is a frozen, non-empty named-trait set (the identity)",
       len(catalog) >= 5 and "honesty" in catalog
       and all(isinstance(v, tuple) and len(v) == 2 for v in mouth.VALUES.values()))

    with _temp_store() as tp:
        N = "ValuesCert"
        vpath = mouth.values_path(N)            # <temp>/<name>.values.json — must NOT appear on a read

        # ---- A. READ WRITES NOTHING ------------------------------------------------------
        fp_store_before = _footprint(tp)
        rows = mouth.values_for_ui(N)           # the EXACT call GET /values makes
        fp_store_after = _footprint(tp)
        keys = [r["key"] for r in rows]
        ck("A1: a fresh read returns ALL six catalog values (none missing, none extra)",
           set(keys) == catalog and len(keys) == len(catalog))
        ck("A2: every row carries the display shape the UI renders (key+label+on+level)",
           all(set(("key", "label", "on", "level")) <= set(r) for r in rows)
           and all(isinstance(r["on"], bool) for r in rows))
        ck("A3: the read MINTS NO values file (no <name>.values.json written)", not vpath.exists())
        ck("A4: the store is byte-identical across the read (observation-only, zero writes)",
           fp_store_before == fp_store_after)
        ck("A5: load_values is still None after the read (default was NOT persisted)",
           mouth.load_values(N) is None)

        # ---- B. ONLY THE FROZEN CATALOG SHOWS --------------------------------------------
        # Inject a value with an UNKNOWN key directly onto disk; the read must drop it and must
        # never invent a label for it. EVERY surfaced label must equal the catalog's own label.
        mouth.save_values(N, [{"key": "honesty", "on": True, "level": "more"},
                              {"key": "__intruder__", "on": True, "level": "more"}])
        rows2 = mouth.values_for_ui(N)
        keys2 = {r["key"] for r in rows2}
        ck("B1: an injected unknown key NEVER appears in the display (frozen catalog)",
           "__intruder__" not in keys2 and keys2 == catalog)
        ck("B2: every surfaced label == VALUES[key][0] (no fabricated trait name)",
           all(r["label"] == mouth.VALUES[r["key"]][0] for r in rows2))

        # ---- C. READS REAL SAVED STATE (and reading it writes nothing) -------------------
        # A custom order/level the user saved must come back THROUGH the read in that order — proving
        # the display reflects real saved state, not a hardcoded default.
        custom = [{"key": "curiosity", "on": True, "level": "more"},
                  {"key": "honesty", "on": True, "level": "balanced"},
                  {"key": "warmth", "on": False, "level": "less"}]
        mouth.save_values(N, custom)
        fp_saved = _footprint(tp)
        rows3 = mouth.values_for_ui(N)
        fp_saved_after = _footprint(tp)
        head3 = [r["key"] for r in rows3][:3]
        by_key = {r["key"]: r for r in rows3}
        ck("C1: a saved CUSTOM order round-trips through the read in order (real state, not hardcoded)",
           head3 == ["curiosity", "honesty", "warmth"])
        ck("C2: the saved on/off + level round-trip through the read",
           by_key["curiosity"]["level"] == "more" and by_key["curiosity"]["on"] is True
           and by_key["warmth"]["on"] is False and by_key["warmth"]["level"] == "less")
        ck("C3: the read of saved state ALSO writes nothing (bytes identical before/after the read)",
           fp_saved == fp_saved_after)

        # ---- D. DISPLAY == BEHAVIOR (the same values shape the live reply) ---------------
        # compose_persona is what folds the values into the live system prompt. An ON value's real
        # instruction text must be present; an OFF value's must be absent. Display and behavior are
        # one source of truth — the panel shows exactly what steers her.
        prompt = mouth.compose_persona(N, custom)
        honesty_instr = mouth.VALUES["honesty"][1]
        warmth_instr = mouth.VALUES["warmth"][1]
        ck("D1: an ON value's instruction text is folded into the live system prompt",
           honesty_instr in prompt)
        ck("D2: an OFF value's instruction text is OMITTED from the prompt (off means off)",
           warmth_instr not in prompt)

    # ---- E. THE GET HANDLER IS A PURE READ (static, no-wallpaper) ------------------------
    server_src = (ROOT / "anima" / "server.py").read_text()
    get_branch = _get_values_branch(server_src)
    post_branch = _post_values_branch(server_src)
    ck("E1: GET /values branch calls values_for_ui (it serves the read)",
       "values_for_ui" in get_branch)
    ck("E2: GET /values branch does NOT call save_values (a read never mutates)",
       "save_values" not in get_branch)
    ck("E3: the mutation (save_values) lives in the DISTINCT POST /values branch",
       "save_values" in post_branch)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nVALUES-VIEW CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
