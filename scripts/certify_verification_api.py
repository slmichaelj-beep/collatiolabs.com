#!/usr/bin/env python3
"""certify_verification_api — the verification run/override/acknowledge API obeys the doctrine:
a Founder Override cannot be created without a complete record, and an override NEVER fakes green.

  1. OVERRIDE REQUIRES RECORD — record_override rejects an incomplete override (missing who/why/risk/
     expiry/follow-up) and stores a complete one.
  2. OVERRIDE EXPIRES         — active_overrides(now) excludes an expired override.
  3. OVERRIDE NEVER FAKES GREEN (keystone) — diamond_eligible is computed from gates ONLY; an override
     is not an input to release_decision.decide(), so an amber gate stays not-eligible no matter what
     override exists.
  4. ACKNOWLEDGE GUARDED     — acknowledge_blocker requires blocker_id + who.
  5. RUN API GUARDED         — start_run rejects an unknown run type; get_run on a missing id errors.
  6. SERVED (if up)          — GET /founder/verification/status returns the computed top; POST
     founder-override with an incomplete body is rejected 400.

Hermetic (a temp override store). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
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

    print("VERIFICATION API — Founder Override requires a record + never fakes green")
    print("=" * 92)

    from anima.verification import api, release_decision

    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        api.VDIR, api.OVERRIDES, api.ACKS, api.RUNS = tp, tp / "ov.json", tp / "ack.json", tp / "runs"

        bad = api.record_override("lamar", "program_reality", "", "", "", "")  # missing fields
        ck("1a. an INCOMPLETE founder override is REJECTED (not stored)",
           bad.get("error") and not api.OVERRIDES.exists())
        good = api.record_override("lamar", "program_reality", "external apple dep",
                                   risk_accepted="low", expires_at="2026-07-01T00:00:00Z",
                                   required_follow_up="ship APNs key", at="2026-06-08T00:00:00Z")
        ck("1b. a COMPLETE founder override is stored as a full record",
           not good.get("error") and good["who"] == "lamar" and api.OVERRIDES.exists())

        ck("2. active_overrides(now) excludes an EXPIRED override",
           api.active_overrides("2026-07-02T00:00:00Z") == []
           and len(api.active_overrides("2026-06-09T00:00:00Z")) == 1)

        # 3 override never fakes green: an amber required gate stays not-eligible (override isn't an input)
        gates = [{"gate_id": "program_reality", "status": "amber", "required_for": ["diamond", "private_alpha"]},
                 {"gate_id": "build_identity", "status": "green", "required_for": ["diamond", "private_alpha"]}]
        dec = release_decision.decide(gates, {"p0_open": 0, "unknown_count": 0}, {"status": "green", "running_commit": "x"})
        ck("3. OVERRIDE NEVER FAKES GREEN — an amber gate stays not diamond-eligible regardless of overrides",
           dec["diamond_eligible"] is False and dec["color"] == "amber")

        ck("4. acknowledge_blocker requires blocker_id + who",
           api.acknowledge_blocker("", "lamar").get("error")
           and not api.acknowledge_blocker("gate:x", "lamar").get("error"))

        ck("5. start_run rejects an unknown type; get_run on a missing id errors",
           api.start_run("bogus").get("error") and api.get_run("nope").get("error"))

    # 6 served leg (only if the server is up + has the new endpoints)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/founder/verification/status", timeout=6) as r:
            up = r.status == 200 and isinstance(json.loads(r.read()).get("release_state"), str)
    except Exception:
        up = False
    if up:
        try:
            req = urllib.request.Request("http://127.0.0.1:8765/founder/verification/founder-override",
                                         data=b'{"who":"x"}', method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=6)
            rejected = False
        except urllib.error.HTTPError as e:
            rejected = e.code == 400
        except Exception:
            rejected = False
        ck("6. GET /founder/verification/status serves the computed top; POST incomplete override -> 400",
           rejected)
    else:
        print("  --   6. (skipped — server without the new endpoints; logic teeth above are server-free)")

    print("\nVERIFICATION-API CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
