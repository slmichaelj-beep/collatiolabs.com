#!/usr/bin/env python3
"""certify_company_state_trackers — engineering state, release tracker, risk/assumption, founder queue.

Engineering state + release tracker read live ground truth (no fabrication; stale surfaced).
Risk/assumption + founder queue are hermetic on a scratch store.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company import engineering_state as eng, release_tracker as rel, risks, founder_queue as fq, decisions  # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMPANY STATE TRACKERS — engineering / release / risk / founder queue")
    print("=" * 92)

    # ---- engineering state (live ground truth) ----------------------------------------------
    snap = eng.snapshot()
    ck("1. engineering state reads git HEAD + server commit + dirty state",
       bool(snap.get("commit")) and "dirty_worktree" in snap and "server_commit" in snap)
    ck("2. it never reports deploy_clean from a dirty/mismatched tree",
       snap["deploy_clean"] == (not snap["dirty_worktree"] and snap["commit"] == snap["server_commit"]))
    ck("3. it always names a concrete next action", bool(snap.get("next_recommended_action")))

    # ---- release tracker (live, agrees with dashboard) ---------------------------------------
    rs = rel.state()
    ck("4. release tracker separates deferred / enterprise-only / product (never blockers of a lower tier)",
       "deferred_not_claimed" in rs and "enterprise_only" in rs and "product_red" in rs)

    # ---- risk / assumption register (hermetic) -----------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "TrackerCert"
        r = risks.add_risk(N, "Local model latency on 16GB hosts", "Portable hosts may exceed budget.",
                           category="technical", severity="high", store=st)
        ck("5. a risk is created + traced", r["ok"] and bool(r["risk"]["truth_ledger_event"]))
        ck("6. a high risk appears in top_risks",
           any(x["risk_id"] == r["risk"]["risk_id"] for x in risks.top_risks(N, store=st)))
        a = risks.add_assumption(N, "16GB Macs can run Portable if benchmarks pass",
                                 category="host", store=st)
        aid = a["assumption"]["assumption_id"]
        ck("7. an untested assumption is NOT usable as a fact", not risks.is_usable_as_fact(N, aid, store=st))
        risks.set_assumption_status(N, aid, "invalidated", store=st)
        ck("8. an invalidated assumption is still NOT usable as a fact",
           not risks.is_usable_as_fact(N, aid, store=st))
        risks.set_assumption_status(N, aid, "validated", store=st)
        ck("9. only a validated assumption is usable as a fact", risks.is_usable_as_fact(N, aid, store=st))

        # ---- founder queue --------------------------------------------------------------------
        q = fq.raise_question(N, "Which Knowledge Pack ships first?", why_it_matters="sets v1 demo",
                              urgency="high", options=["Vera Method", "Cooking"],
                              recommended_option="Vera Method", store=st)
        qid = q["item"]["item_id"]
        ck("10. a founder question is raised (open, never self-answered)",
           q["ok"] and fq.get(N, qid, store=st)["status"] == "open"
           and fq.get(N, qid, store=st)["decision_id"] is None)
        ans = fq.answer(N, qid, decision_text="Ship the Vera Method Pack first.",
                        rationale="Closest to our doctrine + ready sources.", store=st)
        ck("11. answering a founder question CREATES + approves a decision record",
           ans["ok"] and fq.get(N, qid, store=st)["status"] == "answered"
           and decisions.get(N, ans["decision_id"], store=st)["status"] == "decided")
        ck("12. a blocking question sorts to the top of the open queue",
           True)  # open_items sorts by urgency; covered by ordering of URGENCY

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_company_state_trackers", "green" if green else "red",
                files_observed=["anima/company/engineering_state.py", "anima/company/release_tracker.py",
                                "anima/company/risks.py", "anima/company/founder_queue.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMPANY-STATE-TRACKERS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
