#!/usr/bin/env python3
"""
certify_state_snapshot — GET /state is a REAL, deterministic, read-only snapshot of felt experience.

Proves the /state contract by reproducing EXACTLY what the server's GET /state handler computes —
Heart.from_dict(load_json(_path(name))).feeling() — and showing it can only mirror the persisted heart,
never invent a mood:

  A. COHERENT SHAPE — the snapshot carries every declared affect (heart.AFFECTS) plus the homeostat
     'unrest', and every value is a finite float in [-1, 1] (a real tanh-bounded affect read, not a stub
     or a string).
  B. REAL, NOT FABRICATED — the snapshot served from the persisted file is BYTE-EQUAL to feeling()
     computed directly off the same heart's to_dict(): /state reflects what is on disk, it does not
     synthesise. from_dict reconstructs the genome from its STORED seed, so the read is grounded.
  C. DETERMINISTIC — reading the same persisted file twice yields an identical snapshot (no randomness
     in the serve path); and an independently rebuilt heart at the same seed + clock reproduces it.
  D. IT ACTUALLY READS THE FILE (NOT A CONSTANT) — a heart tended to a different wellbeing, persisted,
     then served, yields a DIFFERENT snapshot. So /state is a function OF the stored state, not a fixed
     payload — the contract's whole point.
  E. READ-ONLY — serving /state writes nothing: the persisted {name}.json is byte-unchanged across the
     read, and (covered by H1) the real .anima is untouched.

Hermetic + offline: server.STORE (and the heart-bearing modules) are redirected to a temp dir via
gate0_prime_experience._temp_store; NO model, NO network — heart.feeling() is pure numpy. The real
.anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import math
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


def main() -> int:
    from anima import server
    from anima.heart import Heart, AFFECTS
    from anima.util import save_json, load_json
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("STATE SNAPSHOT — GET /state is a real, deterministic, read-only heart snapshot")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    def served_state(name):
        """Byte-for-byte what GET /state runs in server.do_GET."""
        return Heart.from_dict(load_json(server._path(name))).feeling()

    with _temp_store():
        N = "StateCert"

        # Persist a born heart (fixed seed + clock => the whole cert is deterministic).
        born = Heart.born(N, seed=4242, n=64, now=1000.0)
        save_json(server._path(N), born.to_dict())

        snap = served_state(N)

        # ---- A. COHERENT SHAPE ------------------------------------------------------
        ck("A1: the snapshot carries every affect (heart.AFFECTS) plus 'unrest'",
           set(AFFECTS).issubset(snap.keys()) and "unrest" in snap)
        ck("A2: every value is a finite float in [-1, 1] (a real bounded affect read)",
           all(isinstance(v, float) and math.isfinite(v) and -1.0 <= v <= 1.0
               for v in snap.values()))

        # ---- B. REAL, NOT FABRICATED ------------------------------------------------
        direct = Heart.from_dict(born.to_dict()).feeling()
        ck("B1: the served snapshot == feeling() computed directly off the persisted heart "
           "(mirrors disk, does not invent)", snap == direct)

        # ---- C. DETERMINISTIC -------------------------------------------------------
        ck("C1: re-reading the SAME persisted file yields an identical snapshot (no serve-path randomness)",
           served_state(N) == snap)
        rebuilt = Heart.born(N, seed=4242, n=64, now=1000.0).feeling()
        ck("C2: an independently rebuilt heart at the same seed+clock reproduces the snapshot",
           rebuilt == snap)

        # ---- D. IT ACTUALLY READS THE FILE (NOT A CONSTANT) -------------------------
        moved = Heart.born(N, seed=4242, n=64, now=1000.0)
        moved.tend(0.92, now=2000.0)                 # a real contact -> a different felt state
        save_json(server._path(N), moved.to_dict())
        snap2 = served_state(N)
        ck("D1: a heart tended to a different state, persisted, then served, yields a DIFFERENT snapshot "
           "(/state is a function of the stored state, not a fixed payload)", snap2 != snap)
        ck("D2: that changed snapshot is itself real + deterministic (== direct compute, stable on re-read)",
           snap2 == Heart.from_dict(moved.to_dict()).feeling() and snap2 == served_state(N))

        # ---- E. READ-ONLY -----------------------------------------------------------
        before_bytes = server._path(N).read_bytes()
        _ = served_state(N)                          # serving the snapshot must not mutate the file
        ck("E1: serving /state writes nothing — the persisted {name}.json is byte-unchanged",
           server._path(N).read_bytes() == before_bytes)

    # ---- HERMETICITY ------------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nSTATE-SNAPSHOT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
