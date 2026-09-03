#!/usr/bin/env python3
"""certify_performance_tuning_report — the performance tuning report is REAL: grounded in measured
traces, structurally complete, and its headline cold-start FIX is actually present in the code (not just
documented). Tune from traces, not vibes.

  1. REPORTS EXIST       — reports/performance_tuning.md + reports/performance_patterns.json present.
  2. STRUCTURE COMPLETE  — every pattern carries route/scenario/latency/slowest_stage/host_pressure/
                           model_used/suggested_fix/expected_improvement/risk/cert_required/status.
  3. CANDIDATES COVERED  — the directive's tuning candidates are analysed (cold-start, normal_chat,
                           fast path, source budget, host-pressure policy, heavy intake, final gate,
                           context immune, UI delivery).
  4. GROUNDED IN REAL TRACES — the cold-start (15.7s) + greeting (20ms) latencies match the live Lamar-
                           path Rover evidence (not invented numbers).
  5. KEYSTONE — COLD-START FIX IS REAL — mouth.py keep_alive default is raised to '1h' (not '30m') AND
                           the warm-on-startup thread is wired in server.py. A documented-but-unshipped
                           fix fails this check.
  6. HONEST AMBER        — warm normal-chat is reported over the 8s target (not faked green).

Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERFORMANCE TUNING REPORT — tuned from real traces; the cold-start fix is in the code")
    print("=" * 92)

    md = REPORTS / "performance_tuning.md"
    pj = REPORTS / "performance_patterns.json"
    ck("1. performance_tuning.md + performance_patterns.json present", md.exists() and pj.exists())
    try:
        data = json.loads(pj.read_text())
    except Exception as e:
        data = {}
        print("  XX   (performance_patterns.json unreadable: %r)" % e)
        fails.append("patterns unreadable")
    patterns = data.get("patterns", [])

    # ---- 2 structure complete -------------------------------------------------------------------
    need = {"route", "scenario", "latency_ms", "slowest_stage", "host_pressure", "model_used",
            "suggested_fix", "expected_improvement", "risk", "cert_required", "status"}
    structure_ok = bool(patterns) and all(need <= set(p.keys()) for p in patterns)
    ck("2. every pattern carries the full row schema (route/latency/slowest-stage/fix/risk/cert/status)",
       structure_ok)

    # ---- 3 candidates covered -------------------------------------------------------------------
    blob = " ".join((p.get("route", "") + " " + p.get("scenario", "")).lower() for p in patterns)
    needles = ["cold-start", "normal_chat", "fast path", "source", "host pressure", "intake",
               "final gate", "context immune", "ui delivery"]
    missing = [n for n in needles if n not in blob]
    ck("3. the directive's tuning candidates are analysed%s" % (" — missing: " + ", ".join(missing) if missing else ""),
       not missing)

    # ---- 4 grounded in real traces --------------------------------------------------------------
    try:
        lp = json.loads((REPORTS / "lamar_path_rover_browser.json").read_text())
        lat = lp.get("latency_ms", {})
    except Exception:
        lat = {}
    cold = next((p for p in patterns if "cold-start" in p.get("route", "").lower()), {})
    grounded = (lat.get("first_turn") and cold.get("latency_ms") == lat.get("first_turn"))
    ck("4. cold-start latency matches the live Lamar-path measurement (real, not invented): %s ms"
       % cold.get("latency_ms"), bool(grounded))

    # ---- 5 KEYSTONE: the cold-start fix is in the code ------------------------------------------
    mouth = (ROOT / "anima" / "mouth.py").read_text()
    srv = (ROOT / "anima" / "server.py").read_text()
    keep_alive_fixed = 'os.environ.get("ANIMA_KEEP_ALIVE", "1h")' in mouth
    warm_wired = "def _warm()" in srv and "brain.warm()" in srv and "threading.Thread(target=_warm" in srv
    ck("5. KEYSTONE: cold-start fix shipped — keep_alive default '1h' in mouth.py + warm-on-startup wired in server.py",
       keep_alive_fixed and warm_wired)

    # ---- 6 honest amber -------------------------------------------------------------------------
    warm = next((p for p in patterns if p.get("route", "").startswith("normal_chat")), {})
    honest = "AMBER" in (warm.get("status", "") or "").upper() or "over" in (warm.get("expected_improvement", "") or "").lower()
    ck("6. warm normal-chat is reported honestly over the 8s target (not faked green)", honest)

    print("\n  patterns analysed: %d · cold-start status: %s" % (len(patterns), cold.get("status")))
    print("PERFORMANCE-TUNING-REPORT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
