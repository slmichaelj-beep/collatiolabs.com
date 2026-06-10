#!/usr/bin/env python3
"""certify_release_tier_blockers — only what a tier CLAIMS can block it.

Proves, over the real classifier + tier logic (hermetic synthetic states; nothing live mutated):
  1. enterprise_readiness PARTIAL does NOT block Local/Internal or Private Alpha (scope waiver),
     and classifies enterprise_only_partial (non-blocking) for the global gate.
  2. audiobook_intake DEFERRED does NOT block any current rung (future-tier scope waiver) and
     classifies deferred_not_claimed (non-blocking).
  3. A PRODUCT RED is NEVER waived — it blocks every rung regardless of scope tables.
  4. An off-list product PARTIAL blocks (no waiver without a declared scope).
  5. The Enterprise rung itself still REQUIRES enterprise_readiness — scoped is not vanished.
  6. The global repeatability gate (run_diamond logic) blocks on product_partial/product_red
     ONLY — deferred + enterprise-only buckets never block it.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.verification import flakes, release_tiers as rt   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("RELEASE-TIER BLOCKERS — only what a tier claims can block it")
    print("=" * 92)

    # ---- 1. enterprise scope waiver ----------------------------------------------------------
    w_li = rt.waiver_for("enterprise_readiness", "local_internal", honest_external=set(), status="PARTIAL")
    w_pa = rt.waiver_for("enterprise_readiness", "private_alpha", honest_external=set(), status="PARTIAL")
    ck("1. enterprise_readiness PARTIAL is scope-waived at Local/Internal + Private Alpha",
       w_li == "scope" and w_pa == "scope")
    c = flakes.classify_one("enterprise_readiness", "PARTIAL")
    ck("1b. ...and classifies enterprise_only_partial / NON-blocking for the global gate",
       c["class"] == "enterprise_only_partial" and c["release_blocking"] is False)

    # ---- 2. deferred future-tier waiver -------------------------------------------------------
    waived = [rt.waiver_for("audiobook_intake", t, honest_external=set(), status="DEFERRED")
              for t in rt.TIERS]
    ck("2. audiobook_intake DEFERRED is scope-waived at EVERY current rung (%s)" % waived,
       all(w == "scope" for w in waived))
    c = flakes.classify_one("audiobook_intake", "DEFERRED")
    ck("2b. ...and classifies deferred_not_claimed / NON-blocking",
       c["class"] == "deferred_not_claimed" and c["release_blocking"] is False)

    # ---- 3. product red is never waived --------------------------------------------------------
    reds = [rt.waiver_for(f, "local_internal", honest_external=set(), status="WALLPAPER")
            for f in ("enterprise_readiness", "audiobook_intake")]
    ck("3. a PRODUCT RED is never waived — scope tables cannot bless a defect",
       all(w is None for w in reds))
    c = flakes.classify_one("audiobook_intake", "WALLPAPER")
    ck("3b. ...and classifies product_red / BLOCKING", c["class"] == "product_red"
       and c["release_blocking"] is True)

    # ---- 4. off-list partial blocks ------------------------------------------------------------
    c = flakes.classify_one("some_unscoped_feature", "PARTIAL")
    ck("4. an off-list product PARTIAL blocks (no waiver without a declared scope)",
       c["class"] == "product_partial" and c["release_blocking"] is True)
    ck("4b. ...and has NO tier waiver",
       rt.waiver_for("some_unscoped_feature", "local_internal", honest_external=set(),
                     status="PARTIAL") is None)

    # ---- 5. the Enterprise rung still requires enterprise_readiness ----------------------------
    ck("5. at the Enterprise rung the waiver DISAPPEARS (scoped is not vanished)",
       rt.waiver_for("enterprise_readiness", "enterprise", honest_external=set(),
                     status="PARTIAL") is None)

    # ---- 6. the global gate blocks on product_* only -------------------------------------------
    items = [{"feature": "audiobook_intake", "status": "DEFERRED"},
             {"feature": "enterprise_readiness", "status": "PARTIAL"},
             {"feature": "acknowledge_flow", "status": "PARTIAL"},
             {"feature": "everything_else", "status": "COMPLETE"}]
    run = flakes.classify_run(items, {"dependencies": []}, {})
    blocking = [o["feature"] for o in run["per_feature"] if o["release_blocking"]]
    ck("6. global gate: deferred + enterprise-only + intentional-external never block (blocking: %s)"
       % (blocking or "none"), blocking == [])
    run2 = flakes.classify_run(items + [{"feature": "real_gap", "status": "PARTIAL"}],
                               {"dependencies": []}, {})
    ck("6b. ...but a REAL product partial still blocks",
       "real_gap" in run2["product_partials"])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_release_tier_blockers", "green" if green else "red",
                files_observed=["anima/verification/flakes.py", "anima/verification/release_tiers.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nRELEASE-TIER-BLOCKERS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
