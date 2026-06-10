#!/usr/bin/env python3
"""certify_compounding_engine — Global Compounding Opportunity Engine, every gate.

Allocator: bad-quality can't scale; budgeted action needs approval; scale needs margin+capacity.
Moat: no unlawful data moat. Automation: needs repeated-workflow proof + margin thesis.
Productization: needs proof + build approval + paid layer. Partnership: needs approval; rev-share
needs legal review. Expansion: needs evidence + capacity + approval. Acquisition: research-only,
valuation labeled assumption, outreach needs approval + legal/financial review. Reinvestment: keep
reserve, approval required, protect quality/support, don't overfund unproven.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.compounding import allocator as a, growth as g, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("GLOBAL COMPOUNDING ENGINE — allocate / moat / automate / productize / partner / expand / acquire / reinvest")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "CompCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            ck("1. a bad-quality stream cannot be told to scale (=> fix)",
               a.allocate(N, workstream_id="w1", cash_collected=1000, gross_margin=0.5, quality_score=0.4,
                          capacity_ok=True, requested_action="scale", store=st)["allocation"]["action"] == "fix")
            ck("2. scale without positive margin/capacity downgrades to hold",
               a.allocate(N, workstream_id="w2", cash_collected=500, gross_margin=-0.1, quality_score=0.9,
                          capacity_ok=True, requested_action="scale", store=st)["allocation"]["action"] == "hold")
            ck("3. a budgeted allocation without approval is refused",
               not a.allocate(N, workstream_id="w3", cash_collected=1000, gross_margin=0.5, quality_score=0.9,
                              capacity_ok=True, requested_action="scale", budget=5000, approval_ref="", store=st)["ok"])
            ck("4. a proven, approved scale allocation is recorded",
               a.allocate(N, workstream_id="w3", cash_collected=1000, gross_margin=0.5, quality_score=0.9,
                          capacity_ok=True, requested_action="scale", budget=5000, approval_ref="lamar", store=st)["allocation"]["action"] == "scale")

            ck("5. an unlawful data moat is refused",
               not a.moat(N, workstream_id="w3", moat_type="lawful_workflow_data", lawful_data=False, store=st)["ok"])
            ck("6. a lawful moat (privacy trust) is recorded",
               a.moat(N, workstream_id="w3", moat_type="privacy_trust", store=st)["ok"])

            ck("7. automation without repeated-workflow proof is refused",
               not a.automation(N, workstream_id="w3", repeated_workflow=False, qa_pass_rate=0.9,
                                build_cost_estimate=5000, margin_improvement_estimate=0.3, store=st)["ok"])
            ck("8. automation without a positive margin thesis is refused",
               not a.automation(N, workstream_id="w3", repeated_workflow=True, qa_pass_rate=0.9,
                                build_cost_estimate=5000, margin_improvement_estimate=0, store=st)["ok"])
            ck("9. automation with proof + margin thesis is recommended",
               a.automation(N, workstream_id="w3", repeated_workflow=True, qa_pass_rate=0.9,
                            build_cost_estimate=5000, margin_improvement_estimate=0.3, store=st)["ok"])

            ck("10. productization without proof is refused",
               not a.productize(N, workstream_id="w3", proof_present=False, free_layer="f",
                                paid_layers=["p"], build_approval_ref="lamar", store=st)["ok"])
            ck("11. productization without build approval is refused",
               not a.productize(N, workstream_id="w3", proof_present=True, free_layer="f",
                                paid_layers=["p"], build_approval_ref="", store=st)["ok"])
            ck("12. productization with proof + approval + paid layer is recorded",
               a.productize(N, workstream_id="w3", proof_present=True, free_layer="lite",
                            paid_layers=["pro"], build_approval_ref="lamar", store=st)["ok"])

            ck("13. a partnership without approval is refused",
               not g.partnership(N, partner_type="agency", value_proposition="distribution", store=st)["ok"])
            ck("14. a revenue-share partnership without legal review is refused",
               not g.partnership(N, partner_type="agency", value_proposition="dist", revenue_share=True,
                                 approval_ref="lamar", store=st)["ok"])
            ck("15. an approved, legally-reviewed revenue-share partnership is recorded",
               g.partnership(N, partner_type="agency", value_proposition="dist", revenue_share=True,
                             approval_ref="lamar", legal_review_ref="atty", store=st)["ok"])

            ck("16. expansion without evidence is refused",
               not g.expand(N, workstream_id="w3", path="new_geography", evidence_present=False,
                            capacity_ok=True, approval_ref="lamar", store=st)["ok"])
            ck("17. expansion without a capacity check is refused",
               not g.expand(N, workstream_id="w3", path="new_geography", evidence_present=True,
                            capacity_ok=False, approval_ref="lamar", store=st)["ok"])
            ck("18. expansion without approval is refused",
               not g.expand(N, workstream_id="w3", path="higher_ticket", evidence_present=True,
                            capacity_ok=True, approval_ref="", store=st)["ok"])
            ck("19. a fully-gated expansion is approved",
               g.expand(N, workstream_id="w3", path="higher_ticket", evidence_present=True,
                        capacity_ok=True, approval_ref="lamar", store=st)["ok"])

            acq = g.acquisition_watch(N, candidate="MicroSaaS X", candidate_type="micro_saas",
                                      strategic_rationale="under-monetized, fits our distribution",
                                      valuation_assumptions=["~2x ARR, unverified"], store=st)["acquisition"]
            ck("20. an acquisition candidate is research-only with labeled valuation assumptions",
               acq["status"] == "watch" and acq["valuation_is_assumption"])
            ck("21. acquisition outreach without approval + legal review is refused",
               not g.acquisition_outreach(N, acq["acquisition_id"], approval_ref="lamar", legal_review_ref="", store=st)["ok"])

            ck("22. reinvestment without a reserve is refused",
               not g.reinvest(N, period="2026-06", allocations={"support_qa": 100}, reserve_pct=0.0,
                              approval_ref="lamar", store=st)["ok"])
            ck("23. reinvestment without approval is refused",
               not g.reinvest(N, period="2026-06", allocations={"support_qa": 100}, reserve_pct=0.2,
                              approval_ref="", store=st)["ok"])
            ck("24. reinvestment that starves quality/support while funding sales is refused",
               not g.reinvest(N, period="2026-06", allocations={"sales_tests": 500, "support_qa": 0},
                              reserve_pct=0.2, approval_ref="lamar", store=st)["ok"])
            ck("25. a balanced, reserved, approved reinvestment plan is recorded",
               g.reinvest(N, period="2026-06", allocations={"sales_tests": 500, "support_qa": 200,
                          "cash_reserve": 300}, reserve_pct=0.2, approval_ref="lamar", store=st)["ok"])

            d = api.dashboard(N, store=st)
            ck("26. the dashboard assembles allocations + acquisition watch + honest scaling rules",
               d["ok"] and d["allocations"] and "human-only" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_compounding_engine", "green" if green else "red",
                files_observed=["anima/compounding/allocator.py", "anima/compounding/growth.py"],
                report_paths=["reports/compounding_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nCOMPOUNDING-ENGINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
