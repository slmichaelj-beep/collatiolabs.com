#!/usr/bin/env python3
"""certify_revenue_intelligence_layer — revenue events → graph → lessons, truth separated.

Events become structured intelligence; a payment with no evidence is refused (not counted); only
payment/repeat-purchase counts as revenue (reply/proposal/invoice do not); a margin without a cost
model is flagged unverified; objections become recurring-lesson records; lessons carry evidence.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.revenue_intelligence import store as ri, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("REVENUE INTELLIGENCE LAYER — event store / revenue graph / learning loop / truth separation")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "RICert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            ck("1. an unknown event type is refused",
               not ri.record(N, event_type="nonsense", store=st)["ok"])
            ck("2. a reply is recorded but is NOT revenue",
               ri.record(N, event_type="reply", buyer_segment="SMB", offer_id="o1", channel="warm_intro",
                         response="positive", store=st)["event"]["counts_as_revenue"] is False)
            ck("3. a proposal counts as pipeline, not revenue",
               ri.record(N, event_type="proposal", offer_id="o1", price_presented=2500, store=st)["event"]["counts_as_pipeline"]
               and not ri.record(N, event_type="invoice", offer_id="o1", price_presented=2500, store=st)["event"]["counts_as_revenue"])
            ck("4. a payment with no evidence is refused (not counted)",
               not ri.record(N, event_type="payment", offer_id="o1", price_presented=2500, store=st)["ok"])
            ck("5. a payment with evidence counts as revenue",
               ri.record(N, event_type="payment", buyer_segment="SMB", offer_id="o1", channel="warm_intro",
                         price_presented=2500, payment_evidence_ref="stripe_1", store=st)["event"]["counts_as_revenue"])
            ck("6. a margin with no cost model is flagged unverified",
               not ri.record(N, event_type="delivery", offer_id="o1", gross_margin=0.6, store=st)["event"]["gross_margin_verified"])
            ck("7. a margin with a cost model is verified",
               ri.record(N, event_type="delivery", offer_id="o1", gross_margin=0.6, cost_model_ref="cm1", store=st)["event"]["gross_margin_verified"])
            # objections
            ri.record(N, event_type="objection", offer_id="o1", objection_type="too expensive", store=st)
            ri.record(N, event_type="objection", offer_id="o1", objection_type="too expensive", store=st)
            ri.record(N, event_type="objection", offer_id="o2", objection_type="not now", store=st)

            g = ri.graph(N, store=st)
            ck("8. the graph counts only collected cash as revenue", g["total_cash_collected"] == 2500)
            ck("9. the graph separates pipeline events from revenue", g["pipeline_events"] >= 2)
            ck("10. the graph surfaces cash by channel/buyer/offer",
               g["cash_by_channel"].get("warm_intro") == 2500 and g["cash_by_offer"].get("o1") == 2500)
            ck("11. recurring objections are ranked", g["recurring_objections"].get("too expensive") == 2)

            ls = ri.lessons(N, store=st)
            ck("12. a recurring objection becomes an evidence-backed lesson",
               any("objection" in l["lesson"] and "recurs" in l["lesson"] for l in ls))
            ck("13. a cash-producing offer becomes a high-confidence lesson",
               any("real cash" in l["lesson"] and l.get("confidence") == "high" for l in ls))

            d = api.dashboard(N, store=st)
            ck("14. the dashboard assembles graph + lessons + honest truth note",
               d["ok"] and d["lessons"] and "revenue" in d["honesty"].lower())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_revenue_intelligence_layer", "green" if green else "red",
                files_observed=["anima/revenue_intelligence/store.py"],
                report_paths=["reports/revenue_intelligence_layer.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nREVENUE-INTELLIGENCE-LAYER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
