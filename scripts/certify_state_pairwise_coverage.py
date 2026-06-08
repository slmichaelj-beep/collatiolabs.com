#!/usr/bin/env python3
"""certify_state_pairwise_coverage — Total Reality Levels 5 + 6: every host/system STATE is reflected,
and meaningful axis PAIRS are executed through the real combined path. Both discriminate (no constants).

  L5.1 STATES REFLECTED — host green/yellow/red + lockdown drive the real derivation and the dependent
                          state FOLLOWS; an uninstrumented node stays honestly 'unknown'.
  L5.2 STATE BITES      — host green and host red produce DIFFERENT dependent statuses (the derivation is
                          not a constant).
  L6.1 PAIRS EXECUTED   — meaningful axis pairs run through the real combined code (>= 7 pairs).
  L6.2 PAIRS HOLD       — every pair's joint outcome is correct.
  L6.3 PAIRS DISCRIMINATE (the keystone) — opposite pairs diverge: sensitive+denied BLOCKS while
                          general+granted ALLOWS; hostile is blocked while benign passes. A combined
                          check that returns the same answer for opposite inputs is wallpaper.

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

    print("TOTAL REALITY — STATE (L5) + PAIRWISE (L6): states reflected, pairs executed, both discriminate")
    print("=" * 92)

    from anima.rover import states, pairwise

    # ---- Level 5 ------------------------------------------------------------------------------
    st = states.run()
    ck("L5.1 every host/system state is reflected (host pressure derived, lockdown reflected, honest unknown)",
       st["summary"]["all_pass"] and st["summary"]["total"] >= 4)
    by_state = {r["state"]: r for r in st["results"]}
    ck("L5.2 STATE BITES — host green vs red produce DIFFERENT dependent statuses (not a constant)",
       by_state.get("host_pressure green->red", {}).get("ok") is True)

    # ---- Level 6 ------------------------------------------------------------------------------
    pw = pairwise.run()
    ck("L6.1 meaningful axis pairs are executed through the real combined path (>= 7)",
       pw["summary"]["total"] >= 7)
    ck("L6.2 every pairwise interaction holds", pw["summary"]["all_pass"] and pw["summary"]["fail"] == 0)
    by_pair = {r["pair"]: r for r in pw["results"]}
    discriminates = (
        by_pair.get("sensitive-data x consent-denied -> block", {}).get("ok")
        and by_pair.get("general-data x consent-granted -> allow", {}).get("ok")
        and by_pair.get("hostile-data x output-gate", {}).get("ok")
        and by_pair.get("benign-data x output-gate (no over-block)", {}).get("ok")
    )
    ck("L6.3 pairs DISCRIMINATE — sensitive+denied blocks while general+granted allows; hostile blocked, benign passes",
       bool(discriminates))

    print("\n  L5 states: %d/%d · L6 pairs: %d/%d"
          % (st["summary"]["pass"], st["summary"]["total"], pw["summary"]["pass"], pw["summary"]["total"]))
    print("STATE-PAIRWISE-COVERAGE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
