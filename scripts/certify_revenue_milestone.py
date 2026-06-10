#!/usr/bin/env python3
"""certify_revenue_milestone — the $16k net-profit milestone machine, every gate.

Target/deadline/budget exist; net profit = cash − costs − spend; pipeline/invoice are not cash;
collected cash needs payment evidence AND a registered payment path; a payment path is human-only;
spend needs approval + can't exceed budget; gap + daily pace computed; with no payment path the
milestone is BLOCKED (surfaced, not hidden); offers carry fulfillment limitations; resource requests
tie to the milestone; the daily briefing + dashboard render honestly.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.revenue import milestone as m, milestone_api as api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("REVENUE MILESTONE — $16,000 net profit by 2026-06-28 (governed strike machine)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "MileCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            m.seed_offers(N, store=st)
            offs = m.offers(N, store=st)
            ck("1. three milestone offers exist with a single lead offer",
               len(offs) == 3 and sum(1 for o in offs if o.get("lead")) == 1)
            ck("2. every offer states a fulfillment limitation (no revenue guarantee)",
               all("guarantee" in o["limitation"] or "advisory" in o["limitation"] for o in offs))

            b0 = m.board(N, today="2026-06-10", store=st)
            ck("3. the board carries target/deadline/budget",
               b0["target_net_profit"] == 16000 and b0["deadline"] == "2026-06-28" and b0["starting_budget"] == 1000)
            ck("4. with no payment path, the milestone is BLOCKED (surfaced)",
               b0["status"].startswith("BLOCKED") and b0["payment_path"]["blocking"])
            ck("5. days-left + required daily pace are computed", b0["days_left"] == 18 and b0["required_net_per_day"] > 0)

            ck("6. collected cash with no payment path is refused",
               not m.record_cash(N, offer_id="mo_ai_revenue_audit", amount=2500,
                                 payment_evidence_ref="x", store=st)["ok"])
            ck("7. registering a payment path needs human approval (Vera can't create accounts)",
               not m.register_payment_path(N, kind="stripe_invoice", approval_ref="", store=st)["ok"])
            m.register_payment_path(N, kind="stripe_invoice", approval_ref="lamar", store=st)
            ck("8. cash with no payment evidence is refused (not counted)",
               not m.record_cash(N, offer_id="mo_ai_revenue_audit", amount=2500, payment_evidence_ref="", store=st)["ok"])
            ck("9. cash with evidence + a payment path counts",
               m.record_cash(N, offer_id="mo_ai_revenue_audit", amount=2500, payment_evidence_ref="ch_1", store=st)["ok"])

            ck("10. spend without approval is refused",
               not m.record_spend(N, amount=150, note="tooling", approval_ref="", store=st)["ok"])
            ck("11. spend exceeding the $1000 budget is refused",
               not m.record_spend(N, amount=1500, note="too much", approval_ref="lamar", store=st)["ok"])
            m.record_spend(N, amount=150, note="offer page polish", approval_ref="lamar", store=st)
            m.record_cost(N, amount=100, note="direct fulfillment", store=st)

            b1 = m.board(N, today="2026-06-12", store=st)
            ck("12. net profit = collected − costs − spend",
               b1["net_profit"] == round(2500 - 100 - 150, 2))
            ck("13. the gap to $16k is computed from NET (not collected)", b1["remaining_gap"] == round(16000 - 2250, 2))
            ck("14. with a payment path + cash, status is no longer blocked", b1["status"] == "in progress")

            # collect to milestone
            for i in range(6):
                m.record_cash(N, offer_id="mo_workforce_sprint", amount=2500, payment_evidence_ref="ch_%d" % i, store=st)
            b2 = m.board(N, today="2026-06-20", store=st)
            ck("15. when net >= $16k the board reports MILESTONE MET",
               b2["net_profit"] >= 16000 and b2["status"] == "MILESTONE MET")

            db = m.daily_briefing(N, today="2026-06-12", store=st)
            ck("16. the daily briefing reports cash/net/gap/pace + approvals needed",
               "cash_collected" in db and "required_net_per_day" in db and db["approvals_needed_today"])

            ck("17. a resource request with no milestone impact is refused",
               not m.resource_request(N, resource_needed="x", why_needed="y", milestone_impact="",
                                      cost="$0", minimum_option="a", recommended_option="b",
                                      risk_if_not_provided="z", store=st)["ok"])
            rr = m.resource_request(N, resource_needed="business email", why_needed="credible sender",
                                    milestone_impact="raises reply rate", cost="$0–$100",
                                    minimum_option="use existing", recommended_option="dedicated domain inbox",
                                    risk_if_not_provided="lower conversion", store=st)
            ck("18. a milestone-tied resource request is approval-gated", rr["ok"] and rr["request"]["approval_required"])

            # standing blockers on a fresh store (no payment path) must include payment path
            N2 = "MileFresh"; cs.STORE = st
            srr = m.standing_resource_requests(N2, store=st)
            ck("19. with no payment path, the standing requests surface it as a 100% blocker",
               any("payment" in r["resource_needed"].lower() for r in srr))
            ck("20. outreach approval is always a standing requirement (Vera never sends)",
               any("outreach" in r["resource_needed"].lower() or "outreach" in r["why_needed"].lower() for r in srr))

            d = api.dashboard(N, store=st)
            ck("21. the /revenue/cash dashboard assembles board + offers + briefing + resource requests",
               d["ok"] and d["offers"] and "daily_briefing" in d and "resource_requests" in d)
            ck("22. the dashboard's honesty note keeps cash≠pipeline + human-only sending",
               "pipeline" in d["honesty"].lower() and "human-only" in d["honesty"].lower())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_revenue_milestone", "green" if green else "red",
                files_observed=["anima/revenue/milestone.py", "anima/revenue/milestone_api.py"],
                report_paths=["reports/financial_milestone_16000_plan.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nREVENUE-MILESTONE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
