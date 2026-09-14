#!/usr/bin/env python3
"""certify_operator_evidence_chain — a user can follow a UI claim to its evidence.

UI claim -> trace_id (observation event) -> truth/decision/approval/budget/action/report/cert ref.
Proves real chains and that an UNSUPPORTED claim / missing trace fails.
"""
from __future__ import annotations

import json, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.observation import emit, query, store as obstore   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("OPERATOR EVIDENCE CHAIN — UI claim -> trace -> evidence")
    print("=" * 92)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "EvChainCert"
        old = obstore.STORE; obstore.STORE = st
        try:
            # a founder-briefing claim chains to a report ref
            fb = emit.record(N, "/founder", "company", "daily_briefing_generated",
                             report_refs=["reports/verification_worklog.md"], store_path=st)
            ck("1. founder-briefing event links to a report ref (followable)",
               query.has_evidence(fb) and fb["report_refs"])
            # a budget-governance claim chains to a budget ref
            bg = emit.record(N, "/chairman", "company_operator", "budget_required",
                             result="blocked", budget_refs=["budget_main"], store_path=st)
            ck("2. budget-governance event links to a budget ref", query.has_evidence(bg))
            # an approval-queue claim chains to an approval ref
            aq = emit.record(N, "/founder", "company_operator", "approval_required",
                             result="blocked", approval_refs=["apr_x"], store_path=st)
            ck("3. approval-queue event links to an approval ref", query.has_evidence(aq))
            # a capital-allocation claim chains to a truth + action ref
            ca = emit.record(N, "/chairman", "foundry", "capital_allocation_recommended",
                             truth_refs=["te_x"], action_refs=["act_x"], store_path=st)
            ck("4. capital-allocation event links to truth + action refs", query.has_evidence(ca))
            # trace lookup returns the chain
            chain = query.by_trace(N, fb["trace_id"], store_path=st)
            ck("5. by_trace returns the event chain for a trace_id", len(chain) >= 1)
            # an UNSUPPORTED claim (no evidence) is detectable as unsupported
            bare = emit.record(N, "/founder", "company", "unsupported_claim_viewed", store_path=st)
            ck("6. an event with NO evidence is flagged unsupported (chain fails honestly)",
               not query.has_evidence(bare))
            # a missing trace id resolves to an empty chain (fails to prove)
            ck("7. a missing trace_id yields an empty chain (cannot fake evidence)",
               query.by_trace(N, "tr_doesnotexist", store_path=st) == [])
        finally:
            obstore.STORE = old

    # ---- live: a real surface claim traces to an event with evidence ---------------------------
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/company/briefing.json", timeout=15).read()
        with urllib.request.urlopen("http://127.0.0.1:8765/observation.json", timeout=10) as r:
            obs = json.loads(r.read())
        fb_events = [e for e in obs["events"] if e["action"] == "daily_briefing_generated"]
        ck("8. LIVE: the founder briefing emitted a trace-linked event with a report ref",
           bool(fb_events) and any(e.get("report_refs") for e in fb_events))
        if fb_events:
            tid = fb_events[0]["trace_id"]
            with urllib.request.urlopen("http://127.0.0.1:8765/observation/trace?trace_id=" + tid,
                                        timeout=10) as r:
                tr = json.loads(r.read())
            ck("9. LIVE: /observation/trace resolves that trace to its evidence-linked chain",
               tr.get("ok") and tr.get("evidence_linked") is True)
    except Exception as e:
        ck("8. live evidence chain reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_operator_evidence_chain", "green" if green else "red",
                files_observed=["anima/observation/query.py", "anima/observation/emit.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nOPERATOR-EVIDENCE-CHAIN CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
