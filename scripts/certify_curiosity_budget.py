#!/usr/bin/env python3
"""
certify_curiosity_budget — the Curiosity Budget cap (minimal/balanced/deep) + the engine that reads it.

The budget governs how OFTEN Vera surfaces a contextual question (FREQUENCY only, never content).
This certifies the DETERMINISTIC contract through the SAME functions the server's /capabilities
endpoint and the Curiosity Engine call:

  A. DEFAULT BALANCED — a fresh creature's caps.curiosity_budget() is "balanced".
  B. DURABLE — caps.set_curiosity_budget("deep") persists "deep" and re-reading FRESH from disk is
     still "deep" (restart-survival); "minimal" likewise round-trips.
  C. INVALID COERCES — an off-list value ("reckless") coerces to the safe "balanced" default and is
     NOT stored as junk — a corrupt store can never silently switch curiosity off or crank it up.
  D. THE ENGINE READS IT — anima.curiosity.read_budget() returns EXACTLY the value set via
     caps.set_curiosity_budget (deep / minimal / balanced), a fresh creature reads "balanced", and
     the engine's deterministic frequency gate honours it: over a fixed gap set, "deep" lets
     through readily and "minimal" far less — proving the budget paces CADENCE, not content.

Hermetic + offline: caps.STORE and curiosity.STORE are both in gate0_prime_experience._temp_store's
redirect set, so .anima/{name}.caps.json lands in a temp dir; the real .anima is fingerprinted
before/after and asserted byte-identical. No model, no network. Exit 0 == CERTIFIED, 1 == FAIL.
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


def main() -> int:
    from anima import caps, curiosity
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CURIOSITY BUDGET — minimal/balanced/deep cap + the engine that paces by it")
    print("=" * 74)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "CuriosityCert"

        # ---- A. DEFAULT BALANCED -----------------------------------------------------
        ck("A1: a fresh creature's curiosity budget defaults to 'balanced'",
           caps.curiosity_budget(N) == "balanced")

        # ---- B. DURABLE --------------------------------------------------------------
        ck("B1: set_curiosity_budget('deep') returns 'deep'",
           caps.set_curiosity_budget(N, "deep") == "deep")
        ck("B2: 'deep' is DURABLE on a fresh read from disk (restart-survival)",
           caps.curiosity_budget(N) == "deep")
        caps.set_curiosity_budget(N, "minimal")
        ck("B3: 'minimal' likewise round-trips durably", caps.curiosity_budget(N) == "minimal")

        # ---- C. INVALID COERCES ------------------------------------------------------
        ck("C1: an invalid value coerces to the safe 'balanced' default (not stored as junk)",
           caps.set_curiosity_budget(N, "reckless") == "balanced")
        ck("C2: after the coercion, the persisted value is exactly 'balanced'",
           caps.curiosity_budget(N) == "balanced")
        # belt-and-braces: a hand-written junk value in the store still reads back safe.
        c = caps.load(N)
        c["curiosity"] = "whatever"
        caps.save(N, c)
        ck("C3: a junk value saved through caps.save() reads back as 'balanced' (fail-safe)",
           caps.curiosity_budget(N) == "balanced")

        # ---- D. THE ENGINE READS IT --------------------------------------------------
        caps.set_curiosity_budget(N, "deep")
        ck("D1: the Curiosity Engine reads the budget -> read_budget == 'deep'",
           curiosity.read_budget(N) == "deep")
        caps.set_curiosity_budget(N, "minimal")
        ck("D2: a changed budget is reflected in the engine -> read_budget == 'minimal'",
           curiosity.read_budget(N) == "minimal")
        ck("D3: a fresh creature reads 'balanced' through the engine",
           curiosity.read_budget("CuriosityFresh") == "balanced")

        # the FREQUENCY invariant: over a fixed set of DISTINCT gaps (each a unique taxonomy slot,
        # so the engine's deterministic per-(name, slot) draw differs gap to gap), deep lets through
        # readily and minimal far less — the budget governs cadence, never content. Uses the engine's
        # own real gate (_budget_allows keys on gap['slot'] via _gap_key); no model, no store dep.
        gaps = [{"kind": curiosity.SUSPECTED, "category": "relationships",
                 "slot": f"relationship:person_{i}", "entity": f"person_{i}",
                 "evidence": {"mentions": 1}} for i in range(80)]
        deep_yes = sum(1 for g in gaps if curiosity._budget_allows(N, g, "deep"))
        bal_yes = sum(1 for g in gaps if curiosity._budget_allows(N, g, "balanced"))
        min_yes = sum(1 for g in gaps if curiosity._budget_allows(N, g, "minimal"))
        ck("D4: 'deep' lets every gap through (rate 1.0 == asks readily)", deep_yes == len(gaps))
        ck("D5: 'minimal' asks far less often than 'deep' over the same distinct-gap set",
           min_yes < deep_yes and min_yes < bal_yes)
        ck("D6: the cadence ordering holds: minimal <= balanced <= deep (frequency, not content)",
           min_yes <= bal_yes <= deep_yes)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nCURIOSITY-BUDGET CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
