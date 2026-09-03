#!/usr/bin/env python3
"""certify_workforce_foundry — work-gap → economics → workflow → workforce → catalog → order → QA →
delivery → margin → productization, every gate.

Gaps from approved sources only; micro-work needs extreme automation; negative-margin blocked;
micro fulfillment-cost-too-high blocked; service needs workflow+team before sale; selling
approval-gated; order needs approved service + customer + inputs; delivery blocked before QA pass;
revenue only on payment+acceptance; productize-build needs repeated-run evidence; scale blocked when
margin unknown; no fake reviews/spam (no demand path => no business; channel-policy enforced).
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.workforce import discovery as d, economics as ec, fulfillment as ff, execution as ex, operations as ops, api  # noqa: E402
from anima.market_vision import source_registry as src  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("DIGITAL WORKFORCE FOUNDRY — gap→econ→workflow→workforce→catalog→order→QA→deliver→margin")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "WFCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            src.seed(N, store=st)
            aid = next(s["source_id"] for s in src.inventory(N, store=st)["sources"] if s["status"] == "approved")
            blocked = src.add_source(N, "scrape", "web", legal_policy="blocked", store=st)["source"]

            ck("1. a work gap from a blocked source is refused",
               not d.scan_work_gap(N, source_id=blocked["source_id"], title="x", description="y",
                                   buyer_segment="z", task_type="research", store=st)["ok"])
            gap = d.scan_work_gap(N, source_id=aid, title="SaaS app-review tagging", description="tag reviews",
                                  buyer_segment="SaaS teams", task_type="analysis", pain="manual tagging",
                                  evidence_refs=["r1", "r2"], store=st)["work_gap"]
            ck("2. a work gap from an approved source is created", gap["work_gap_id"])

            ck("3. micro-work without extreme automation is refused",
               not d.classify(N, gap["work_gap_id"], unit_type="micro", price_per_unit=0.75,
                              automation_requirement="medium", store=st)["ok"])
            cl = d.classify(N, gap["work_gap_id"], unit_type="micro", price_per_unit=0.75,
                            automation_requirement="extreme", store=st)
            ck("4. micro-work with extreme automation classifies (=> product)",
               cl["ok"] and cl["classification"]["recommended_model"] == "product")
            dec = d.decide(N, gap["work_gap_id"], recommended_path="product", why="repeatable, automatable",
                           confidence="medium", store=st)
            ck("5. a product/service decision is produced with rationale", dec["ok"] and dec["decision"]["why"])

            ck("6. negative-margin unit economics is blocked",
               not ec.unit_economics(N, gap["work_gap_id"], price_per_unit=0.75, ai_cost=0.5,
                                     human_review_cost=0.4, store=st)["ok"])
            ck("7. micro-work with too-high fulfillment cost is blocked",
               not ec.unit_economics(N, gap["work_gap_id"], price_per_unit=0.75, ai_cost=0.5, store=st)["ok"])
            ue = ec.unit_economics(N, gap["work_gap_id"], price_per_unit=0.75, ai_cost=0.04,
                                   tool_api_cost=0.02, cac=0.05, store=st)
            ck("8. viable unit economics is computed + labeled estimate",
               ue["ok"] and ue["unit_economics"]["margins_are_estimates"])
            ck("9. no demand path => no business",
               not ec.demand_capture(N, gap["work_gap_id"], buyer="SaaS PMs", where_to_find_buyers=[],
                                     sales_motion="content", proof_needed=["demo"], store=st)["ok"])
            ck("10. a channel that violates policy is refused",
               not ec.demand_capture(N, gap["work_gap_id"], buyer="SaaS PMs", where_to_find_buyers=["forum"],
                                     sales_motion="outbound", proof_needed=["demo"], channel_policy_ok=False, store=st)["ok"])

            ck("11. a fulfillment workflow needs inputs/steps/QA/failure-modes",
               not ff.design_workflow(N, gap["work_gap_id"], inputs_required=[], steps=["s"],
                                      qa_checks=["c"], delivery_format="csv", turnaround_time="1d",
                                      failure_modes=["f"], store=st)["ok"])
            wf = ff.design_workflow(N, gap["work_gap_id"], inputs_required=["review export"],
                                    steps=["ingest", "tag", "qa"], qa_checks=["accuracy", "format"],
                                    delivery_format="tagged CSV", turnaround_time="24h",
                                    failure_modes=["ambiguous reviews"], agents_required=["tagger"], store=st)["workflow"]
            ck("12. a complete fulfillment workflow is designed", wf["workflow_id"])

            ck("13. a service cannot exist without a team (workflow alone insufficient)",
               not ff.add_service(N, gap["work_gap_id"], service_name="Review Tagging", buyer="SaaS",
                                  promise="tagged reviews", deliverable="CSV", price=0.75,
                                  turnaround_time="24h", limitations=["English only"], store=st)["ok"])
            ck("14. a paid team without budget is refused",
               not ff.build_workforce(N, gap["work_gap_id"], team_name="Tag Team", roles=["tagger", "qa"],
                                      is_paid=True, qa_policy_ref="qa1", store=st)["ok"])
            team = ff.build_workforce(N, gap["work_gap_id"], team_name="Tag Team", roles=["tagger", "qa"],
                                      qa_policy_ref="qa1", store=st)
            ck("15. a workforce team with a workflow + QA policy is built", team["ok"])
            svc = ff.add_service(N, gap["work_gap_id"], service_name="Review Tagging", buyer="SaaS teams",
                                 promise="tagged reviews in 24h", deliverable="tagged CSV", price=49.0,
                                 turnaround_time="24h", limitations=["English only", "max 5k rows"], store=st)["service"]
            ck("16. a service with workflow+team+limitations is drafted", svc["status"] == "draft")

            ck("17. a draft (unapproved) service cannot take a work order",
               not ex.create_work_order(N, svc["service_id"], customer_id="cust1",
                                        inputs_received=["export.csv"], price=49.0, store=st)["ok"])
            ck("18. selling a service requires approval",
               not ff.approve_service(N, svc["service_id"], approval_ref="", store=st)["ok"])
            ff.approve_service(N, svc["service_id"], approval_ref="lamar", store=st)
            wo = ex.create_work_order(N, svc["service_id"], customer_id="cust1",
                                      inputs_received=["export.csv"], price=49.0, cost_estimate=3.2, store=st)["work_order"]
            ck("19. an approved service + customer + inputs creates a work order", wo["work_order_id"])

            ck("20. delivery is blocked before a QA pass",
               not ex.deliver(N, wo["work_order_id"], deliverable_refs=["out.csv"], store=st)["ok"])
            failqa = ex.run_qa(N, wo["work_order_id"], checks={"accuracy": True, "source_citation": False}, store=st)
            ck("21. missing source citation fails QA", failqa["qa"]["result"] == "fail")
            okqa = ex.run_qa(N, wo["work_order_id"], checks={"accuracy": True, "format": True, "source_citation": True}, store=st)
            ck("22. a clean QA pass marks the order ready for delivery", okqa["qa"]["accepted_for_delivery"])
            dv = ex.deliver(N, wo["work_order_id"], deliverable_refs=["out.csv"], store=st)
            ck("23. after QA pass, delivery succeeds + is NOT yet revenue",
               dv["ok"] and dv["work_order"]["revenue_recognition_status"] == "pending")

            nopay = ex.record_outcome(N, wo["work_order_id"], customer_status="delivered", store=st)
            ck("24. no revenue is recognized without payment/acceptance evidence",
               nopay["work_order"]["revenue_recognition_status"] == "not_revenue")
            paid = ex.record_outcome(N, wo["work_order_id"], customer_status="accepted",
                                     payment_evidence_ref="stripe_ch_123", store=st)
            ck("25. revenue is recognized only with payment+acceptance evidence",
               paid["work_order"]["revenue_recognition_status"] == "recognized")
            ck("26. a testimonial is blocked without permission", not paid["work_order"]["testimonial_allowed"])

            mr = ops.margin_report(N, svc["service_id"], store=st)["margin"]
            ck("27. the margin report computes from real recognized orders", mr["units_completed"] == 1 and mr["revenue"] == 49.0)
            cap = ops.capacity(N, svc["service_id"], tasks_per_day=10, committed_per_day=25, store=st)["capacity"]
            ck("28. over-capacity blocks selling more", not cap["can_sell_more"])
            rep = ops.reputation(N, svc["service_id"], quality_score=0.5, refund_rate=0.3, store=st)["reputation"]
            ck("29. bad quality/refunds block scale", not rep["scale_allowed"])
            ck("30. productization build needs repeated-run evidence",
               ops.productize(N, svc["service_id"], repeatable_steps=["ingest", "tag"],
                              automation_candidates=["tagging"], software_hypothesis="self-serve tagger",
                              observed_runs=1, store=st)["productization"]["recommended_next_step"] == "watch")
            ck("31. a workstream with many repeated runs recommends building an internal tool",
               ops.productize(N, svc["service_id"], repeatable_steps=["ingest", "tag"],
                              automation_candidates=["tagging"], software_hypothesis="self-serve tagger",
                              observed_runs=6, store=st)["productization"]["recommended_next_step"] == "build_internal_tool")

            br = ops.chairman_briefing(N, store=st)
            ck("32. the briefing separates activity from recognized revenue", "activity" in br["honesty"].lower() or "recognized" in br["honesty"].lower())
            dash = api.dashboard(N, store=st)
            ck("33. the dashboard assembles gaps/catalog/portfolio/briefing",
               dash["ok"] and dash["work_gaps"] and dash["service_catalog"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_workforce_foundry", "green" if green else "red",
                files_observed=["anima/workforce/discovery.py", "anima/workforce/economics.py",
                                "anima/workforce/fulfillment.py", "anima/workforce/execution.py",
                                "anima/workforce/operations.py"],
                report_paths=["reports/workforce_foundry_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex2:
        print("  (emit failed: %r)" % ex2)
    print("\nWORKFORCE-FOUNDRY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
