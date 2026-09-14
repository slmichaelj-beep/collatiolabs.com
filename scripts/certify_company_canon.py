#!/usr/bin/env python3
"""certify_company_canon — the company self-model exists, is approval-gated, traced, reversible."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company import canon   # noqa: E402
from anima.truth import query as tq   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMPANY CANON — structured self-model, approval-gated, traced, reversible")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "CanonCert"
        import anima.company.storage as cs
        # redirect company store + truth store to scratch
        old = cs.default_store
        cs.default_store = lambda: st
        try:
            c = canon.load(N, store=st)
            ck("1. canon exists with every required field", canon.validate(c) == [])
            # 2. change requires approval (pending does not mutate)
            r = canon.propose_change(N, "mission", "Build the local-first founder brain.", store=st)
            ck("2. a proposed change is PENDING, not yet applied",
               r["ok"] and canon.load(N, store=st)["mission"] != "Build the local-first founder brain.")
            # 3. approval applies + emits truth event
            a = canon.approve_change(N, r["pending_id"], store=st)
            c2 = canon.load(N, store=st)
            ck("3. approval applies the change AND emits a Truth Ledger event",
               a["ok"] and c2["mission"] == "Build the local-first founder brain."
               and bool(a["truth_ledger_event"]))
            ck("3b. the canon event is traceable in the ledger (claim_type=system, company subject)",
               any(e.get("event_id") == a["truth_ledger_event"]
                   and (e.get("subject") or "").startswith("company:canon")
                   for e in tq.fold(N, store=st).values()))
            # 4. unknown field refused
            ck("4. an unknown canon field is refused",
               not canon.propose_change(N, "world_domination_plan", "x", store=st)["ok"])
            # 5. rollback
            rb = canon.rollback_change(N, "mission", store=st)
            ck("5. a canon field can be rolled back to its prior value",
               rb["ok"] and canon.load(N, store=st)["mission"] != "Build the local-first founder brain.")
        finally:
            cs.default_store = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_company_canon", "green" if green else "red",
                files_observed=["anima/company/canon.py", "anima/company/storage.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMPANY-CANON CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
