#!/usr/bin/env python3
"""run_total_scenario_matrix — execute the Total Scenario Matrix with the Rover and write the evidence
bundle (Level 2). Generates the matrix from the real product, runs the synthetic user against the real
backing paths, and persists reports/total_reality/<run_id>/.

    python3 scripts/run_total_scenario_matrix.py [--persona founder]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    persona = "founder"
    if "--persona" in sys.argv:
        try:
            persona = sys.argv[sys.argv.index("--persona") + 1]
        except Exception:
            pass

    from anima.scenarios import inventory, generator
    from anima.rover import runner
    from anima.observation_harness import bundle

    matrix = generator.generate(inventory.full_inventory())
    run = runner.run(matrix, persona=persona)
    run_id = "trt_%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), persona)
    d = bundle.write_bundle(run_id, run, matrix, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    v = bundle.verify_bundle(run_id, matrix)

    s = run["summary"]
    print("TOTAL REALITY RUN %s (persona=%s)" % (run_id, persona))
    print("  scenarios=%d  executed=%d (pass=%d fail=%d)  blocked=%d  deferred=%d  P0=%d P1=%d"
          % (s["total"], s["executed"], s["pass"], s["fail"], s["blocked"], s["deferred"], s["p0"], s["p1"]))
    print("  evidence bundle: %s  (complete=%s, recorded=%d/%d)"
          % (d.relative_to(ROOT), v["complete"], v["recorded"], v["total"]))
    # exit non-zero on any P0/P1 (a real failure blocks)
    return 0 if (s["p0"] == 0 and s["p1"] == 0 and v["complete"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
