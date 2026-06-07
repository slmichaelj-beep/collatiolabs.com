#!/usr/bin/env python3
"""
certify_improvement_engine — the self-diagnosing -> self-improving loop, proven end-to-end on a real
reports/patterns input, with status DECIDED by actually RUNNING certs (the no-wallpaper rule, one
level up).

The Pattern Observatory turns observation into work orders (reports/patterns.json):

    pattern -> evidence -> root cause -> recommended fix -> required cert

This module ingests those work orders into a tracked IMPROVEMENT BACKLOG and drives each to a
VERIFIABLE closure by running its required cert. This cert proves that contract through the SAME
functions the CLI (scripts/improvement_backlog.py / pattern_to_backlog.py) calls:

  A. INGEST A REAL PATTERNS INPUT — ingest() folds a reports/patterns-shaped payload into one
     BacklogItem per pattern, each OPEN, carrying its work-order fields (severity/root_cause/fix/
     cert_required) faithfully.
  B. CERT RESOLUTION — resolve_cert maps an explicit alias, a 'scripts/x.py --flag', and a
     'python3 -m pkg --flag' phrase to the right runnable argv (flags preserved); a descriptive-only
     phrase resolves to None; runnable_certs de-dupes two phrases that name the same command.
  C. STATUS IS DECIDED BY RUNNING THE CERT (the heart) — verify_item runs cert_required through the
     engine's REAL _default_runner (a real subprocess, no fake):
        * an item whose cert is the genuinely-passing hermetic scripts/certify_cross_store_search.py
          -> CERTIFIED (loop closed, fix PROVEN right now);
        * an item whose cert exits non-zero -> NEEDS_WORK (actionable, honest — never a spurious pass);
        * an item with only a descriptive phrase -> MANUAL (no runnable command; a human must verify).
     The per-cert exit codes are recorded in the item's verification block.
  D. RANK — actionable-first: the NEEDS_WORK item sorts before the CERTIFIED one.
  E. DURABLE ROUND-TRIP — save_backlog/load_backlog round-trip every item to a TEMP path, and
     re-ingesting preserves each item's created stamp + prior CERTIFIED status (history kept).
  F. CLI SURFACE — the real user entry scripts/improvement_backlog.py --json renders the ranked
     backlog from the redirected store (ingest -> verify -> rank -> report), proving the live path the
     user actually drives.

Hermetic + offline: every reports path (PATTERNS_JSON / BACKLOG_JSON + the load/save default args) is
redirected into a temp dir, so the REAL reports/improvement_backlog.json is never clobbered; no live
model, no live server, no network (the one subprocess we run is the independently-hermetic
cross_store_search cert). The real .anima is fingerprinted before/after and asserted byte-identical
(the engine never writes .anima). Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_footprint = _g0pe._footprint

# A real, genuinely-passing, independently-hermetic cert -> the CERTIFIED branch.
_PASSING_CERT = "scripts/certify_cross_store_search.py"
# A syntactically-valid but NON-EXISTENT cert path -> _default_runner exits non-zero -> NEEDS_WORK.
_FAILING_CERT = "scripts/certify_improvement_engine_no_such_cert_zzz.py"


def _redirect_reports(ie, tmp: Path):
    """Point every reports path the engine + CLI touch at a temp dir, and return a restore fn.
    The load/save helpers bind their default path at def-time, so we patch __defaults__ too (not just
    the module constants) — otherwise the CLI's bare load_backlog()/save_backlog() would hit the real
    reports/. Mirrors how the other certs redirect extra stores not covered by _temp_store."""
    saved = {
        "PATTERNS_JSON": ie.PATTERNS_JSON,
        "BACKLOG_JSON": ie.BACKLOG_JSON,
        "load_backlog_def": ie.load_backlog.__defaults__,
        "save_backlog_def": ie.save_backlog.__defaults__,
        "load_patterns_def": ie.load_patterns.__defaults__,
    }
    ie.PATTERNS_JSON = tmp / "patterns.json"
    ie.BACKLOG_JSON = tmp / "improvement_backlog.json"
    ie.load_backlog.__defaults__ = (tmp / "improvement_backlog.json",)
    ie.save_backlog.__defaults__ = (tmp / "improvement_backlog.json",)
    ie.load_patterns.__defaults__ = (tmp / "patterns.json",)

    def restore():
        ie.PATTERNS_JSON = saved["PATTERNS_JSON"]
        ie.BACKLOG_JSON = saved["BACKLOG_JSON"]
        ie.load_backlog.__defaults__ = saved["load_backlog_def"]
        ie.save_backlog.__defaults__ = saved["save_backlog_def"]
        ie.load_patterns.__defaults__ = saved["load_patterns_def"]

    return restore


def main() -> int:
    from anima import improvement_engine as ie
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("IMPROVEMENT ENGINE — self-diagnosing -> self-improving (ingest -> verify-by-cert -> rank)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # A real reports/patterns-shaped payload (same envelope pattern_observatory.py emits): a P0 that
    # WILL certify (its cert genuinely passes), a P1 that WILL fail (a non-existent cert -> non-zero),
    # and a P2 that is descriptive-only (no runnable command -> MANUAL).
    payload = {
        "phase": "5 — Pattern Observatory",
        "schema": "pattern -> evidence -> root cause -> recommended fix -> required cert",
        "patterns": [
            {"pattern_id": "source_use", "title": "Source retrieved but not used", "severity": "P0",
             "frequency": 3, "root_cause": "a labeled source was retrieved but the reply bypassed it",
             "recommended_fix": "re-assert the reference-recall seam",
             "cert_required": [_PASSING_CERT, _PASSING_CERT],   # dup on purpose -> must de-dupe to 1
             "expected_improvement": {"metric": "source_used_rate"}, "source": "audit:source_use"},
            {"pattern_id": "completeness", "title": "Response stripped", "severity": "P1",
             "frequency": 2, "root_cause": "final gate truncated the reply",
             "recommended_fix": "preserve the whole answer through the gate",
             "cert_required": [_FAILING_CERT], "source": "traces"},
            {"pattern_id": "host_resource_spike", "title": "Host spike", "severity": "P2",
             "frequency": 1, "root_cause": "a host resource spike correlated with a slow turn",
             "recommended_fix": "investigate the host window",
             "cert_required": ["anima.host_window probe (descriptive only — no runnable command)"],
             "source": "traces"},
        ],
    }

    tmp_dir = tempfile.mkdtemp(prefix="ie_cert_")
    restore = _redirect_reports(ie, Path(tmp_dir))
    try:
        # ---- A. INGEST A REAL PATTERNS INPUT --------------------------------------------
        items = ie.ingest(payload)
        ck("A1: ingest creates one backlog item per pattern", len(items) == 3)
        ck("A2: every fresh item starts OPEN (unverified this run)",
           all(it.status == ie.OPEN for it in items))
        by_id = {it.pattern_id: it for it in items}
        ck("A3: work-order fields are carried from the patterns input (severity + root cause)",
           by_id["source_use"].severity == "P0"
           and by_id["source_use"].root_cause.startswith("a labeled source"))

        # ---- B. CERT RESOLUTION ----------------------------------------------------------
        ck("B1: resolve a 'scripts/x.py' phrase -> that runnable argv",
           ie.resolve_cert(_PASSING_CERT) == [_PASSING_CERT])
        ck("B2: resolve a 'scripts/x.py --flag' phrase keeps the flag",
           ie.resolve_cert("scripts/certify_whole_mri.py --gate")
           == ["scripts/certify_whole_mri.py", "--gate"])
        ck("B3: resolve a 'python3 -m pkg --flag' phrase -> that argv",
           ie.resolve_cert("python3 -m anima.whole_mri --selftest")
           == ["python3", "-m", "anima.whole_mri", "--selftest"])
        ck("B4: a descriptive-only phrase resolves to None (no runnable command)",
           ie.resolve_cert("anima.host_window probe (descriptive only — no runnable command)") is None)
        ck("B5: runnable_certs de-dupes two phrases naming the SAME command -> 1",
           len(ie.runnable_certs([_PASSING_CERT, _PASSING_CERT])) == 1)

        # ---- C. STATUS IS DECIDED BY RUNNING THE CERT (real _default_runner, real subprocess) ----
        for it in items:
            ie.verify_item(it)                       # default runner == ie._default_runner (real)
        by_id = {it.pattern_id: it for it in items}
        ck("C1: P0 whose cert genuinely PASSES -> CERTIFIED (loop closed, fix proven NOW)",
           by_id["source_use"].status == ie.CERTIFIED)
        ck("C2: the CERTIFIED item's verification records a real exit-0 cert run",
           by_id["source_use"].verification.get("all_ok") is True
           and by_id["source_use"].verification.get("runnable") == 1
           and any(r.get("exit") == 0 and r.get("ok") is True
                   for r in by_id["source_use"].verification.get("results", [])))
        ck("C3: P1 whose cert FAILS (non-zero) -> NEEDS_WORK (actionable, never a spurious pass)",
           by_id["completeness"].status == ie.NEEDS_WORK)
        ck("C4: the NEEDS_WORK item records a non-zero cert exit",
           any(r.get("ok") is False and r.get("exit") != 0
               for r in by_id["completeness"].verification.get("results", [])))
        ck("C5: P2 with only a descriptive phrase -> MANUAL (no runnable command)",
           by_id["host_resource_spike"].status == ie.MANUAL
           and by_id["host_resource_spike"].verification.get("runnable") == 0)

        # ---- D. RANK ---------------------------------------------------------------------
        ordered = ie.rank(items)
        ck("D1: rank() puts the actionable NEEDS_WORK item first",
           ordered[0].pattern_id == "completeness")
        ck("D2: rank() puts the proven-done CERTIFIED item last",
           ordered[-1].pattern_id == "source_use")

        # ---- E. DURABLE ROUND-TRIP (TEMP path) -------------------------------------------
        out_path = ie.save_backlog(items)            # default arg now -> temp dir
        ck("E1: save_backlog writes into the redirected temp dir (NOT real reports/)",
           Path(out_path).parent == Path(tmp_dir))
        loaded = ie.load_backlog()
        ck("E2: load_backlog round-trips all items with their status",
           len(loaded) == 3
           and {it.pattern_id: it.status for it in loaded}
           == {it.pattern_id: it.status for it in items})
        created0 = {it.pattern_id: it.created for it in loaded}
        re_ingested = ie.ingest(payload, existing=loaded)
        ck("E3: re-ingest preserves each item's created stamp (history kept)",
           all(it.created == created0[it.pattern_id] for it in re_ingested))
        ck("E4: re-ingest preserves the prior CERTIFIED status (not silently reopened)",
           {it.pattern_id: it.status for it in re_ingested}["source_use"] == ie.CERTIFIED)

        # ---- F. CLI SURFACE (the real user entry) ----------------------------------------
        # scripts/improvement_backlog.py reads ie.PATTERNS_JSON / load_backlog() (now redirected) and
        # renders the ranked backlog. We invoke its main() and assert it renders our items + counts.
        _spec_cli = importlib.util.spec_from_file_location(
            "ie_cli", str(ROOT / "scripts" / "improvement_backlog.py"))
        cli = importlib.util.module_from_spec(_spec_cli)
        _spec_cli.loader.exec_module(cli)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_cli = cli.main(["--json"])             # machine-readable ranked payload
        cli_out = buf.getvalue()
        ck("F1: the CLI scripts/improvement_backlog.py --json exits 0", rc_cli == 0)
        try:
            cli_payload = json.loads(cli_out)
        except Exception:
            cli_payload = {}
        cli_status = {it["pattern_id"]: it["status"] for it in cli_payload.get("items", [])}
        ck("F2: the CLI renders the ranked backlog the user reads (3 items, our statuses)",
           cli_payload.get("stats", {}).get("total") == 3
           and cli_status.get("source_use") == ie.CERTIFIED
           and cli_status.get("completeness") == ie.NEEDS_WORK)
        ck("F3: the CLI reports exactly one proven-done (CERTIFIED) + one actionable-open(NEEDS_WORK)",
           cli_payload.get("stats", {}).get("certified") == 1
           and cli_payload.get("stats", {}).get("open_actionable") == 1)
    finally:
        restore()
        try:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (engine never writes .anima)",
       fp_before == fp_after)

    print("\nIMPROVEMENT-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
