#!/usr/bin/env python3
"""certify_operator_governance_visibility — the operator UI visibly states the governance posture.

/governance.json serves the live posture (authority L0, external/spending disabled, legal human-
only, kill switch); the founder + chairman pages render the governance banner from it.
"""
from __future__ import annotations

import json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("OPERATOR GOVERNANCE VISIBILITY — the UI states where authority stands")
    print("=" * 92)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/governance.json", timeout=10) as r:
            g = json.loads(r.read())["governance"]
        ck("1. /governance.json serves the live posture",
           g["authority_level"] == "L0" and g["external_actions_enabled"] is False
           and g["spending_enabled"] is False and g["legal_financial_human_only"] is True
           and "kill_switch_active" in g)
    except Exception as e:
        ck("1. /governance.json reachable (server down: %r)" % e, False)
        g = {}

    # the operator pages render the banner from /governance.json
    for page in ("founder.html", "chairman.html"):
        html = (ROOT / "anima" / "web" / page).read_text()
        ck("2. %s renders the governance banner (authority/external/spending/legal/kill) from "
           "/governance.json" % page,
           "govBanner" in html and "/governance.json" in html
           and all(t in html for t in ("authority_level", "external_actions_enabled",
                                       "spending_enabled", "human-only", "Kill switch")))
        ck("2b. %s shows the trace/observed chip + Observation link" % page,
           "Observed • Trace linked" in html and 'href="/observation"' in html)

    # the default posture is the SAFE one
    ck("3. default posture is the safe one: L0 / external off / spending off / legal human-only",
       g.get("authority_level") == "L0" and not g.get("external_actions_enabled")
       and not g.get("spending_enabled") and g.get("legal_financial_human_only"))

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_operator_governance_visibility", "green" if green else "red",
                files_observed=["anima/web/founder.html", "anima/web/chairman.html",
                                "anima/observation/emit.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nOPERATOR-GOVERNANCE-VISIBILITY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
