#!/usr/bin/env python3
"""certify_decision_ledger — decisions are recorded, approval-gated, traceable, supersedable."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company import decisions as dec   # noqa: E402
from anima.truth import query as tq   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("DECISION LEDGER — remember decisions like a founder operator")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "DecCert"
        p = dec.propose(N, "Defer audiobook_intake", "Not part of Local/Internal; future Media tier.",
                        dtype="release", rationale="Out of current scope; honest deferral.",
                        reversibility="two_way", store=st)
        did = p["decision"]["decision_id"]
        ck("1. a decision is proposed (status=proposed, not yet durable)",
           p["ok"] and dec.get(N, did, store=st)["status"] == "proposed"
           and dec.get(N, did, store=st)["truth_ledger_event"] is None)
        a = dec.approve(N, did, store=st)
        ck("2. approval makes it decided + emits a Truth Ledger event",
           a["ok"] and dec.get(N, did, store=st)["status"] == "decided" and bool(a["truth_ledger_event"]))
        ck("3. 'why did we decide this?' is answerable (rationale + options preserved)",
           "honest deferral" in dec.get(N, did, store=st)["rationale"].lower())
        # supersede
        p2 = dec.propose(N, "Re-claim audiobook at Media tier", "Claim it when Media tier opens.",
                         dtype="release", store=st)
        d2 = p2["decision"]["decision_id"]
        a2 = dec.approve(N, d2, supersedes=[did], store=st)
        ck("4. a newer decision supersedes the old (old -> superseded, links recorded)",
           a2["ok"] and dec.get(N, did, store=st)["status"] == "superseded"
           and d2 in dec.get(N, did, store=st)["superseded_by"])
        # reopen
        dec.reopen(N, did, reason="revisit", store=st)
        ck("5. a decision can be reopened (status=reopened)",
           dec.get(N, did, store=st)["status"] == "reopened")
        ck("6. decisions trace to the Truth Ledger (company:decision subject)",
           any((e.get("subject") or "").startswith("company:decision")
               for e in tq.fold(N, store=st).values()))
        v = dec.views(N, store=st)
        ck("7. views expose recent/open/superseded/one-way",
           all(k in v for k in ("recent", "open", "superseded", "one_way", "all")))
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_decision_ledger", "green" if green else "red",
                files_observed=["anima/company/decisions.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nDECISION-LEDGER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
