#!/usr/bin/env python3
"""certify_foundry_evaluation — strategy council + market validation + simulation."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.foundry import evaluation as ev   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FOUNDRY EVALUATION — council, market validation, simulation (truth-disciplined)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        idea = {"idea_id": "idea_1", "revenue_goal": 1000000, "budget": 10000, "budget_limit": 10000}

        # ---- strategy council --------------------------------------------------------------
        c = ev.strategy_council("EvalCert", idea, store=st)
        ck("1. all 13 council roles produce a vote", len(c["votes"]) == 13)
        ck("2. disagreements are preserved", isinstance(c["major_disagreements"], list))
        # skeptic no_go + few go's => not forced to go
        ri = {"Skeptic / Devil's Advocate": {"vote": "no_go", "risk": "no proven demand"}}
        c2 = ev.strategy_council("EvalCert", idea, role_inputs=ri, store=st)
        ck("3. the skeptic can drive a no_go / research_more (council not forced to go)",
           c2["recommendation"] in ("no_go", "research_more"))
        # strong go consensus can reach go
        ri_go = {r: {"vote": "go"} for r in ev.COUNCIL_ROLES}
        c3 = ev.strategy_council("EvalCert", idea, role_inputs=ri_go, store=st)
        ck("4. a strong consensus CAN reach go (not artificially suppressed)", c3["recommendation"] == "go")

        # ---- market validation -------------------------------------------------------------
        mv = ev.market_validation("EvalCert", idea, claims=[
            {"text": "5h/mo on invoicing", "source": "survey"},
            {"text": "big TAM", "assumption": True},
            {"text": "everyone switches"}], store=st)
        ck("5. sourced claim kept, assumption labeled, UNSUPPORTED claim refused",
           any(x["kind"] == "sourced" for x in mv["claims"])
           and any(x["kind"] == "assumption" for x in mv["claims"])
           and "everyone switches" in mv["refused_unsupported_claims"])
        ck("6. verdict is from the bounded set + unknowns surfaced",
           mv["verdict"] in ev.MARKET_VERDICTS and mv["unknowns"])

        # ---- simulation --------------------------------------------------------------------
        sim = ev.simulation("EvalCert", idea, price=20, conversion=0.02, cac=30, monthly_cost=500, store=st)
        ck("7. simulation gives best/base/worst (never a single certain number)",
           set(sim["scenarios"]) == {"worst", "base", "best"})
        ck("8. assumptions explicit + highest-risk variable named + no fake certainty",
           sim["assumptions"] and sim["highest_risk_variable"]
           and "not a guarantee" in sim["statement"].lower())
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_foundry_evaluation", "green" if green else "red",
                files_observed=["anima/foundry/evaluation.py"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDRY-EVALUATION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
