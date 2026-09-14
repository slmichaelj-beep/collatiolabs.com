#!/usr/bin/env python3
"""certify_foundry_execution — experiments, kill/pivot/scale, capital allocation, vendor."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.foundry import core, execution as ex   # noqa: E402
from anima.company_operator import authority, approvals, budget   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FOUNDRY EXECUTION — experiments, kill/pivot/scale, capital, vendor (governed)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "FoundryExecCert"
        core.set_preflight(N, total_capital=25000, max_loss=10000, allowed_jurisdictions=["US-DE"],
                           max_active_ventures=3, store=st)
        v = core.create_venture(N, "Invoicer", "idea_1", jurisdiction="US-DE", store=st)["venture"]
        vid = v["venture_id"]

        # ---- experiments require success + kill criteria -----------------------------------
        ck("1. an experiment without success_criteria is refused",
           not ex.create_experiment(N, vid, "demand exists", "landing page", kill_criteria=["<1% signup"], store=st)["ok"])
        ck("2. an experiment without kill_criteria is refused",
           not ex.create_experiment(N, vid, "demand exists", "landing page", success_criteria=[">5% signup"], store=st)["ok"])
        e = ex.create_experiment(N, vid, "demand exists", "landing page", budget=200,
                                 success_criteria=[">5% signup"], kill_criteria=["<1% signup"], store=st)
        ck("3. a complete experiment is created (draft)", e["ok"] and e["experiment"]["status"] == "draft")

        # ---- a PAID experiment cannot run without approved budget --------------------------
        r = ex.run_experiment(N, vid, e["experiment"]["experiment_id"], store=st)
        ck("4. a PAID experiment cannot run without an approved packet/budget", not r["ok"])
        ap = approvals.create(N, "Run landing test", "spend", cost=200, store=st)["approval"]
        approvals.decide(N, ap["approval_id"], "approved", store=st)
        budget.approve_budget(N, total=5000, per_transaction_cap=1000, store=st)
        r = ex.run_experiment(N, vid, e["experiment"]["experiment_id"], approval_ref=ap["approval_id"], store=st)
        ck("5. ...the same paid experiment runs once approved + budgeted", r["ok"])

        # ---- a failed experiment triggers kill/pivot review --------------------------------
        rr = ex.record_result(N, vid, e["experiment"]["experiment_id"], success=False, store=st)
        ck("6. a failed experiment moves the venture into kill/pivot review",
           rr["ok"] and rr["triggers_review"]
           and core.get_venture(N, vid, store=st)["current_phase"] == "kill_pivot_review")

        # ---- zombie + lifecycle ------------------------------------------------------------
        ck("7. a venture with NO kill criteria is a zombie (flagged)", ex.is_zombie(N, vid, store=st))
        ex.set_criteria(N, vid, kill=["no signups after $200"], pivot=["pivot to SMBs"],
                        scale=["100 paying users"], store=st)
        rec = ex.lifecycle_recommendation(N, vid, store=st)
        ck("8. in kill/pivot review with criteria set -> recommend kill_or_pivot",
           rec["recommendation"] == "kill_or_pivot")
        # scale blocked without traction
        core.update_venture(N, vid, {"current_phase": "operating"}, store=st)
        ck("9. scale is BLOCKED without traction evidence",
           ex.lifecycle_recommendation(N, vid, traction_evidence=False, store=st)["recommendation"] == "no_scale")
        ck("9b. scale is a candidate WITH traction evidence",
           ex.lifecycle_recommendation(N, vid, traction_evidence=True, store=st)["recommendation"] == "scale")

        # ---- capital allocation ------------------------------------------------------------
        a1 = ex.allocate(N, vid, amount=500, store=st)
        ck("10. an initial allocation funds within the portfolio budget", a1["ok"])
        big = ex.allocate(N, vid, amount=5000, traction_evidence=False, store=st)
        ck("11. a funding INCREASE without traction is refused (no scale without proof)",
           not big["ok"] and big.get("recommendation") == "research_more")
        over = ex.allocate(N, vid, amount=999999, traction_evidence=True, store=st)
        ck("12. allocation beyond the unallocated portfolio budget is refused", not over["ok"])

        # ---- vendor coordinator ------------------------------------------------------------
        ven = ex.vendor_sow(N, vid, "designer", "logo + landing visual", store=st)
        ck("13. a vendor SOW is drafted; contact requires approval",
           ven["ok"] and ven["vendor"]["contact_requires_approval"]
           and not ex.can_contact_vendor(N, ven["vendor"], store=st)["allowed"])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_foundry_execution", "green" if green else "red",
                files_observed=["anima/foundry/execution.py"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDRY-EXECUTION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
