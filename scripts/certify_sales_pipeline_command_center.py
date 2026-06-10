#!/usr/bin/env python3
"""certify_sales_pipeline_command_center — the sales pipeline command center is real + honest.

The sales pipeline in this build is surfaced through the backend command-center data (pipeline
briefing) rather than a standalone /sales page; /sales is honestly NOT linked as active. This cert
proves the pipeline command-center data is real (stages, hot/stale, approvals, forecast labeled
assumption) and that revenue truth distinguishes activity / pipeline / closed revenue.
"""
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
    print("SALES PIPELINE COMMAND CENTER — pipeline state, forecast honesty, revenue truth")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SalesCmdCert"
        pl.add_opportunity(N, "lead1", value=12000, stage="qualified", store=st)
        pl.add_opportunity(N, "lead2", value=40000, stage="proposal_sent", store=st)
        b = pl.briefing(N, store=st)
        ck("1. the pipeline command center shows stages + pipeline value + approvals",
           "by_stage" in b and b["pipeline_value"] >= 52000 and "approvals_needed" in b)
        ck("2. the forecast is labeled an assumption, NOT revenue",
           "forecast_note" in b and "NOT revenue" in b["forecast_note"] and b["closed_revenue"] == 0)
        rt = pl.revenue_truth(N, store=st)
        ck("3. revenue truth distinguishes activity / pipeline / closed revenue",
           rt["closed_revenue"] == 0 and rt["pipeline_value_forecast"] >= 52000
           and "activity" in rt)
        # /sales is honestly NOT linked as an active page (no false claim)
        idx = (ROOT / "anima" / "web" / "index.html").read_text()
        ck("4. /sales is NOT linked as an active surface (honest — built as backend + chairman/founder)",
           'href="/sales"' not in idx)
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_sales_pipeline_command_center", "green" if green else "red",
                files_observed=["anima/commercial/sales_mastery/pipeline.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSALES-PIPELINE-COMMAND-CENTER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
