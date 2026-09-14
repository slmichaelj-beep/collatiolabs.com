#!/usr/bin/env python3
"""certify_distribution_engine — Distribution + Demand Capture, every gate.

Buyer DB: forbidden source refused; needs_review source can't be contacted; contact needs approval.
Assets: unsupported claim refused; draft only; publishing needs approval. Partners: agreement needs
approval; revenue-share needs legal review. Overview honest.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.distribution import engine as e, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("DISTRIBUTION + DEMAND CAPTURE — buyer DB / assets / partners / funnels")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "DistCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            ck("1. a forbidden buyer source is refused",
               not e.add_buyer(N, company="X", buyer_type="smb", source="spam_list", pain_hypothesis="p", store=st)["ok"])
            review = e.add_buyer(N, company="Y", buyer_type="smb", source="public_business_listing",
                                 pain_hypothesis="manual ops", store=st)["buyer"]
            ck("2. an approved-list source qualifies", review["source_policy"] == "approved")
            nr = e.add_buyer(N, company="Z", buyer_type="smb", source="approved_directory",
                             pain_hypothesis="p", store=st)["buyer"]
            # approved_directory is in APPROVED_SOURCES -> approved; build a needs_review case via unknown source
            unknown = e.add_buyer(N, company="W", buyer_type="smb", source="conference_badge_scan",
                                  pain_hypothesis="p", store=st)["buyer"]
            ck("3. an unlisted source is needs_review", unknown["source_policy"] == "needs_review")
            ck("4. a needs_review buyer cannot be contacted",
               not e.can_contact(N, unknown["buyer_profile_id"], approval_ref="lamar", store=st)["allowed"])
            ck("5. an approved buyer still needs approval to contact",
               not e.can_contact(N, review["buyer_profile_id"], approval_ref="", store=st)["allowed"])
            ck("6. an approved buyer with approval can be contacted",
               e.can_contact(N, review["buyer_profile_id"], approval_ref="lamar", store=st)["allowed"])

            ck("7. an asset with an unsupported claim is refused",
               not e.build_asset(N, asset_type="landing_page", target_buyer="smb", pain="p", offer="o",
                                 cta="book", claims=["10x faster"], proof_refs=[], store=st)["ok"])
            asset = e.build_asset(N, asset_type="landing_page", target_buyer="smb ops", pain="manual work",
                                  offer="audit", cta="Book a call", claims=["audited in 72h"],
                                  proof_refs=["delivery#1"], store=st)["asset"]
            ck("8. a proof-backed asset is a draft (not published)", asset["status"] == "draft")
            ck("9. publishing without approval is refused",
               not e.publish_asset(N, asset["asset_id"], approval_ref="", store=st)["ok"])
            ck("10. publishing with approval succeeds",
               e.publish_asset(N, asset["asset_id"], approval_ref="lamar", store=st)["asset"]["status"] == "published")

            ck("11. a partner agreement without approval is refused",
               not e.add_partner(N, partner_type="agency", value_proposition="dist", store=st)["ok"])
            ck("12. a revenue-share partner without legal review is refused",
               not e.add_partner(N, partner_type="agency", value_proposition="dist", revenue_share=True,
                                 approval_ref="lamar", store=st)["ok"])
            ck("13. an approved, legally-reviewed revenue-share partner is recorded",
               e.add_partner(N, partner_type="agency", value_proposition="dist", revenue_share=True,
                             approval_ref="lamar", legal_review_ref="atty", store=st)["ok"])

            d = api.dashboard(N, store=st)
            ck("14. the dashboard shows buyers/assets/published + honest gating",
               d["ok"] and d["published"] and "legal review" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_distribution_engine", "green" if green else "red",
                files_observed=["anima/distribution/engine.py"],
                report_paths=["reports/distribution_demand_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nDISTRIBUTION-ENGINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
