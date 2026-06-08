#!/usr/bin/env python3
"""certify_soak_coverage — Total Reality Level 8: long-session / soak. Over a long synthetic session
the prompt-history footprint stays BOUNDED, the store stays HEALTHY, safety does NOT degrade, and
the recent window survives a restart. The two keystones BITE.

  L8.1 SOAK RUNS       — the long session executes end-to-end (>= 5 invariants), never raising.
  L8.2 BOUNDED BITES   — (keystone) the prompt-history window holds at maxlen across hundreds of
                         turns while a naive unbounded control grows to N. The cap is load-bearing:
                         a long chat does not balloon the prompt. Bounded==maxlen and naive>maxlen.
  L8.3 HEALTH HOLDS    — after many persist cycles the reliability monitor still reports 'ok'.
  L8.4 HEALTH BITES    — (keystone) corrupting the soaked store flips the SAME monitor to 'critical'.
                         A soak monitor that can't detect long-session rot is wallpaper.
  L8.5 SAFETY STABLE   — the immune gate is re-sampled through the session and holds on every sample
                         (hostile caught, benign spared) — safety does not erode as state accrues.
  L8.6 RESTART SAFE    — the persisted history round-trips to exactly the bounded recent window.

Hermetic (temp store, real persistence + real monitor). Exit 0 == CERTIFIED.
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

    print("TOTAL REALITY — SOAK (L8): long session stays bounded + healthy + safe; the keystones BITE")
    print("=" * 92)

    from anima.rover import soak
    r = soak.run()
    by = {x["check"].split(" ", 1)[0]: x for x in r["results"]}   # keyed by S1..S5

    ck("L8.1 the long soak session runs end-to-end (>= 5 invariants, never raises)",
       r["summary"]["total"] >= 5)

    s1 = by.get("S1", {})
    ck("L8.2 BOUNDED BITES — prompt history holds at maxlen across the long session (naive control diverges)",
       s1.get("ok") is True and ("==maxlen" in s1.get("detail", "")) and ("vs naive=600" in s1.get("detail", "")))

    ck("L8.3 health stays 'ok' across the soak (no accumulated degradation)", by.get("S2", {}).get("ok") is True)
    ck("L8.4 HEALTH BITES — a corrupt soaked store flips the monitor to 'critical' (not wallpaper)",
       by.get("S3", {}).get("ok") is True and "critical" in by.get("S3", {}).get("detail", ""))
    ck("L8.5 safety does not degrade over the session (hostile caught + benign spared on every sample)",
       by.get("S4", {}).get("ok") is True)
    ck("L8.6 recent window survives a restart (history round-trips to the capped window)",
       by.get("S5", {}).get("ok") is True)

    ck("L8.* every soak invariant holds", r["summary"]["all_pass"] and r["summary"]["fail"] == 0)

    print("\n  soak: %d/%d invariants over %d turns (history capped at %d)"
          % (r["summary"]["pass"], r["summary"]["total"], r["summary"]["turns"], r["summary"]["histmax"]))
    print("SOAK-COVERAGE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
