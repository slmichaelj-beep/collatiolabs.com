#!/usr/bin/env python3
"""certify_foundry_safety — abuse prevention + foundry kill switch."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.foundry import safety   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FOUNDRY SAFETY — abuse prevention + kill switch")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "FoundrySafetyCert"
        ck("1. a spam / mass-outreach pattern is blocked",
           not safety.screen_action(N, "send_message", "blast to 5000 emails, act now!", store=st)["allowed"])
        ck("2. a fake-identity / impersonation request is blocked",
           not safety.screen_action(N, "create_account", "create a fake persona to pose as a human", store=st)["allowed"])
        ck("3. storing raw credentials is blocked",
           not safety.screen_action(N, "file_create", "save the API key and password in Vera", store=st)["allowed"])
        ck("4. a bank transfer is human/professional-only (blocked here)",
           not safety.screen_action(N, "bank_transfer", "wire $5000 to vendor", store=st)["allowed"])
        ck("5. a clean action passes the abuse screen (still subject to authority+approval)",
           safety.screen_action(N, "draft", "draft a friendly outreach to an approved lead", store=st)["allowed"])
        # cross-venture leak
        ck("6. cross-venture data access without an approved import is blocked",
           not safety.cross_venture_leak_blocked("vA", "vB")["allowed"])
        ck("7. a venture reading its OWN data is allowed",
           safety.cross_venture_leak_blocked("vA", "vA")["allowed"])
        ck("8. an explicit approved cross-venture import is allowed",
           safety.cross_venture_leak_blocked("vA", "vB", approved=True)["allowed"])
        # kill switch
        safety.engage(N, scopes=["all"], store=st)
        ck("9. global kill freezes everything", safety.is_frozen(N, store=st))
        ck("9b. restart requires explicit confirm",
           not safety.disengage(N, store=st)["ok"] and safety.disengage(N, confirm=True, store=st)["ok"])
        safety.engage(N, venture_id="vX", store=st)
        ck("10. a per-venture freeze stops one venture, not the rest",
           safety.is_frozen(N, venture_id="vX", store=st) and not safety.is_frozen(N, venture_id="vY", store=st))
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_foundry_safety", "green" if green else "red",
                files_observed=["anima/foundry/safety.py"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDRY-SAFETY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
