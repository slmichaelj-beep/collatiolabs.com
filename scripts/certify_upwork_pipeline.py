#!/usr/bin/env python3
"""certify_upwork_pipeline — the bid funnel + Connects ledger + revenue truth.

Triage logs bid/skip; a staged bid starts 'drafted'; submit spends Connects; only payment evidence
lets a bid reach 'paid'; submitted=activity, awarded=pipeline, paid=cash (separated honestly);
Connects decrement on submit; the board assembles the funnel.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.marketplaces.upwork import pipeline as p, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("UPWORK PIPELINE — funnel / connects / revenue truth")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "UWCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            p.set_connects(N, available=100, store=st)
            p.record_triage(N, job_title="Big unverified job", verdict="skip",
                            reason="50+ proposals, unverified", store=st)
            p.record_triage(N, job_title="Fresh FastAPI debug", verdict="bid",
                            reason="fresh, <5 proposals, in lane", fresh=True, verified=True, store=st)
            ck("1. triage logs both a skip and a bid verdict",
               p.board(N, st)["funnel"]["skipped"] == 1 and p.board(N, st)["funnel"]["bid_verdicts"] == 1)

            bid = p.stage_bid(N, job_title="Fresh FastAPI debug", bid_amount=200, fit_reason="code", store=st)["bid"]
            ck("2. a staged bid starts in 'drafted'", bid["status"] == "drafted")
            ck("3. paid without evidence is refused (no cash without proof)",
               not p.advance(N, bid["bid_id"], "paid", store=st)["ok"])

            p.advance(N, bid["bid_id"], "submitted", connects_spent=13, store=st)
            c = p.board(N, st)["connects"]
            ck("4. submitting spends Connects (decrements available, adds spent)",
               c["available"] == 87 and c["spent"] == 13)
            ck("5. a submitted bid counts as ACTIVITY, not cash",
               p.board(N, st)["money"]["activity_bids"] == 1 and p.board(N, st)["money"]["collected_cash_paid"] == 0)

            p.advance(N, bid["bid_id"], "replied", store=st)
            p.advance(N, bid["bid_id"], "awarded", store=st)
            ck("6. an awarded contract is PIPELINE value, not yet cash",
               p.board(N, st)["money"]["pipeline_value_awarded"] == 200 and p.board(N, st)["money"]["collected_cash_paid"] == 0)
            ck("7. paid WITH evidence counts as collected cash",
               p.advance(N, bid["bid_id"], "paid", paid_evidence_ref="upwork_payment_1", store=st)["ok"]
               and p.board(N, st)["money"]["collected_cash_paid"] == 200)
            ck("8. a terminal (paid) bid cannot be advanced again",
               not p.advance(N, bid["bid_id"], "delivered", store=st)["ok"])

            d = api.dashboard(N, store=st)
            ck("9. the dashboard assembles funnel + connects + money + honesty",
               d["ok"] and "funnel" in d and "submitted/replied" in d["honesty"])
            ck("10. honesty keeps activity != pipeline != cash",
               "pipeline" in d["honesty"].lower() and "cash" in d["honesty"].lower())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_upwork_pipeline", "green" if green else "red",
                files_observed=["anima/marketplaces/upwork/pipeline.py"],
                report_paths=["reports/upwork_pipeline.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nUPWORK-PIPELINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
