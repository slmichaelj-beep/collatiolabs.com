#!/usr/bin/env python3
"""certify_sales_core — buyer psychology + lead sourcing/qualification + discovery."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial.sales_mastery import core   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("SALES CORE — buyer psychology, leads, qualification, discovery")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SalesCoreCert"
        # outreach blocked before buyer pain is defined
        ck("1. outreach is blocked before buyer pain is defined",
           not core.outreach_ready(N, "offer1", store=st)["ready"])
        core.buyer_psychology(N, "offer1", persona="solo freelancer",
                              economic_pain="5h/mo lost to invoicing", desired_outcome="1-click invoices",
                              objections=["price"], store=st)
        ck("2. with economic pain defined, outreach becomes ready",
           core.outreach_ready(N, "offer1", store=st)["ready"])
        # bad source refused
        ck("3. a non-approved lead source (scraped/spam) is refused",
           not core.add_lead(N, "offer1", source="purchased list", store=st)["ok"])
        l = core.add_lead(N, "offer1", source="referral", company="Acme", store=st)
        ck("4. an approved-source lead is added", l["ok"])
        lid = l["lead"]["lead_id"]
        # qualification gates
        q_bad = core.qualify(N, lid, pain_fit="low", store=st)
        ck("5. low pain-fit disqualifies the lead",
           q_bad["lead"]["status"] == "disqualified"
           and not core.can_contact(N, lid, store=st)["allowed"])
        l2 = core.add_lead(N, "offer1", source="inbound_website", store=st)["lead"]
        core.qualify(N, l2["lead_id"], pain_fit="high", budget_fit="high", authority_fit="decision_maker",
                     timing="now", store=st)
        ck("6. a high-fit lead is qualified + contactable",
           core.can_contact(N, l2["lead_id"], store=st)["allowed"])
        l3 = core.add_lead(N, "offer1", source="event", store=st)["lead"]
        core.qualify(N, l3["lead_id"], pain_fit="high", budget_fit="unknown", store=st)
        ck("7. an unknown-fit lead needs research (not contacted yet)",
           not core.can_contact(N, l3["lead_id"], store=st)["allowed"])
        # discovery
        core.discovery_plan(N, "opp1", store=st)
        d = core.discovery_complete(N, "opp1", pain_confirmed=True, budget_status="confirmed",
                                    timeline="this quarter", store=st)
        ck("8. discovery with pain+budget+timeline qualifies + advances",
           d["advances"] and d["discovery"]["qualification"] == "qualified")
        d2 = core.discovery_complete(N, "opp1", pain_confirmed=False, store=st)
        ck("9. discovery without confirmed pain does NOT advance", not d2["advances"])
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_sales_core", "green" if green else "red",
                files_observed=["anima/commercial/sales_mastery/core.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSALES-CORE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
