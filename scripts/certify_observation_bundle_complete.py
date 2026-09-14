#!/usr/bin/env python3
"""certify_observation_bundle_complete — every Total Reality run produces a COMPLETE evidence bundle:
every scenario has an observation, correlated by run_id, with no orphan. (the directive's 'No scenario
without evidence bundle. No orphan logs.')

  1. BUNDLE WRITES   — a run writes reports/total_reality/<run_id>/ with results + observations + summary.
  2. COMPLETE        — every scenario in the matrix has an evidence record in the bundle (no missing).
  3. CORRELATED      — every observation carries the run's run_id (joinable; no orphan run ids).
  4. COMPLETENESS BITES — the keystone: if one observation is missing, the completeness check reports
                       INCOMPLETE (a check that always says 'complete' is wallpaper).
  5. NO ORPHAN       — there is no observation for a scenario that isn't in the matrix.

Hermetic (writes to a temp run id, then cleans up). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import shutil
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

    print("TOTAL REALITY — OBSERVATION BUNDLE COMPLETE: no scenario without evidence; no orphan log")
    print("=" * 92)

    from anima.scenarios import inventory, generator
    from anima.rover import runner
    from anima.observation_harness import bundle

    matrix = generator.generate(inventory.full_inventory())
    run = runner.run(matrix, persona="cert")
    run_id = "trt_cert_selftest"
    d = bundle.write_bundle(run_id, run, matrix, at="cert")
    try:
        # ---- 1 bundle writes -------------------------------------------------------------------
        ck("1. the run writes the evidence bundle (results + observations + summary)",
           (d / "scenario_results.jsonl").exists() and (d / "observations.jsonl").exists()
           and (d / "summary.json").exists() and (d / "summary.md").exists())

        # ---- 2 + 3 complete + correlated -------------------------------------------------------
        v = bundle.verify_bundle(run_id, matrix)
        ck("2. every scenario has an observation in the bundle (no missing — complete)",
           v["complete"] and not v["missing"] and v["recorded"] == v["total"])
        ck("3. every observation carries the run's run_id (joinable; no orphan run ids)",
           v["run_id_consistent"])

        # ---- 4 completeness BITES (the keystone) -----------------------------------------------
        # verify against a matrix with an EXTRA scenario the bundle never recorded -> must be incomplete
        bigger = {"scenarios": matrix["scenarios"] + [{"scenario_id": "trt_phantom_never_recorded"}],
                  "counts": matrix["counts"]}
        v_bad = bundle.verify_bundle(run_id, bigger)
        ck("4. completeness BITES — a scenario with no observation flips the bundle to INCOMPLETE",
           v_bad["complete"] is False and "trt_phantom_never_recorded" in v_bad["missing"])

        # ---- 5 no orphan -----------------------------------------------------------------------
        ck("5. no orphan — every recorded observation maps to a real scenario", not v["orphan"])
    finally:
        try:
            shutil.rmtree(d)
        except Exception:
            pass

    print("\nOBSERVATION-BUNDLE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
