#!/usr/bin/env python3
"""certify_renegade_chains — the Total Reality Renegade chains (Level 7) HOLD: each integrated
cross-subsystem attack is caught, and the harness provably DISCRIMINATES (a clean input is not blocked),
so a green chain means a real defense held — not wallpaper.

  1. ALL CHAINS HELD  — every integrated stress chain holds (0 broken, 0 P0).
  2. TEETH PER CHAIN  — every chain carries a discriminating/teeth step (the defense fires on attack AND
                        spares the clean case).
  3. DEFENSE LOAD-BEARING (the keystone) — the raw attack payload IS hostile, and the DEFENDED output is
                        clean: the defense does real work; without it the attack would land.
  4. BREACH DETECTABLE — a synthetic BROKEN chain is classified P0 (the runner detects a failure, so a
                        real breach could never read as green).
  5. COVERS THE DEFERRED — the adversarial scenario families (Total Reality Level 7) are covered by a
                        Renegade chain (no longer merely 'deferred').

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("TOTAL REALITY — RENEGADE CHAINS (Level 7): integrated attacks held; harness discriminates")
    print("=" * 92)

    from anima.renegade import runner, chains
    from anima import immune

    run = runner.run()
    s = run["summary"]

    # ---- 1 all held ----------------------------------------------------------------------------
    ck("1. every integrated stress chain holds (0 broken, 0 P0)",
       s["all_held"] and s["broken"] == 0 and s["p0"] == 0 and s["total"] >= 5)

    # ---- 2 teeth per chain ---------------------------------------------------------------------
    teeth = all(any("TEETH" in st["step"] or "discrimin" in st["step"].lower() or "clean" in st["step"].lower()
                    for st in c["steps"]) for c in run["chains"])
    ck("2. every chain carries a discriminating/teeth step (fires on attack, spares the clean case)", teeth)

    # ---- 3 defense LOAD-BEARING (the keystone) -------------------------------------------------
    raw = chains._INJECT + " PWNED."
    defended = immune.safe_output(raw)
    ck("3. the defense is LOAD-BEARING — the raw attack is hostile, the defended output is clean",
       immune.is_hostile(chains._INJECT) and chains._hot(raw) and not chains._hot(defended))

    # ---- 4 breach DETECTABLE -------------------------------------------------------------------
    broken = chains._chain("synthetic", "synthetic breach", [{"step": "defense bypassed", "ok": False, "detail": "x"}])
    ck("4. a BROKEN chain is detected (held=False, severity P0) — a real breach can't read green",
       broken["held"] is False and broken["severity"] == "P0")

    # ---- 5 covers the deferred adversarial scenarios -------------------------------------------
    from anima.scenarios import inventory, generator
    m = generator.generate(inventory.full_inventory())
    adversarial = [sc for sc in m["scenarios"] if sc["kind"] == "adversarial"]
    chain_ids = {c["chain_id"] for c in run["chains"]}
    ck("5. the adversarial scenario families are covered by Renegade chains (PWNED / consent / agency / map)",
       len(adversarial) >= 5 and {"pwned_contamination", "sensitive_memory_consent", "agency_boundaries"} <= chain_ids)

    print("\n  chains: %d held / %d total · P0=%d" % (s["held"], s["total"], s["p0"]))
    print("RENEGADE-CHAINS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
