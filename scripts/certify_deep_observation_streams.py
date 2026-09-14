#!/usr/bin/env python3
"""certify_deep_observation_streams — Total Reality deep observation streams (directive section 13).

Beyond "every scenario has an observation" (the Level-2 bundle cert), every observation now carries a
DEEP record (kind / level / status / severity — the per-scenario MRI-grade detail) and a host_ref to a
real per-run HOST SNAPSHOT (the host context the run executed under). The deep stream is correlated and
COMPLETE, and the completeness check BITES.

  DO.1 HOST SNAPSHOT     — the run writes a real host_snapshot.json (a true host reading, not empty).
  DO.2 DEEP ON EVERY OBS — every observation carries its deep record (kind/level/status/severity).
  DO.3 HOST-REF ON EVERY — every observation carries a host_ref joining it to the run's host snapshot.
  DO.4 LEVEL-2 INTACT    — the enrichment is additive: the original bundle completeness still holds
                           (every scenario still has a run_id-correlated observation; no orphan).
  DO.5 DEEP BITES        — (keystone) an observation missing its deep record flips deep-completeness to
                           INCOMPLETE. A deep-stream check that always says 'complete' is wallpaper.

Hermetic (writes under a cert run_id, cleaned up). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
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

    print("TOTAL REALITY — DEEP OBSERVATION STREAMS: per-scenario deep record + per-run host snapshot")
    print("=" * 92)

    from anima.scenarios import inventory, generator
    from anima.rover import runner
    from anima.observation_harness import bundle

    matrix = generator.generate(inventory.full_inventory())
    run = runner.run(matrix, persona="deepcert")
    run_id = "trt_deep_selftest"
    d = bundle.write_bundle(run_id, run, matrix, at="deepcert")
    bite_id = "trt_deep_bite"
    db = bundle.bundle_dir(bite_id)
    try:
        ck("DO.1 the run writes a real per-run host snapshot (host_snapshot.json, true reading)",
           (d / "host_snapshot.json").exists()
           and isinstance(json.loads((d / "host_snapshot.json").read_text()).get("host"), dict)
           and bool(json.loads((d / "host_snapshot.json").read_text()).get("host")))

        dv = bundle.verify_deep_observations(run_id)
        ck("DO.2 every observation carries its deep record (kind/level/status/severity)",
           dv["total"] > 0 and dv["with_deep"] == dv["total"])
        ck("DO.3 every observation carries a host_ref joining it to the run's host snapshot",
           dv["with_host_ref"] == dv["total"] and dv["host_snapshot_present"])
        ck("DO.* deep observation streams are COMPLETE (deep + host_ref on every scenario)",
           dv["deep_complete"])

        # DO.4 the original Level-2 completeness is untouched by the enrichment (additive)
        v = bundle.verify_bundle(run_id, matrix)
        ck("DO.4 LEVEL-2 INTACT — the original bundle completeness still holds (no orphan, correlated)",
           v["complete"] and not v["missing"] and not v["orphan"])

        # DO.5 DEEP BITES — a synthetic bundle with ONE observation missing its deep record is INCOMPLETE
        db.mkdir(parents=True, exist_ok=True)
        (db / "host_snapshot.json").write_text(json.dumps({"run_id": bite_id, "host": {"level": "green"}}))
        with (db / "observations.jsonl").open("w", encoding="utf-8") as f:
            f.write(json.dumps({"run_id": bite_id, "scenario_id": "ok1", "host_ref": "host_snapshot.json",
                                "deep": {"kind": "surface", "level": 2, "status": "pass", "severity": None}}) + "\n")
            f.write(json.dumps({"run_id": bite_id, "scenario_id": "bad1", "host_ref": "host_snapshot.json"}) + "\n")  # NO deep
        dv_bad = bundle.verify_deep_observations(bite_id)
        ck("DO.5 DEEP BITES — an observation with no deep record flips deep-completeness to INCOMPLETE",
           dv_bad["deep_complete"] is False and dv_bad["with_deep"] < dv_bad["total"])

        print("\n  deep stream: %d/%d observations carry deep + host_ref · host level=%s"
              % (dv["with_deep"], dv["total"], dv["host_level"]))
    finally:
        for x in (d, db):
            try:
                shutil.rmtree(x)
            except Exception:
                pass

    print("DEEP-OBSERVATION-STREAMS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
