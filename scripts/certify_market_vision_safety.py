#!/usr/bin/env python3
"""certify_market_vision_safety — the abuse/illegality blocks for the opportunity engine.

Blocks: illegal scraping / platform abuse, fake competitor claims, unsupported privacy/data-sale
claims, build-without-validation, spend/outreach without approval. These are the doctrine lines the
Market Vision Engine must never cross.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.market_vision import (source_registry as src, signals as sig, mining, thesis as th,  # noqa: E402
                                 validation as val, routers)

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("MARKET VISION SAFETY — abuse, illegality, and unsupported-claim blocks")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "MVSafe"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            src.seed(N, store=st)
            aid = next(s["source_id"] for s in src.inventory(N, store=st)["sources"] if s["status"] == "approved")

            ck("1. illegal scraping behavior is refused",
               not src.can_scan(N, aid, behavior="illegal_scraping", store=st)["allowed"])
            ck("2. platform abuse behavior is refused",
               not src.can_scan(N, aid, behavior="platform_abuse", store=st)["allowed"])
            ck("3. contact harvesting for spam is refused",
               not src.can_scan(N, aid, behavior="contact_harvesting_for_spam", store=st)["allowed"])
            ck("4. private data collection is refused",
               not src.can_scan(N, aid, behavior="private_data_collection", store=st)["allowed"])

            ck("5. a fake (uncited) competitor claim is refused",
               not mining.analyze_competitor(N, competitor_name="X", market="m", weaknesses=["bad"],
                                              evidence_signal_ids=[], store=st)["ok"])
            ck("6. an unsupported data-sale claim is refused",
               not mining.detect_privacy_gap(N, market="m", incumbent="X", observed_practice="p",
                                             user_concern_signal_ids=[], claims_data_sale=True, store=st)["ok"])

            # build without validation downgrade
            s1 = sig.extract(N, aid, signal_type="complaint", text_summary="pain",
                             evidence_excerpt_ref="e1", store=st)["signal"]
            t = th.generate(N, title="T", one_line_thesis="o", customer="c", pain="p", product_gap="g",
                            proposed_product="pp", business_model="free_core_paid_pro",
                            evidence_refs=[s1["signal_id"]], assumptions=["a"], risks=["r"],
                            recommended_next_step="launch_venture", store=st)["thesis"]
            ck("7. a build/launch recommendation without validation is blocked (downgraded)",
               t["recommended_next_step"] != "launch_venture")

            ck("8. an experiment with no budget is refused (no blind spend)",
               not val.recommend(N, t["opportunity_id"], hypothesis="h", method="outreach_test",
                                 budget=None, duration="1w", success_criteria=["x"],
                                 kill_criteria=["y"], store=st)["ok"])
            ck("9. a venture route without approval is refused (no unapproved launch)",
               not routers.route_to_venture(N, t["opportunity_id"], approval_ref="", budget=100,
                                            validation_present=True, store=st)["ok"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_market_vision_safety", "green" if green else "red",
                files_observed=["anima/market_vision/source_registry.py", "anima/market_vision/mining.py",
                                "anima/market_vision/validation.py", "anima/market_vision/routers.py"],
                report_paths=[], duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nMARKET-VISION-SAFETY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
