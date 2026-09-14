#!/usr/bin/env python3
"""certify_revenue_ops_setup — Collatio revenue-operations rails, every gate.

No raw credentials stored (secret-looking values rejected); account registry tracks accounts as
governed records; readiness flags reject secret pointers + gate outreach/offer approval; payment-path
+ business-bank statuses are visible and gate launch; operator boundary (draft vs approval vs never)
enforced; account requests are specific + approval-gated; launch checklist surfaces blockers + the
exact asks for Lamar. Cash-vs-pipeline truth + outreach-approval are covered by the milestone cert.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.revenue import revops as ro, milestone as m, milestone_api as api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("REVENUE OPS SETUP — account registry / readiness / operator boundary / launch checklist")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "RevOpsCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            # no raw credentials
            ck("1. an account whose pointer contains a card number is refused",
               not ro.register_account(N, service_name="Bank", category="bank",
                                       raw_value_check="card 4242424242424242", store=st)["ok"])
            ck("2. an account whose pointer contains a Stripe secret key is refused",
               not ro.register_account(N, service_name="Stripe", category="payments",
                                       credentials_location="sk_live_abc123XYZ", store=st)["ok"])
            acc = ro.register_account(N, service_name="Stripe", category="payments",
                                      purpose="invoicing", credentials_location="password_manager", store=st)["account"]
            ck("3. a clean account record stores NO raw credentials + is regulated-risk",
               acc["raw_credentials_stored"] is False and acc["risk_level"] == "regulated"
               and acc["credentials_location"] == "password_manager_ref_only")
            ck("4. payment/bank accounts are KYC-required (human)", acc["kyc_required"])

            # readiness
            r0 = ro.readiness(N, store=st)
            ck("5. fresh readiness is not cleared to launch + lists blockers",
               not r0["cleared_to_launch"] and r0["blockers"])
            ck("6. a readiness pointer that looks like a secret is refused",
               not ro.set_readiness(N, "payment_path", "active", pointer="routing 021000021", store=st)["ok"])
            ck("7. outreach_approval=approved without an approval ref is refused",
               not ro.set_readiness(N, "outreach_approval", "approved", store=st)["ok"])
            ck("8. a safe readiness pointer is accepted",
               ro.set_readiness(N, "sender_email", "active", pointer="lamar@collatiolabs.com", store=st)["ok"])

            # payment path drives readiness via the milestone tracker
            ck("9. with no payment path, readiness shows payment_path != active",
               ro.readiness(N, store=st)["flags"]["payment_path"] != "active")
            m.register_payment_path(N, kind="stripe_invoice", approval_ref="lamar", store=st)
            ck("10. after Lamar registers a payment path, readiness shows it active",
               ro.readiness(N, store=st)["flags"]["payment_path"] == "active")
            ck("11. business bank still missing => still PARTIALLY BLOCKED (surfaced)",
               any("bank" in b for b in ro.readiness(N, store=st)["blockers"]))

            # full clear path
            ro.set_readiness(N, "offer_approval", "approved", approval_ref="lamar", store=st)
            ro.set_readiness(N, "buyer_list", "approved", pointer="15 warm names", store=st)
            ro.set_readiness(N, "outreach_approval", "approved", approval_ref="lamar", store=st)
            ck("12. with payment+sender+offer+buyers+outreach approved, cleared_to_launch is true",
               ro.readiness(N, store=st)["cleared_to_launch"])

            # operator boundary
            ck("13. Vera may draft an invoice (no approval needed)", ro.can(N, "draft_invoice")["allowed"])
            ck("14. sending an invoice needs approval", not ro.can(N, "send_invoice")["allowed"])
            ck("15. opening an account needs approval", not ro.can(N, "open_account")["allowed"])
            ck("16. storing a bank number is NEVER allowed", not ro.can(N, "store_bank_number", approval_ref="lamar")["allowed"])

            # setup packets + launch checklist
            ck("17. the bank setup packet says Vera never stores the login",
               any("login" in x or "account number" in x for x in ro.bank_setup_packet()["vera_never"]))
            ck("18. the Stripe checklist records only a password-manager pointer",
               ro.stripe_setup_checklist()["vera_records"]["credentials"] == "password_manager_ref_only")
            lc = ro.launch_checklist(N, store=st)
            ck("19. the launch checklist lists the exact questions for Lamar", len(lc["questions_for_lamar"]) == 10)

            # account request specificity
            ck("20. an account request with no milestone impact is refused",
               not ro.account_request(N, needed="phone", why_needed="calls", milestone_impact="",
                                      minimum_option="Google Voice", recommended_option="OpenPhone", store=st)["ok"])
            ck("21. a specific, approval-gated account request is recorded",
               ro.account_request(N, needed="business email", why_needed="credible sender",
                                  milestone_impact="raises reply rate", minimum_option="existing",
                                  recommended_option="Workspace inbox", store=st)["request"]["approval_required"])

            d = api.dashboard(N, store=st)
            ck("22. /revenue/cash now carries the launch-readiness row + cleared flag",
               "readiness" in d and "cleared_to_launch" in d and "launch_blockers" in d)
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_revenue_ops_setup", "green" if green else "red",
                files_observed=["anima/revenue/revops.py", "anima/revenue/milestone_api.py"],
                report_paths=["reports/revenue_ops_setup_packet.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nREVENUE-OPS-SETUP CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
