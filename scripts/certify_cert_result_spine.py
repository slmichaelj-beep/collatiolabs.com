#!/usr/bin/env python3
"""certify_cert_result_spine — the machine-readable cert result spine holds.

Proves (each rule BITES — the bad case downgrades, the good case stays):
  1. STALE COMMIT BLOCKS GREEN     — recorded commit != HEAD -> effective stale.
  2. DIRTY TREE BLOCKS GREEN       — unwaived dirty file -> blocked; explicit waiver -> green.
  3. MISSING REPORT BLOCKS GREEN   — a recorded report_path that no longer exists -> blocked.
  4. HOST MISMATCH BLOCKS          — host-specific record from another host -> blocked.
  5. PROFILE MISMATCH BLOCKS       — host-specific record from another runtime profile -> blocked.
  6. CHANGED INPUT HASH BLOCKS     — an observed input modified after the run -> stale.
  7. DASHBOARD CANNOT GREEN STALE  — freshness.compute() surfaces every downgraded record; an
                                     absent/unknown record is 'unknown', never green.
Plus: emit() writes a SCHEMA-COMPLETE record; a schema-incomplete record evaluates 'unknown'.

Hermetic: scratch records in a temp dir; the real reports/cert_results is restored byte-identical.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.verification import cert_result as cr   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("CERT-RESULT SPINE — no UI state, no stale record, no unknown can create green")
    print("=" * 92)

    head = cr.head_commit()
    me = cr.host_id()

    # ---- 0. emit writes a schema-complete record -------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        old_dir = cr.RESULTS_DIR
        cr.RESULTS_DIR = Path(td)
        try:
            obs = Path(td) / "input.txt"
            obs.write_text("v1")
            rep = Path(td) / "some_report.json"
            rep.write_text("{}")
            rec = cr.emit("scratch_cert", "green", files_observed=[str(obs)],
                          report_paths=[str(rep)], duration_sec=0.1, host_specific=True)
            ck("0. emit() writes every schema field", all(k in rec for k in cr.REQUIRED_FIELDS))
            ck("0b. record persisted + loadable", cr.load("scratch_cert") is not None)

            # ---- 1. stale commit bites ------------------------------------------------------
            ev = cr.evaluate(dict(rec, commit="0000000"), head=head, live_dirty=[],
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("1. STALE COMMIT — recorded commit != HEAD -> stale", ev["effective"] == "stale")
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=[],
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("1b. ...and a matching commit stays green", ev["effective"] == "green")

            # ---- 2. dirty tree bites unless waived ------------------------------------------
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=["anima/server.py"],
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("2. DIRTY TREE — unwaived dirty file -> blocked", ev["effective"] == "blocked")
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=["anima/server.py"],
                             waived_dirty=("anima/server.py",),
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("2b. ...an EXPLICIT waiver (named non-impacting file) stays green",
               ev["effective"] == "green")

            # ---- 3. missing report bites ----------------------------------------------------
            rep.unlink()
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=[],
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("3. MISSING REPORT — recorded report_path gone -> blocked", ev["effective"] == "blocked")
            rep.write_text("{}")

            # ---- 4/5. host + profile mismatch bite ------------------------------------------
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=[],
                             live_host_id="deadbeefdeadbeef", live_profile_id=rec["runtime_profile_id"])
            ck("4. HOST MISMATCH — host-specific record from another host -> blocked",
               ev["effective"] == "blocked")
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=[],
                             live_host_id=rec["host_id"], live_profile_id="Ultra@otherhost")
            ck("5. PROFILE MISMATCH — another runtime profile -> blocked", ev["effective"] == "blocked")
            any_rec = cr.emit("portable_cert", "green", files_observed=[str(obs)],
                              report_paths=[str(rep)], host_specific=False)
            ev = cr.evaluate(any_rec, head=any_rec["commit"], live_dirty=[],
                             live_host_id="deadbeefdeadbeef", live_profile_id="Ultra@otherhost")
            ck("5b. a host-agnostic record ('any') is NOT host/profile-gated", ev["effective"] == "green")

            # ---- 6. changed input hash bites ------------------------------------------------
            obs.write_text("v2 — changed after the run")
            ev = cr.evaluate(rec, head=rec["commit"], live_dirty=[],
                             live_host_id=rec["host_id"], live_profile_id=rec["runtime_profile_id"])
            ck("6. CHANGED INPUTS — observed file modified since the run -> stale",
               ev["effective"] == "stale")

            # ---- schema floor ----------------------------------------------------------------
            ev = cr.evaluate({"cert_name": "x", "status": "green"})
            ck("S. a schema-INCOMPLETE record evaluates 'unknown' (never green)",
               ev["effective"] == "unknown")
            ev = cr.evaluate(None)
            ck("S2. an ABSENT record evaluates 'unknown' (never green)", ev["effective"] == "unknown")

            # ---- 7. the dashboard path consumes the spine -------------------------------------
            stale_rec = cr.emit("stale_probe_cert", "green", files_observed=[str(obs)],
                                report_paths=[str(rep)])
            (cr.RESULTS_DIR / "stale_probe_cert.json").write_text(
                json.dumps(dict(stale_rec, commit="0000000")))
            from anima.verification import freshness
            fr = freshness.compute()
            down = fr.get("cert_results_downgraded", {})
            ck("7. freshness.compute() surfaces the downgraded record (dashboard cannot green it)",
               down.get("stale_probe_cert", {}).get("effective") == "stale")
        finally:
            cr.RESULTS_DIR = old_dir

    # ---- emit OUR OWN result through the spine (the spine certifies itself) -----------------
    green = not fails
    cr.emit("certify_cert_result_spine", "green" if green else "red",
            files_observed=["anima/verification/cert_result.py", "anima/verification/freshness.py"],
            report_paths=[], duration_sec=time.perf_counter() - t0,
            failures=fails, next_action="" if green else "fix the failing spine rule(s) above")

    print("\nCERT-RESULT-SPINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
