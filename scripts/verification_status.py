#!/usr/bin/env python3
"""verification_status — print the COMPUTED release verdict (directive §28 block) from the live
dashboard. Read-only; never sets anything green.

  python3 scripts/verification_status.py            # human-readable
  python3 scripts/verification_status.py --json      # the raw dashboard payload
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# the §28 gate order + label
LINES = [
    ("build_identity", "BUILD IDENTITY"), ("program_reality", "PROGRAM REALITY"),
    ("feature_certs", "FEATURE CERTS"), ("live_user_reality", "LIVE USER REALITY"),
    ("scenario_coverage", "TOTAL SCENARIO MATRIX"), ("rover_journeys", "ROVER CRITICAL JOURNEYS"),
    ("observation_bundle", "OBSERVATION BUNDLE"), ("renegade", "RENEGADE CHAINS"),
    ("performance", "PERFORMANCE REALITY"), ("host_reality", "HOST REALITY"),
    ("ai_security", "AI SECURITY"), ("consent_privacy", "CONSENT / PRIVACY / DATA CONTROL"),
    ("recovery", "RECOVERY"), ("ui_truth_consistency", "UI TRUTH CONSISTENCY"),
    ("evidence_room", "EVIDENCE ROOM"), ("cert_freshness", "CERT FRESHNESS"),
    ("flake_classification", "CERT-FLAKE CLASSIFICATION"), ("repeatability", "DIAMOND REPEATABILITY"),
]


def main() -> int:
    from anima.verification import dashboard
    d = dashboard.data()
    if "--json" in sys.argv:
        print(json.dumps(d, indent=2))
        return 0
    if d.get("error"):
        print("VERIFICATION STATUS: BLOCKED — %s" % d["error"])
        return 1
    t = d["top"]
    gs = {g["gate_id"]: g["status"] for g in d["gates"]}
    print("VERIFICATION STATUS")
    print("=" * 60)
    verdict = "PASS" if t["diamond_eligible"] else t["release_state"]
    print("DIAMOND CERTIFICATION v2: %s" % verdict)
    for gid, label in LINES:
        st = gs.get(gid, "unknown").upper()
        print("%-34s %s" % (label + ":", st))
    print("OBSERVATION BUNDLE COMPLETE:        %s" % t.get("observation_bundle"))
    print("UNKNOWN:                            %d" % t.get("unknown_user_behavior", 0))
    print("P0 OPEN:                            %d" % t.get("p0_open", 0))
    print("P1 OPEN:                            %d" % t.get("p1_open", 0))
    print("STALE CERTS:                        %d" % t.get("stale_certs", 0))
    print("UNCLASSIFIED FLAKES:                %d" % t.get("unclassified_flakes", 0))
    print("OPEN BLOCKERS:                      %d" % t.get("open_blockers", 0))
    print("RUNNING == COMMITTED == SERVED == CERTIFIED: %s"
          % ("YES" if t.get("running_eq_committed_eq_served_eq_certified") else "NO"))
    print("-" * 60)
    print("RELEASE STATE: %s · DECISION: %s" % (t["release_state"], t["release_decision"]))
    print("REASON: %s" % t.get("reason", ""))
    # the four-rung Diamond ladder (release tiers)
    rt = d.get("release_tiers") or []
    if rt:
        print("-" * 60)
        print("RELEASE TIERS (Diamond ladder) — highest now: %s"
              % (t.get("highest_diamond_tier_label") or "none yet"))
        for r in rt:
            mark = "  <= ceiling" if r.get("tier_id") == t.get("highest_diamond_tier") else ""
            miss = r.get("missing_evidence") or []
            why = (" · missing: " + ", ".join(miss[:3])) if miss else ""
            print("  %-38s %-7s Diamond=%-3s [%s]%s%s" % (
                r.get("name") or r.get("label"), r.get("color"),
                "YES" if r.get("diamond_eligible") else "NO", r.get("decision", ""), why, mark))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
