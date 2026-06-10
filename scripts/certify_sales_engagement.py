#!/usr/bin/env python3
"""certify_sales_engagement — messaging + followup + demo + objections + negotiation/closing."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial.sales_mastery import engagement as eng   # noqa: E402
from anima.company_operator import approvals   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("SALES ENGAGEMENT — messaging, followup, demo, objections, negotiation/closing")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SalesEngCert"
        # messaging
        ck("1. a message without buyer pain is refused",
           not eng.draft_message(N, mtype="cold_email", buyer_pain="", outcome="save time", store=st)["ok"])
        ck("2. a spam / fake-urgency message is blocked",
           not eng.draft_message(N, mtype="cold_email", buyer_pain="invoicing pain",
                                 outcome="ACT NOW limited time guaranteed", store=st)["ok"])
        ck("3. an ROI %% claim with no proof is blocked",
           not eng.draft_message(N, mtype="cold_email", buyer_pain="invoicing pain",
                                 outcome="cut costs 40%", store=st)["ok"])
        m = eng.draft_message(N, mtype="cold_email", buyer_pain="5h/mo on invoicing",
                              outcome="1-click invoices", proof_point="pilot saved 4h/mo", store=st)
        ck("4. a clean, evidence-backed message drafts (send still gated)",
           m["ok"] and m["message"]["requires_approval_to_send"])
        # sending gated
        ck("5. sending without approval (and below L3) is blocked",
           not eng.can_send(N, m["message"], authority_level=0, store=st)["allowed"])
        ap = approvals.create(N, "Send outreach", "send", store=st)["approval"]
        approvals.decide(N, ap["approval_id"], "approved", store=st)
        ck("6. sending WITH an approved packet is allowed",
           eng.can_send(N, m["message"], approval_ref=ap["approval_id"], store=st)["allowed"])
        # followup discipline
        ck("7. opt-out stops follow-up",
           eng.schedule_followup(N, "lead1", touch_count=1, opted_out=True, store=st)["action"] == "stop")
        ck("8. max touches routes to nurture (no harassment)",
           eng.schedule_followup(N, "lead1", touch_count=eng.MAX_TOUCHES, store=st)["action"] == "nurture")
        # demo
        ck("9. a demo claim NOT in live capabilities is a fake capability (blocked)",
           not eng.demo_claim_allowed("teleportation", live_capabilities=["invoicing"])["allowed"]
           and eng.demo_claim_allowed("invoicing", live_capabilities=["invoicing"])["allowed"])
        # objections
        ck("10. an unsupported ROI rebuttal is refused; an evidence-linked one is allowed",
           not eng.objection_response(N, "too expensive", response="you'll save 50%", store=st)["ok"]
           and eng.objection_response(N, "too expensive", response="pilots saved 4h/mo",
                                      proof_needed=["pilot data"], store=st)["ok"])
        # negotiation + closing
        plan = eng.negotiation_plan(N, list_price=1000, floor_price=800, discount_authority_pct=15, store=st)["plan"]
        ck("11. a discount beyond authority is blocked; within authority allowed",
           not eng.discount_allowed(plan, proposed_price=700)["allowed"]
           and eng.discount_allowed(plan, proposed_price=900)["allowed"])
        ck("12. a binding close requires an approved packet",
           not eng.can_close(N, store=st)["allowed"])
        ap2 = approvals.create(N, "Close deal", "legal", store=st)["approval"]
        approvals.decide(N, ap2["approval_id"], "approved", store=st)
        ck("12b. ...and is allowed once approved", eng.can_close(N, approval_ref=ap2["approval_id"], store=st)["allowed"])
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_sales_engagement", "green" if green else "red",
                files_observed=["anima/commercial/sales_mastery/engagement.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSALES-ENGAGEMENT CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
