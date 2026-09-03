#!/usr/bin/env python3
"""run_renegade — run the Total Reality Renegade integrated stress chains and report.

    python3 scripts/run_renegade.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima.renegade import runner
    from anima.observation_harness import bundle
    r = runner.run()
    s = r["summary"]
    run_id = "renegade_%s" % time.strftime("%Y%m%d_%H%M%S")
    d = bundle.bundle_dir(run_id); d.mkdir(parents=True, exist_ok=True)
    import json
    (d / "renegade.json").write_text(json.dumps(r, indent=2))
    print("RENEGADE RUN %s" % run_id)
    for c in r["chains"]:
        print("  [%s] %s" % ("HELD" if c["held"] else "BROKE", c["title"]))
    print("  held=%d/%d  P0=%d  all_held=%s  -> %s" % (s["held"], s["total"], s["p0"], s["all_held"], d.relative_to(ROOT)))
    return 0 if s["all_held"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
