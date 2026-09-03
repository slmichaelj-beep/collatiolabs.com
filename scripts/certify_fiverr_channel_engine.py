#!/usr/bin/env python3
"""certify_fiverr_channel_engine — sources/intel/opportunity/gigs/profile/account/fulfillment/QA/
messaging/revenue/learning/router, every gate.

Sources never default-allowed; intel only manual/approved (no bulk scrape); prohibited service
concepts rejected; gig prohibited-claim block + publish approval + active-account gate; no fake
identity; no raw credentials; cell needs QA checklist; order needs requirements; delivery blocked
w/o QA; messaging blocks mass/review-pressure/off-platform; order isn't cash until payout evidence;
refund reverses; owned-channel router blocks circumvention.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.marketplaces.fiverr import sources as s, gigs as g, fulfillment as f, revenue as r, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FIVERR CHANNEL ENGINE — sources/intel/gigs/fulfillment/revenue/learning/router")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "FivCh"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            # sources
            src = s.register_source(N, source_type="public_gig", policy_status="needs_review", store=st)["source"]
            ck("1. an unreviewed source can't be used", not s.can_use_source(N, src["source_id"], store=st)["allowed"])
            src2 = s.register_source(N, source_type="help_doc", policy_status="approved", store=st)["source"]
            ck("2. an approved low-PII source can be used", s.can_use_source(N, src2["source_id"], store=st)["allowed"])
            ck("3. a login+automation source cannot be auto-approved",
               s.register_source(N, source_type="own_account", policy_status="approved",
                                 login_required=True, automation_allowed=True, store=st)["source"]["policy_status"] == "needs_review")

            # intel
            ck("4. bulk-scrape intel method is refused",
               not s.market_intel(N, category="ai", method="bulk_scrape", store=st)["ok"])
            ck("5. manual intel confidence reflects sample size",
               s.market_intel(N, category="ai workflow audits", method="manual_review", manual_sample_size=2, store=st)["intel"]["confidence"] == "low")

            # opportunity
            ck("6. a prohibited service concept (fake reviews) is rejected",
               not s.scan_opportunity(N, category="marketing", service_concept="buy fake reviews", buyer_pain="x", store=st)["ok"])
            opp = s.scan_opportunity(N, category="business", service_concept="AI workflow audit",
                                     buyer_pain="manual ops", starting_price_range="$250-$1500", store=st)
            ck("7. a compliant opportunity recommends drafting a gig", opp["ok"] and opp["opportunity"]["recommended_action"] == "draft_gig")

            # gigs
            ck("8. a gig with a prohibited claim is blocked",
               not g.draft_gig(N, title="I will get you guaranteed rankings", category="seo", prices=(50, 100, 150),
                               deliverables={"basic": ["x"], "standard": ["y"], "premium": ["z"]},
                               delivery_days=(1, 2, 3), description="guaranteed #1 ranking", requirements_from_buyer=["url"],
                               limitations=["none"], store=st)["ok"])
            ck("9. a gig with no buyer requirements is refused",
               not g.draft_gig(N, title="I will audit your workflows", category="business", prices=(250, 750, 1500),
                               deliverables={"basic": ["review"], "standard": ["report"], "premium": ["roadmap"]},
                               delivery_days=(2, 4, 6), description="practical workflow audit", requirements_from_buyer=[],
                               limitations=["advisory only; no revenue guarantee"], store=st)["ok"])
            gig = g.draft_gig(N, title="I will audit your business workflows for AI automation opportunities",
                              category="business", prices=(250, 750, 1500),
                              deliverables={"basic": ["workflow review"], "standard": ["opportunity report"], "premium": ["roadmap"]},
                              delivery_days=(2, 4, 6), description="A practical workflow + automation opportunity audit.",
                              requirements_from_buyer=["a description of your current workflows"],
                              limitations=["advisory + planning; estimates are assumptions, not guarantees"], store=st)["gig"]
            ck("10. a compliant gig drafts (claims pass) but is not published", gig["prohibited_claims_check"] == "pass" and gig["status"] == "draft")
            ck("11. publishing without approval is refused",
               not g.publish_gig(N, gig["gig_id"], approval_ref="", account_active=True, store=st)["ok"])
            ck("12. publishing without an active account is refused",
               not g.publish_gig(N, gig["gig_id"], approval_ref="lamar", account_active=False, store=st)["ok"])
            ck("13. with approval + active account a gig publishes",
               g.publish_gig(N, gig["gig_id"], approval_ref="lamar", account_active=True, store=st)["gig"]["status"] == "published")

            # profile + account
            ck("14. a fictional human persona is refused",
               not g.build_profile(N, display_name="Fake Person", bio="b", represents="Lamar",
                                   ai_disclosure="AI-assisted", fictional_persona=True, store=st)["ok"])
            ck("15. a profile without AI/company disclosure is refused",
               not g.build_profile(N, display_name="Lamar", bio="b", represents="Lamar", ai_disclosure="", store=st)["ok"])
            ck("16. the account record stores NO raw credentials + blocks abuse actions",
               (lambda a: not a["raw_credentials_stored"] and "scrape" in a["blocked_vera_actions"])(g.account_record(N, status="active", store=st)["account"]))

            # fulfillment
            ck("17. a cell needs a QA checklist + delivery template",
               not f.build_cell(N, gig_id=gig["gig_id"], roles=["analyst"], qa_checklist=[], delivery_template="t", store=st)["ok"])
            f.build_cell(N, gig_id=gig["gig_id"], roles=["analyst", "qa"], qa_checklist=["scope_match", "accuracy"],
                         delivery_template="report.md", capacity_per_day=3, store=st)
            noreq = f.intake_order(N, gig_id=gig["gig_id"], buyer_handle="buyer1", package="standard",
                                   price=750, requirements_received=[], store=st)["order"]
            ck("18. an order without requirements waits (work can't start)", noreq["status"] == "waiting_requirements")
            order = f.intake_order(N, gig_id=gig["gig_id"], buyer_handle="buyer2", package="standard",
                                   price=750, requirements_received=["workflow doc"], store=st)["order"]
            ck("19. order net revenue subtracts the platform fee", order["net_revenue_estimate"] < order["price"])
            ck("20. delivery is blocked before QA passes",
               not f.deliver(N, order["order_id"], deliverable_refs=["r"], store=st)["ok"])
            failqa = f.run_qa(N, order["order_id"], checks={"scope_match": True}, store=st)
            ck("21. incomplete QA fails (missing checks)", failqa["qa"]["result"] == "fail")
            okqa = f.run_qa(N, order["order_id"], checks={k: True for k in f.QA_CHECKS}, store=st)
            ck("22. a full QA pass allows delivery", okqa["qa"]["accepted_for_delivery"]
               and f.deliver(N, order["order_id"], deliverable_refs=["report.md"], store=st)["ok"])

            # messaging
            ck("23. a mass message is refused", not f.draft_message(N, context="inquiry", recipient="x", draft="hi", mass=True, store=st)["ok"])
            ck("24. review-pressure language is refused",
               not f.draft_message(N, context="delivery", recipient="x", draft="please leave me a 5-star review", store=st)["ok"])
            ck("25. off-platform payment solicitation is refused",
               not f.draft_message(N, context="order", recipient="x", draft="just pay me directly via PayPal", store=st)["ok"])
            ck("26. a clean inbound response drafts (approval-gated)",
               f.draft_message(N, context="inquiry", recipient="x", draft="Happy to help — can you share your current workflow?", store=st)["message"]["approval_required"])

            # revenue truth
            pend = r.record_revenue(N, order_id=order["order_id"], gross_order_amount=750, payout_status="pending", store=st)["revenue"]
            ck("27. a pending order is NOT cash", not pend["cash_received"])
            ck("28. an order with no payout evidence is NOT cash even if available",
               not r.record_revenue(N, order_id=order["order_id"], gross_order_amount=750, payout_status="available", store=st)["revenue"]["cash_received"])
            paid = r.record_revenue(N, order_id=order["order_id"], gross_order_amount=750, payout_status="paid_out",
                                    direct_fulfillment_cost=50, payout_evidence_ref="fiverr_payout_1", store=st)["revenue"]
            ck("29. paid_out + evidence counts as cash; net profit subtracts fee + cost",
               paid["cash_received"] and paid["net_profit_estimate"] == round(750 - 150 - 50, 2))
            ck("30. a refund reverses recognition",
               not r.record_revenue(N, order_id=order["order_id"], gross_order_amount=750, payout_status="refunded",
                                    payout_evidence_ref="x", store=st)["revenue"]["cash_received"])

            # learning + router
            ck("31. a learning record maps a signal to an action",
               r.learn(N, gig_id=gig["gig_id"], signal_type="inquiry", lesson="buyers ask about pricing",
                       recommended_action="revise_gig", store=st)["ok"])
            ck("32. owned-channel route without proven demand is refused",
               not r.route_to_owned(N, gig_id=gig["gig_id"], demand_proven=False, owned_offer_concept="x", store=st)["ok"])
            ck("33. owned-channel route without a separate acquisition channel is refused (no circumvention)",
               not r.route_to_owned(N, gig_id=gig["gig_id"], demand_proven=True, owned_offer_concept="audit", store=st)["ok"])
            ck("34. a proven gig routes to an owned concept via a separate channel, no circumvention",
               (lambda x: x["ok"] and not x["route"]["circumvention"])(r.route_to_owned(N, gig_id=gig["gig_id"], demand_proven=True,
                owned_offer_concept="direct $2,500 audit", separate_acquisition_channel="own landing page + cold email", store=st)))

            d = api.dashboard(N, store=st)
            ck("35. the dashboard assembles policy + account + gigs + orders + revenue honestly",
               d["ok"] and d["policy"]["scraping"].startswith("blocked") and "payout" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_fiverr_channel_engine", "green" if green else "red",
                files_observed=["anima/marketplaces/fiverr/sources.py", "anima/marketplaces/fiverr/gigs.py",
                                "anima/marketplaces/fiverr/fulfillment.py", "anima/marketplaces/fiverr/revenue.py"],
                report_paths=["reports/fiverr_channel_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nFIVERR-CHANNEL-ENGINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
