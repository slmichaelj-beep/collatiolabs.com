#!/usr/bin/env python3
"""certify_cert_freshness — old green is not current green. A cert/report is stale if a covered source
changed after it was written, or its recorded commit != HEAD. Stale required certs can never be green.

  1. COMPUTES        — freshness.compute() returns per-report staleness on the real reports.
  2. STALE BITES     — (keystone) a covered source NEWER than its report is flagged stale; a report
                       newer than its sources is fresh. The detector actually fires.
  3. COMMIT BITES    — a report recording a commit != HEAD is flagged stale.
  4. REQUIRED GATING — a stale REQUIRED report appears in stale_required (which blocks Diamond).

Hermetic (a temp dir for the teeth). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import os
import sys
import time
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

    print("CERT FRESHNESS — a covered source changing after a cert makes it STALE (no old green)")
    print("=" * 92)

    from anima.verification import freshness
    import tempfile, json

    real = freshness.compute()
    ck("1. freshness computes per-report staleness on the real reports",
       isinstance(real.get("reports"), list) and "any_stale" in real and "stale_required" in real)

    # ---- teeth in a temp dir: patch ROOT/REPORTS/COVERED -----------------------------------------
    saved = (freshness.ROOT, freshness.REPORTS, dict(freshness.COVERED))
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        (tp / "reports").mkdir()
        freshness.ROOT = tp
        freshness.REPORTS = tp / "reports"
        freshness.COVERED = {"r.json": (["src.py"], True)}
        try:
            # report NEWER than source -> fresh
            (tp / "src.py").write_text("x = 1\n")
            time.sleep(0.02)
            (tp / "reports" / "r.json").write_text(json.dumps({"ok": True}))
            fresh = freshness.compute()
            r_fresh = next(r for r in fresh["reports"] if r["report"] == "r.json")
            ck("2a. a report NEWER than its covered source is FRESH", r_fresh["stale"] is False)

            # source NEWER than report -> stale
            time.sleep(0.02)
            (tp / "src.py").write_text("x = 2  # changed after the cert\n")
            os.utime(tp / "src.py", None)
            stale = freshness.compute()
            r_stale = next(r for r in stale["reports"] if r["report"] == "r.json")
            ck("2b. STALE BITES — a covered source NEWER than the report flips it to STALE",
               r_stale["stale"] is True and r_stale["mtime_stale"] is True)
            ck("4. a stale REQUIRED report appears in stale_required (blocks Diamond)",
               "r.json" in stale["stale_required"])

            # commit mismatch -> stale (pin a deterministic HEAD; the temp dir is not a git repo)
            saved_head = freshness._head
            freshness._head = lambda: "aaaabbbbccccdddd"
            freshness.COVERED = {"c.json": (["nonexistent_glob_*.py"], True)}
            (tp / "reports" / "c.json").write_text(json.dumps({"commit": "deadbeefdeadbeef"}))
            cm = freshness.compute()
            freshness._head = saved_head
            r_cm = next(r for r in cm["reports"] if r["report"] == "c.json")
            ck("3. COMMIT BITES — a report whose recorded commit != HEAD is flagged stale",
               r_cm["stale"] is True and r_cm["commit_stale"] is True)
        finally:
            freshness.ROOT, freshness.REPORTS, freshness.COVERED = saved

    print("\n  real reports stale_required: %s" % (real["stale_required"] or "none"))
    print("CERT-FRESHNESS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
