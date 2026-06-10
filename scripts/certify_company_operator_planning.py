#!/usr/bin/env python3
"""certify_company_operator_planning — idea->validation->committee->business case->blueprint.

Planning only: no external action, no spend. Market claims cite sources or are labeled
assumptions (unsupported claims refused). The committee is willing to say NO. The blueprint
requires approval before execution.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company_operator import planning as pl   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMPANY OPERATOR PLANNING — idea to blueprint, planning only, no fake certainty")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "PlanCert"

        # ---- idea intake -------------------------------------------------------------------
        thin = pl.intake(N, "an app idea", store=st)
        ck("1. an incomplete idea is 'draft' with missing_fields listed",
           thin["status"] == "draft" and "budget_limit" in thin["missing_fields"])
        full = pl.intake(N, "local-first invoicing for freelancers", fields={
            "problem": "freelancers hate invoicing", "target_customer": "solo freelancers",
            "proposed_solution": "1-click local invoicing", "budget_limit": 10000,
            "revenue_goal": 1000000, "timeline": "3 years", "jurisdiction": "US-DE",
            "risk_tolerance": "medium", "differentiation": "fully local + private"}, store=st)
        ck("2. a complete idea is ready_for_validation", full["status"] == "ready_for_validation")

        # ---- market validation: unsupported claims refused --------------------------------
        v = pl.validate_market(N, full, claims=[
            {"text": "freelancers spend 5h/mo on invoicing", "source": "survey-2025"},
            {"text": "TAM is huge", "assumption": True},
            {"text": "everyone will switch instantly"}], store=st)  # last has no source/assumption
        ck("3. a sourced claim is kept; an assumption is kept+labeled; an UNSUPPORTED claim is refused",
           any(c["kind"] == "sourced" for c in v["claims"])
           and any(c["kind"] == "assumption" for c in v["claims"])
           and "everyone will switch instantly" in v["refused_unsupported_claims"])

        # ---- committee can say NO ----------------------------------------------------------
        bad = pl.intake(N, "vague idea", fields={"problem": "x", "target_customer": "y",
                                                 "proposed_solution": "z"}, store=st)
        vbad = pl.validate_market(N, bad, claims=[{"text": "trust me"}], store=st)
        cbad = pl.committee(N, bad, vbad, store=st)
        ck("4. the committee says no_go / research_more on a weak, unfunded, undifferentiated idea",
           cbad["recommendation"] in ("no_go", "research_more") and cbad["kill_reasons"])

        good = pl.committee(N, full, v, store=st)
        ck("5. a complete, differentiated, evidenced idea can get go / research_more (not forced)",
           good["recommendation"] in ("go", "research_more"))

        # ---- business case + blueprint ------------------------------------------------------
        bc = pl.business_case(N, full, monthly_cost=500, store=st)
        ck("6. business case has best/base/worst + runway + kill thresholds",
           set(bc["scenarios"]) == {"worst", "base", "best"} and bc["runway_months"] == 20
           and bc["kill_thresholds"])
        bp = pl.blueprint(N, full, v, good, bc, store=st)
        ck("7. the blueprint is a DRAFT that requires approval before execution",
           bp["status"] == "draft" and bp["requires_approval_before_execution"] is True)
        ck("8. the blueprint records the market unknowns + go/no-go (no fabricated certainty)",
           bp["sections"]["go_no_go"] == good["recommendation"]
           and "market_unknowns" in bp["sections"])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_company_operator_planning", "green" if green else "red",
                files_observed=["anima/company_operator/planning.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMPANY-OPERATOR-PLANNING CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
