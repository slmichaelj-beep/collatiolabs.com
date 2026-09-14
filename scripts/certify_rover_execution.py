#!/usr/bin/env python3
"""certify_rover_execution — the Total Reality Rover actually EXECUTES the Level-2 scenario matrix against
the real server backing paths, classifies every scenario, and silently skips nothing.

  1. EVERY SCENARIO ACCOUNTED — every scenario in the matrix gets a result (pass/fail/blocked/deferred);
                                none is dropped. (the directive's 'untested critical paths: 0')
  2. REAL EXECUTION  — the Level-2 surface + control scenarios are actually run against the REAL server
                       data functions (>= 60 executed, not delegated).
  3. NO P0/P1 OPEN   — the executed scenarios surface no release-blocking failure.
  4. EXECUTION BITES — the keystone: a scenario pointing at a NON-EXISTENT surface is classified FAIL.
                       A runner that can't fail is wallpaper.
  5. HONEST DELEGATION — blocked/deferred scenarios name where they are really covered (gate / Rover /
                       Renegade), never a fake pass.

Hermetic (in-process against the real server module). Exit 0 == CERTIFIED.
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

    print("TOTAL REALITY — ROVER EXECUTION (Level 2): every scenario executed or honestly delegated")
    print("=" * 92)

    from anima.scenarios import inventory, generator, schema
    from anima.rover import runner

    matrix = generator.generate(inventory.full_inventory())
    run = runner.run(matrix, persona="founder")
    res = run["results"]
    s = run["summary"]
    by_id = {r["scenario_id"]: r for r in res}

    # ---- 1 every scenario accounted ------------------------------------------------------------
    want = {sc["scenario_id"] for sc in matrix["scenarios"]}
    ck("1. every scenario gets a result (none silently dropped)",
       set(by_id) == want and all(r["status"] in ("pass", "fail", "blocked", "deferred") for r in res))

    # ---- 2 real execution ----------------------------------------------------------------------
    ck("2. the Level-2 surface + control scenarios are actually executed (>=60 run against real paths)",
       s["executed"] >= 60 and all(r["detail"] for r in res if r["status"] in ("pass", "fail")))

    # ---- 3 no P0/P1 ----------------------------------------------------------------------------
    ck("3. the executed scenarios surface no P0/P1 release blocker",
       s["p0"] == 0 and s["p1"] == 0 and s["fail"] == 0)

    # ---- 4 execution BITES (the keystone) ------------------------------------------------------
    bad = {"scenarios": [schema.scenario("trt_surface___ghost__", "Ghost surface", "__ghost__",
                                          user_intent="view_living_map", expected_outcome="page_loads",
                                          level=2, family="founder_admin")],
           "counts": {"total": 1}}
    bad_run = runner.run(bad, persona="founder")
    ck("4. execution BITES — a scenario on a non-existent surface is classified FAIL",
       bad_run["results"][0]["status"] == "fail" and bad_run["summary"]["fail"] == 1)

    # ---- 5 honest delegation -------------------------------------------------------------------
    delegated = [r for r in res if r["status"] in ("blocked", "deferred")]
    ck("5. blocked/deferred scenarios name where they are really covered (no fake pass)",
       bool(delegated) and all(any(w in r["detail"] for w in ("delegated", "deferred", "covered"))
                               for r in delegated))

    print("\n  executed=%d pass=%d fail=%d · blocked=%d deferred=%d · P0=%d P1=%d"
          % (s["executed"], s["pass"], s["fail"], s["blocked"], s["deferred"], s["p0"], s["p1"]))
    print("ROVER-EXECUTION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
