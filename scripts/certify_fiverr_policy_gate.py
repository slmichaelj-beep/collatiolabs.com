#!/usr/bin/env python3
"""certify_fiverr_policy_gate — the Fiverr acceptability gate, every block + every allow.

Public-doc reading allowed; manual review allowed; own-account ops allowed; order fulfillment allowed.
Scraping / mass messaging / fake reviews / off-platform payment / third-party-ToS / regulated services
all BLOCKED. Unknown source => NEEDS_HUMAN_REVIEW (never auto-allowed).
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.marketplaces.fiverr import policy as p  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FIVERR POLICY GATE — blocks + allows")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "FivPol"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            def C(**kw): return p.classify(N, store=st, **kw)
            ck("1. reading public help docs is allowed",
               C(action="read_help_doc", source_policy_status="known_allowed")["classification"] == "ALLOWED_PUBLIC_DOC_RESEARCH")
            ck("2. manual market review is allowed",
               C(action="manual_review_category", source_policy_status="known_allowed")["classification"] == "ALLOWED_MANUAL_MARKET_REVIEW")
            ck("3. operating own account (draft) is allowed",
               C(action="own_account_draft_gig", source_policy_status="known_allowed")["allowed"])
            ck("4. fulfilling a purchased order is allowed",
               C(action="fulfill_order", source_policy_status="known_allowed")["classification"] == "ALLOWED_ORDER_FULFILLMENT")
            ck("5. automated bulk scraping is BLOCKED",
               C(action="scrape_gigs", uses_automation=True, bulk_extraction=True)["classification"] == "BLOCKED_UNAUTHORIZED_SCRAPING")
            ck("6. mass messaging is BLOCKED",
               C(action="message_buyers", sends_messages=True, mass_messaging=True)["classification"] == "BLOCKED_MASS_MESSAGING")
            ck("7. fake reviews/engagement is BLOCKED",
               C(action="boost", fake_review_or_engagement=True)["classification"] == "BLOCKED_FAKE_REVIEW_OR_ENGAGEMENT")
            ck("8. off-platform payment is BLOCKED (ToS circumvention)",
               C(action="collect_payment", off_platform_payment=True)["classification"] == "BLOCKED_TOS_CIRCUMVENTION")
            ck("9. a third-party-ToS-violating service is BLOCKED",
               C(action="offer_service", third_party_tos_violation=True)["classification"] == "BLOCKED_THIRD_PARTY_TOS_VIOLATION")
            ck("10. a regulated/prohibited service is BLOCKED",
               C(action="offer_service", regulated_or_prohibited_service=True)["classification"] == "BLOCKED_REGULATED_OR_PROHIBITED_SERVICE")
            ck("11. an unknown source => NEEDS_HUMAN_REVIEW (not auto-allowed)",
               C(action="browse", source_policy_status="unknown")["classification"] == "NEEDS_HUMAN_REVIEW")
            ck("12. automated 'research' at scale routes to human review",
               C(action="research", uses_automation=True, source_policy_status="known_allowed")["classification"] == "NEEDS_HUMAN_REVIEW")
            ck("13. is_allowed() is true only for ALLOWED_* classes",
               p.is_allowed(C(action="read_help_doc", source_policy_status="known_allowed"))
               and not p.is_allowed(C(action="scrape_gigs", uses_automation=True, bulk_extraction=True)))
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_fiverr_policy_gate", "green" if green else "red",
                files_observed=["anima/marketplaces/fiverr/policy.py"],
                report_paths=["reports/fiverr_policy_verdict.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nFIVERR-POLICY-GATE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
