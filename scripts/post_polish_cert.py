#!/usr/bin/env python3
"""post_polish_cert — the ONE honest status gate for the post-polish 10^380 program (founder §10).

Reports each lane as GREEN (its cert passes), PARTIAL (partly built), or DEFERRED (not built yet —
never faked green). POST-POLISH: GREEN only when every REQUIRED lane is GREEN and running == committed.

    python3 scripts/post_polish_cert.py            # the status board
    python3 scripts/post_polish_cert.py --gate      # exit non-zero unless every required lane is GREEN
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(args, token, timeout=400):
    try:
        r = subprocess.run([sys.executable] + [str(a) for a in args], capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT))
        return (r.returncode == 0 and token in (r.stdout + r.stderr))
    except Exception:
        return False


def _audit_clean():
    try:
        d = json.loads((ROOT / "reports" / "live_path_results.json").read_text())
        feats = d.get("features") or []
        bad = sum(1 for f in feats if f.get("status") in ("WALLPAPER", "STUB", "UNREACHABLE", "REGRESSED", "UNKNOWN"))
        parts = [f for f in feats if f.get("status") == "PARTIAL"]
        return bad == 0 and all("EXTERNAL" in (f.get("reason") or "").upper() for f in parts), len(feats)
    except Exception:
        return False, 0


def main() -> int:
    gate = "--gate" in sys.argv
    print("POST-POLISH CERT — the honest status board")
    print("=" * 92)

    clean, n = _audit_clean()
    running_committed = _run([SCRIPTS / "deploy_check.py"], "GREEN", 60)

    # (lane, state, required, detail)
    lanes = []

    def lane(name, state, required, detail):
        lanes.append((name, state, required, detail))
        glyph = {"GREEN": "●", "PARTIAL": "◐", "DEFERRED": "○"}.get(state, "?")
        print("  %s  %-26s %-9s %s" % (glyph, name, state, detail))

    lane("DIAMOND BASELINE", "GREEN" if clean else "PARTIAL", True,
         "%d contracts, 0 wallpaper/stub/unknown" % n if clean else "audit not clean")
    lane("CONTEXT IMMUNE SYSTEM",
         "GREEN" if _run([SCRIPTS / "certify_context_immune.py"], "CONTEXT-IMMUNE CERT: CERTIFIED") else "PARTIAL",
         True, "four-route contamination immunity + correction-flush + fixture")
    lane("ROVER CRITICAL",
         "GREEN" if _run([SCRIPTS / "vera_rover.py", "--gate"], "ROVER: PASS") else "PARTIAL",
         True, "synthetic user drives core + adversarial journeys (first cut)")
    # Wave 2 Alpha: only agency suggest-only is built; the rest are DEFERRED
    w2 = _run([SCRIPTS / "certify_agency_suggest_only.py"], "AGENCY-SUGGEST-ONLY CERT: CERTIFIED")
    lane("WAVE 2 ALPHA", "PARTIAL" if w2 else "DEFERRED", False,
         "agency suggest-only GREEN; identity-sandbox-live + approval-queue + no-silent-power + aggregate PENDING")
    lane("TRUST DASHBOARD",
         "GREEN" if _run([SCRIPTS / "certify_observatory.py"], "OBSERVATORY CERT: CERTIFIED") else "PARTIAL",
         False, "read-only Observatory GREEN; Trust Dashboard 2.0 (quarantine/connector panels) PENDING")
    lm_static = _run([SCRIPTS / "certify_living_map.py"], "LIVING MAP STATIC: GREEN")
    lm_nowall = _run([SCRIPTS / "certify_living_map_no_wallpaper.py"], "LIVING MAP NO-WALLPAPER: GREEN")
    lane("LIVING MAP", "GREEN" if (lm_static and lm_nowall) else "PARTIAL", False,
         "M1 static real map + M2 live event pulses GREEN (nodes/edges/status + animation backed by "
         "real telemetry, no wallpaper); M3 replay + M4 simulation + M5 pattern overlay PENDING")
    lane("UX BOW", "DEFERRED", False, "product_polish GREEN; the full Diamond UX bow not yet a distinct cert")
    lane("DEMO READINESS", "DEFERRED", False, "demo script + one-click demo data not built")
    lane("PRIVATE ALPHA READINESS", "DEFERRED", False, "non-builder core-loop walkthrough not certified")
    lane("RUNNING == COMMITTED", "GREEN" if running_committed else "PARTIAL", True,
         "the live server executes exactly the committed code" if running_committed else "restart needed")

    required_green = all(s == "GREEN" for _, s, req, _ in lanes if req)
    greens = sum(1 for _, s, _, _ in lanes if s == "GREEN")
    deferred = sum(1 for _, s, _, _ in lanes if s == "DEFERRED")
    print("=" * 92)
    verdict = "GREEN" if required_green else "IN PROGRESS"
    print("POST-POLISH: %s   (%d/%d lanes green · %d deferred · required-lanes-green=%s)"
          % (verdict, greens, len(lanes), deferred, required_green))
    print("RUNNING == COMMITTED" if running_committed else "RUNNING != COMMITTED (restart)")
    return 0 if (not gate or required_green) else 1


if __name__ == "__main__":
    raise SystemExit(main())
