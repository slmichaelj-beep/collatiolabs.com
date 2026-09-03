#!/usr/bin/env python3
"""certify_revenue_swarm_factory — Revenue Swarm Factory, every gate.

Experiment needs success+kill+budget+fulfillment+approval. Variants keep claims consistent
(unsupported differentiation refused). Channels policy-checked (forbidden refused; outreach approval-
gated). Kill/scale/pivot enforces evidence (no signal=>kill; scale needs demand+margin+capacity).
Budget allocator: no spend without approval; scale band needs evidence; loss-maker can't scale.
Portfolio separates pipeline from cash; dead experiments shown.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.revenue_swarm import factory as f, portfolio as p, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("REVENUE SWARM FACTORY — experiments / variants / channels / kill-scale / budget")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SwarmCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            ck("1. an experiment with no kill criteria is refused",
               not f.create_experiment(N, opportunity_id="o1", offer_id="of1", hypothesis="h", method="audit_presale",
                                       buyer_segment="b", budget=250, duration_days=7, success_criteria=["5 sales"],
                                       kill_criteria=[], fulfillment_plan="manual", store=st)["ok"])
            ck("2. an experiment with no fulfillment plan is refused",
               not f.create_experiment(N, opportunity_id="o1", offer_id="of1", hypothesis="h", method="audit_presale",
                                       buyer_segment="b", budget=250, duration_days=7, success_criteria=["5"],
                                       kill_criteria=["0"], fulfillment_plan="", store=st)["ok"])
            e = f.create_experiment(N, opportunity_id="o1", offer_id="of1", hypothesis="SMBs will pre-buy an audit",
                                    method="audit_presale", buyer_segment="SMB ops", budget=250, duration_days=7,
                                    success_criteria=["3 presales"], kill_criteria=["0 replies in 20"],
                                    fulfillment_plan="concierge", store=st)["experiment"]
            ck("3. a complete experiment is created (approval pending)", e["status"] == "approval_pending")
            ck("4. running an experiment without approval is refused",
               not f.approve_experiment(N, e["experiment_id"], approval_ref="", store=st)["ok"])
            ck("5. an approved experiment can run", f.approve_experiment(N, e["experiment_id"], approval_ref="lamar", store=st)["ok"])

            ck("6. an unsupported differentiation variant is refused",
               not f.offer_variant(N, experiment_id=e["experiment_id"], variant_type="premium_audit", price=2500,
                                   differentiation="best in world", store=st)["ok"])
            ck("7. a variant labels its price as an assumption",
               f.offer_variant(N, experiment_id=e["experiment_id"], variant_type="cheap_report", price=49,
                               store=st)["variant"]["price_is_assumption"])

            ck("8. a forbidden channel is refused",
               not f.channel_test(N, experiment_id=e["experiment_id"], channel="spam", store=st)["ok"])
            ck("9. a policy-violating channel is refused",
               not f.channel_test(N, experiment_id=e["experiment_id"], channel="content_post", policy_ok=False, store=st)["ok"])
            ck("10. an outreach channel without approval is refused",
               not f.channel_test(N, experiment_id=e["experiment_id"], channel="direct_email_approved", store=st)["ok"])
            ck("11. an approved channel test is created",
               f.channel_test(N, experiment_id=e["experiment_id"], channel="warm_intro", store=st)["ok"])

            # results + kill/scale/pivot
            p.record_results(N, e["experiment_id"], leads=20, replies=0, store=st)
            kill = p.kill_scale_pivot(N, e["experiment_id"], store=st)["recommendation"]
            ck("12. no signal => kill", kill["action"] == "kill")

            e2 = f.create_experiment(N, opportunity_id="o2", offer_id="of2", hypothesis="h2", method="paid_consult",
                                     buyer_segment="b", budget=250, duration_days=7, success_criteria=["s"],
                                     kill_criteria=["k"], fulfillment_plan="manual", store=st)["experiment"]
            p.record_results(N, e2["experiment_id"], leads=20, replies=6, meetings=3, cash=300, store=st)
            nopf = p.kill_scale_pivot(N, e2["experiment_id"], demand_proven=True, margin_proven=False,
                                      capacity_proven=True, store=st)["recommendation"]
            ck("13. signal but unproven margin => pivot (not scale)", nopf["action"] == "pivot")
            scale = p.kill_scale_pivot(N, e2["experiment_id"], demand_proven=True, margin_proven=True,
                                       capacity_proven=True, store=st)["recommendation"]
            ck("14. demand+margin+capacity all proven => scale", scale["action"] == "scale")

            ck("15. spend without approval is refused",
               not p.allocate_budget(N, e2["experiment_id"], band="validation", approval_ref="", store=st)["ok"])
            ck("16. an organic ($0) band needs no approval",
               p.allocate_budget(N, e2["experiment_id"], band="organic", store=st)["ok"])
            ck("17. a scale budget without evidence is refused",
               not p.allocate_budget(N, e2["experiment_id"], band="scale", approval_ref="lamar",
                                     evidence_present=False, store=st)["ok"])
            ck("18. a loss-making experiment cannot get scale budget",
               not p.allocate_budget(N, e2["experiment_id"], band="scale", approval_ref="lamar",
                                     evidence_present=True, margin_positive=False, store=st)["ok"])
            ck("19. an evidence-backed, margin-positive scale budget is approved",
               p.allocate_budget(N, e2["experiment_id"], band="scale", approval_ref="lamar",
                                 evidence_present=True, margin_positive=True, store=st)["ok"])

            port = p.portfolio(N, store=st)
            ck("20. the portfolio shows the killed experiment (not hidden)", port["killed"])
            ck("21. the portfolio separates pipeline meetings from collected cash",
               port["pipeline_meetings"] == 3 and port["cash_collected"] == 300)
            dash = api.dashboard(N, store=st)
            ck("22. the dashboard assembles experiments + portfolio + honest next move",
               dash["ok"] and dash["experiments"] and "cash" in dash["honesty"].lower())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_revenue_swarm_factory", "green" if green else "red",
                files_observed=["anima/revenue_swarm/factory.py", "anima/revenue_swarm/portfolio.py"],
                report_paths=["reports/revenue_swarm_factory.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nREVENUE-SWARM-FACTORY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
