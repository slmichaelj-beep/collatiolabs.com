#!/usr/bin/env python3
"""certify_sales_pipeline_revenue — pipeline + learning loop + revenue truth + safety."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial.sales_mastery import pipeline as pl   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("SALES PIPELINE / REVENUE — own the state, measured by revenue not activity")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SalesPipeCert"
        o = pl.add_opportunity(N, "lead1", value=12000, stage="qualified", store=st)
        oid = o["opportunity"]["opportunity_id"]
        ck("1. an opportunity enters the pipeline", o["ok"])
        # closing requires a reason
        ck("2. closing without a win/loss reason is refused",
           not pl.advance(N, oid, "closed_won", store=st)["ok"])
        ck("3. closing WITH a reason succeeds",
           pl.advance(N, oid, "closed_won", win_loss_reason="champion + budget confirmed", store=st)["ok"])
        # revenue truth
        o2 = pl.add_opportunity(N, "lead2", value=50000, stage="proposal_sent", store=st)
        rt = pl.revenue_truth(N, store=st)
        ck("4. pipeline value is NOT counted as closed revenue",
           rt["closed_revenue"] == 12000 and rt["pipeline_value_forecast"] >= 50000
           and rt["closed_revenue"] != rt["pipeline_value_forecast"])
        ck("5. activity is distinct from pipeline and revenue",
           "activity" in rt and "assumptions" in rt["rule"] or "assumption" in rt["rule"])
        b = pl.briefing(N, store=st)
        ck("6. the briefing labels the forecast as an assumption (not revenue)",
           "forecast_note" in b and "NOT revenue" in b["forecast_note"])
        # learning loop -> teaching draft (no silent policy mutation)
        pl.record_outcome(N, oid, outcome="won", reason="proof-first demo worked", store=st)
        ch = pl.propose_policy_change(N, "lead every demo with the strongest proof point", store=st)
        ck("7. a durable sales-policy change becomes a Teaching draft (not silent)",
           ch["ok"] and ch.get("teaching_draft"))
        # safety
        ck("8. a deceptive / fake-testimonial message is blocked",
           not pl.screen(N, "use a fake testimonial from a happy customer", store=st)["allowed"])
        ck("9. an ROI claim without proof is blocked; a clean message passes",
           not pl.screen(N, "guaranteed 3x ROI", is_roi_claim=True, has_proof=False, store=st)["allowed"]
           and pl.screen(N, "a clear, honest note about the pilot result", store=st)["allowed"])
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_sales_pipeline_revenue", "green" if green else "red",
                files_observed=["anima/commercial/sales_mastery/pipeline.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSALES-PIPELINE-REVENUE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
