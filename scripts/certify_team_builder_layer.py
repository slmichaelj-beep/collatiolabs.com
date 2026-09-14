#!/usr/bin/env python3
"""certify_team_builder_layer — Team Builder / delegation / product-support, every gate.

Org needs escalation + quality policy; role needs responsibilities + deliverables + authority bound.
Delegation needs context + deliverables + success criteria; external needs approval; paid needs
budget; regulated needs professional review. Work orders need a QA pass + deliverable to close.
Agents can't send/spend/sign. Vendor hire needs approval + budget. Deliverable review escalates
legal/financial + claim-checks customer-facing. Support org needs triage + escalation + capacity.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.teams import org, delegation as dg, quality as q, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("TEAM BUILDER LAYER — org / roles / delegation / work-orders / agents / vendors / QA")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "TeamCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            nopol = org.design_org(N, product_or_offer_id="p1", mission="support X", store=st)
            ck("1. an org without escalation/quality policy is refused", not nopol["ok"])
            o = org.design_org(N, product_or_offer_id="p1", mission="support X", org_type="agent_augmented",
                               escalation_policy="page Lamar on legal/financial", quality_policy="QA before delivery", store=st)["org"]
            ck("2. an org with policies is created", o["org_id"])
            noresp = org.add_role(N, o["org_id"], role_name="QA", role_type="ai_agent",
                                  responsibilities=[], deliverables=["report"], store=st)
            ck("3. a role with no responsibilities is refused", not noresp["ok"])
            nodel = org.add_role(N, o["org_id"], role_name="QA", role_type="ai_agent",
                                 responsibilities=["check work"], deliverables=[], store=st)
            ck("4. a role with no deliverables is refused", not nodel["ok"])
            role = org.add_role(N, o["org_id"], role_name="Support Agent", role_type="ai_agent",
                                responsibilities=["triage tickets"], deliverables=["triaged queue"],
                                authority_level="L1", store=st)["role"]
            ck("5. a complete role has authority bounds + forbidden actions",
               role["authority_level"] == "L1" and role["forbidden_actions"])

            noctx = dg.delegate(N, role_id=role["role_id"], task="t", objective="o",
                                deliverables=["d"], success_criteria=["s"], context_refs=[], store=st)
            ck("6. a delegation with no context is refused", not noctx["ok"])
            nosucc = dg.delegate(N, role_id=role["role_id"], task="t", objective="o",
                                 deliverables=["d"], success_criteria=[], context_refs=["c"], store=st)
            ck("7. a delegation with no success criteria is refused", not nosucc["ok"])
            extnoappr = dg.delegate(N, role_id=role["role_id"], task="t", objective="o", deliverables=["d"],
                                    success_criteria=["s"], context_refs=["c"], is_external=True, store=st)
            ck("8. external delegation without approval is refused", not extnoappr["ok"])
            paidnobud = dg.delegate(N, role_id=role["role_id"], task="t", objective="o", deliverables=["d"],
                                    success_criteria=["s"], context_refs=["c"], is_paid=True, store=st)
            ck("9. paid delegation without budget is refused", not paidnobud["ok"])
            good = dg.delegate(N, role_id=role["role_id"], task="triage", objective="clear queue",
                               deliverables=["queue"], success_criteria=["<1h response"], context_refs=["ctx"], store=st)
            ck("10. a complete delegation is accepted with a review requirement", good["ok"] and good["delegation"]["review_required"])

            wo = dg.create_work_order(N, org_id=o["org_id"], role_id=role["role_id"], title="Triage Mon",
                                      description="triage", deliverables=["triaged"], store=st)["work_order"]
            ck("11. a work order cannot be done without a QA pass",
               not dg.complete_work_order(N, wo["work_order_id"], qa_passed=False, deliverable_ref="r", store=st)["ok"])
            ck("12. a work order cannot be done without a deliverable ref",
               not dg.complete_work_order(N, wo["work_order_id"], qa_passed=True, deliverable_ref="", store=st)["ok"])
            ck("13. a QA-passed work order with a deliverable can close",
               dg.complete_work_order(N, wo["work_order_id"], qa_passed=True, deliverable_ref="queue#1", store=st)["ok"])

            at = dg.create_agent_team(N, org_id=o["org_id"], mission="research", agents=["scout"],
                                      allowed_tools=["read"], store=st)["agent_team"]
            ck("14. an agent team forbids external/spend/sign tools", "send_external_message" in at["forbidden_tools"])
            ck("15. an agent cannot send an external message", not dg.agent_can(N, "send_external_message")["allowed"])
            ck("16. an agent cannot spend", not dg.agent_can(N, "spend")["allowed"])
            ck("17. an agent's allowed action output is draft-until-reviewed",
               "draft" in dg.agent_can(N, "summarize")["note"])

            ck("18. hiring a vendor without approval is refused",
               not dg.hire_vendor(N, vendor_name="Acme Dev", category="developer", approval_ref="", store=st)["ok"])
            ck("19. paid vendor work without budget is refused",
               not dg.hire_vendor(N, vendor_name="Acme Dev", category="developer", approval_ref="lamar", budget_ref="", store=st)["ok"])
            ck("20. an approved, budgeted vendor can be engaged (contract required)",
               dg.hire_vendor(N, vendor_name="Acme Dev", category="developer", approval_ref="lamar", budget_ref="b1", store=st)["vendor"]["contract_required"])

            ck("21. a legal/financial deliverable escalates (not auto-accepted by Vera)",
               q.review(N, work_order_id=wo["work_order_id"], review_type="legal_professional",
                        criteria=["valid"], passed=True, reviewer="vera", store=st)["review"]["result"] == "escalated")
            ck("22. a customer-facing deliverable with no proof is rejected",
               q.review(N, work_order_id=wo["work_order_id"], review_type="customer_promise", criteria=["claim"],
                        passed=True, customer_facing=True, claim_proof_ok=False, store=st)["review"]["result"] == "rejected")
            ck("23. poor performance recommends coach/replace",
               q.performance(N, role_id=role["role_id"], period="2026-06", completed=2, overdue=5,
                             quality_pass_rate=0.3, store=st)["performance"]["recommendation"] == "replace")
            ck("24. a budget-overrun escalation is high-severity + blocks spend",
               q.escalate(N, trigger="budget_overrun", summary="over by 40%", store=st)["escalation"]["blocks_spend"])

            ck("25. a support org without triage/escalation is refused",
               not q.build_support_org(N, product_id="p1", triage_policy="", escalation_path="x",
                                       support_promise="24h", capacity_ok=True, store=st)["ok"])
            ck("26. a support promise without capacity check is refused",
               not q.build_support_org(N, product_id="p1", triage_policy="t", escalation_path="e",
                                       support_promise="24h", capacity_ok=False, store=st)["ok"])
            ck("27. a capacity-checked support org with approved templates is built",
               q.build_support_org(N, product_id="p1", triage_policy="t", escalation_path="e",
                                   support_promise="24h", capacity_ok=True, response_templates=["hi"],
                                   templates_approved=True, store=st)["ok"])

            d = api.dashboard(N, store=st)
            ck("28. the dashboard assembles orgs/work-orders/agents/vendors/escalations",
               d["ok"] and d["roles_total"] >= 1 and "review" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_team_builder_layer", "green" if green else "red",
                files_observed=["anima/teams/org.py", "anima/teams/delegation.py", "anima/teams/quality.py"],
                report_paths=["reports/team_builder_delegation_layer.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nTEAM-BUILDER-LAYER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
