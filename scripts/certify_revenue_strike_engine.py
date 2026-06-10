#!/usr/bin/env python3
"""certify_revenue_strike_engine — Immediate Revenue Strike Engine, every gate.

Cash wedges (blocked asset excluded; sell_now needs proof). Offer (limitations + QA required;
unsupported claim refused; launch needs approval + fulfillment). Buyers (forbidden source refused;
disqualified never contacted; outreach approval-gated). Sprint (claim needs proof; spam/fake-urgency
refused; success/kill required). Fulfillment packet required before launch. Revenue truth (pipeline/
forecast/invoice ≠ revenue; cash needs evidence; profit needs cost model).
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.revenue import strike as s, truth as t, api  # noqa: E402
from anima.commercial import assets as _assets, ip_license as _ip  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("IMMEDIATE REVENUE STRIKE ENGINE — wedge / offer / buyers / sprint / fulfillment / truth")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "RevCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            _assets.seed(N, store=st)
            assets = _assets.inventory(N, store=st)["assets"]
            blocked_asset = assets[0]["asset_id"]   # unknown ownership
            clear_asset = assets[1]["asset_id"]
            _ip.set_status(N, clear_asset, ip_status="owned", license_status="clear",
                           security_status="safe_to_demo", store=st)

            ck("1. a wedge tied to a blocked/unknown-ownership asset is refused",
               not s.find_cash_wedge(N, wedge_name="x", offer_type="audit", buyer="b", pain="p",
                                     deliverable="d", price_range="$500", asset_id=blocked_asset, store=st)["ok"])
            noproof = s.find_cash_wedge(N, wedge_name="AI workflow audit", offer_type="audit",
                                        buyer="ops leaders", pain="manual workflows", deliverable="audit report",
                                        price_range="$1500", proof_available=[], store=st)["cash_wedge"]
            ck("2. a wedge with no proof is not sell_now", noproof["recommended_action"] != "sell_now")
            w = s.find_cash_wedge(N, wedge_name="AI trust readiness audit", offer_type="audit",
                                  buyer="AI teams", pain="no trust posture", deliverable="readiness report",
                                  price_range="$2500", proof_available=["cert report"],
                                  fulfillment_complexity="low", asset_id=clear_asset, store=st)["cash_wedge"]
            ck("3. a cleared, proven, low-complexity wedge is sell_now", w["recommended_action"] == "sell_now")
            for i in range(4):
                s.find_cash_wedge(N, wedge_name="wedge%d" % i, offer_type="report", buyer="b", pain="p",
                                  deliverable="report", price_range="$200", proof_available=["x"], store=st)
            ranked = s.rank_wedges(N, store=st)
            ck("4. at least 5 wedges are ranked, sell_now first", len(ranked) >= 5 and ranked[0]["recommended_action"] == "sell_now")

            ck("5. an offer with unsupported claims is refused",
               not s.package_offer(N, w["cash_wedge_id"], promise="get trust-ready", price=2500,
                                   timeline="1 week", limitations=["scope: 1 product"], inputs_required=["docs"],
                                   proof=[], qa_checklist=["accuracy"], claims=["99% pass"], store=st)["ok"])
            offer = s.package_offer(N, w["cash_wedge_id"], promise="get trust-ready in a week", price=2500,
                                    timeline="1 week", limitations=["scope: 1 product"], inputs_required=["docs"],
                                    proof=["prior cert"], qa_checklist=["accuracy", "completeness"], store=st)["offer"]
            ck("6. a complete offer is drafted (not auto-live)", offer["status"] == "draft")
            ck("7. launching without approval is refused",
               not s.launch_offer(N, offer["offer_id"], approval_ref="", fulfillment_ready=True, store=st)["ok"])
            ck("8. launching without a fulfillment packet is refused",
               not s.launch_offer(N, offer["offer_id"], approval_ref="lamar", fulfillment_ready=False, store=st)["ok"])

            ck("9. a buyer from a forbidden source is refused",
               not s.add_buyer(N, company_or_person="X", source="spam_list", pain_hypothesis="p", store=st)["ok"])
            ck("10. a buyer with no pain hypothesis is refused",
               not s.add_buyer(N, company_or_person="Y", source="warm_network", pain_hypothesis="", store=st)["ok"])
            b = s.add_buyer(N, company_or_person="Acme AI", source="warm_network",
                            pain_hypothesis="shipping AI with no trust story", fit_score=3, store=st)["buyer"]
            ck("11. contacting a buyer without approval is refused",
               not s.can_contact_buyer(N, b["buyer_id"], approval_ref="", store=st)["allowed"])
            ck("12. an approved contact on a qualified buyer is allowed",
               s.can_contact_buyer(N, b["buyer_id"], approval_ref="lamar", store=st)["allowed"])

            ck("13. a sprint with a claim but no proof is refused",
               not s.build_sprint(N, offer["offer_id"], messages=["hi"], proof_points=[], claims=["best"],
                                  success_criteria=["5 calls"], kill_criteria=["0 replies"], store=st)["ok"])
            ck("14. a sprint with spam language is refused",
               not s.build_sprint(N, offer["offer_id"], messages=["ACT NOW limited time!!!"], proof_points=["p"],
                                  claims=[], success_criteria=["5 calls"], kill_criteria=["0 replies"], store=st)["ok"])
            sp = s.build_sprint(N, offer["offer_id"], messages=["Saw you shipped an AI feature — want a trust audit?"],
                                proof_points=["prior cert"], claims=[], success_criteria=["5 calls"],
                                kill_criteria=["<2 replies in 20"], store=st)
            ck("15. a clean sprint is drafted (send still approval-gated)",
               sp["ok"] and sp["sales_sprint"]["approval_required"])

            ck("16. a fulfillment packet needs inputs/workflow/QA",
               not s.fulfillment_packet(N, offer["offer_id"], customer_inputs=[], workflow_steps=["x"],
                                        qa_checklist=["y"], delivery_format="pdf", time_estimate="3d",
                                        cost_estimate=300, store=st)["ok"])
            fp = s.fulfillment_packet(N, offer["offer_id"], customer_inputs=["product docs"],
                                      workflow_steps=["assess", "draft", "qa"], qa_checklist=["accuracy"],
                                      delivery_format="PDF report", time_estimate="3 days", cost_estimate=300, store=st)
            ck("17. a complete fulfillment packet is ready", fp["ok"] and fp["fulfillment"]["ready"])
            ck("18. with approval + fulfillment ready, the offer can launch",
               s.launch_offer(N, offer["offer_id"], approval_ref="lamar", fulfillment_ready=True, store=st)["ok"])

            ck("19. pipeline (proposal/invoice) is NOT counted as revenue",
               not t.record_event(N, offer_id=offer["offer_id"], stage="invoice_sent", amount=2500, store=st)["event"]["counts_as_revenue"])
            ck("20. cash_collected without payment evidence is refused",
               not t.record_event(N, offer_id=offer["offer_id"], stage="cash_collected", amount=2500, store=st)["ok"])
            ck("21. cash_collected with payment evidence counts as revenue",
               t.record_event(N, offer_id=offer["offer_id"], stage="cash_collected", amount=2500,
                              payment_evidence_ref="stripe_ch_1", store=st)["event"]["counts_as_revenue"])
            ck("22. profit without a cost model is refused",
               not t.record_event(N, offer_id=offer["offer_id"], stage="gross_profit", amount=2200, store=st)["ok"])
            bd = t.board(N, store=st)
            ck("23. the truth board separates pipeline from collected cash",
               bd["cash_collected"] == 2500 and bd["pipeline_value_forecast"] == 2500 and "NOT revenue" in bd["honesty"])

            dash = api.dashboard(N, store=st)
            ck("24. the dashboard assembles wedges + revenue truth + next move",
               dash["ok"] and dash["top_wedge"] and dash["revenue_truth"]["cash_collected"] == 2500)
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_revenue_strike_engine", "green" if green else "red",
                files_observed=["anima/revenue/strike.py", "anima/revenue/truth.py"],
                report_paths=["reports/revenue_strike_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nREVENUE-STRIKE-ENGINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
