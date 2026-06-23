#!/usr/bin/env python3
"""certify_marketplace_resource_invariants - Upwork Connects and bid FSM hold.

The Upwork tracker is human-in-the-loop, but its accounting must still be exact. Connects cannot
overspend, failed submissions cannot advance, and bid statuses move through a finite state machine.
Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.marketplaces.upwork import pipeline as p  # noqa: E402

oks, fails = [], []


def ck(label: str, cond: bool):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("MARKETPLACE RESOURCE INVARIANTS - Upwork Connects + finite states")
    print("=" * 84)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        name = "MarketplaceResourceCert"

        p.set_connects(name, available=3, store=st)
        over = p.spend_connects(name, amount=10, note="overspend", store=st)
        c = p.board(name, st)["connects"]
        ck("1. direct Connects overspend is refused",
           not over["ok"] and "insufficient" in over["error"])
        ck("2. refused overspend does not mutate the Connects ledger",
           c["available"] == 3 and c["spent"] == 0)

        zero = p.spend_connects(name, amount=0, note="zero", store=st)
        negative = p.spend_connects(name, amount=-1, note="negative", store=st)
        ck("3. zero Connects spend is refused", not zero["ok"] and "positive" in zero["error"])
        ck("4. negative Connects spend is refused",
           not negative["ok"] and "positive" in negative["error"])

        bad_available = p.set_connects(name, available=-4, store=st)
        ck("5. negative available Connects is refused",
           not bad_available["ok"] and "non-negative" in bad_available["error"])

        p.set_connects(name, available=2, store=st)
        costly = p.stage_bid(name, job_title="Costly proposal", bid_amount=200,
                             connects_cost=9, store=st)["bid"]
        submit_block = p.advance(name, costly["bid_id"], "submitted", store=st)
        costly_after = [b for b in p.bids(name, st) if b["bid_id"] == costly["bid_id"]][0]
        c2 = p.board(name, st)["connects"]
        ck("6. submission fails when Connects cannot be spent",
           not submit_block["ok"] and "insufficient" in submit_block["error"])
        ck("7. failed submission keeps bid drafted and Connects unchanged",
           costly_after["status"] == "drafted" and c2["available"] == 2 and c2["spent"] == 0)

        p.set_connects(name, available=20, store=st)
        legal = p.stage_bid(name, job_title="Legal proposal", bid_amount=500,
                            connects_cost=6, store=st)["bid"]
        jump = p.advance(name, legal["bid_id"], "awarded", store=st)
        ck("8. drafted bids cannot jump directly to awarded",
           not jump["ok"] and "illegal transition" in jump["error"])

        submit = p.advance(name, legal["bid_id"], "submitted", store=st)
        repeat_submit = p.advance(name, legal["bid_id"], "submitted", connects_spent=6, store=st)
        c3 = p.board(name, st)["connects"]
        ck("9. legal submit spends exactly the staged Connects", submit["ok"]
           and c3["available"] == 14 and c3["spent"] == 6)
        ck("10. repeated submitted state is refused without double-spend",
           not repeat_submit["ok"] and c3 == p.board(name, st)["connects"])

        paid_jump = p.advance(name, legal["bid_id"], "paid", paid_evidence_ref="payment", store=st)
        ck("11. submitted bids cannot jump directly to paid even with evidence",
           not paid_jump["ok"] and "illegal transition" in paid_jump["error"])

        ck("12. paid still requires evidence on a legal paid transition",
           p.advance(name, legal["bid_id"], "replied", store=st)["ok"]
           and p.advance(name, legal["bid_id"], "awarded", store=st)["ok"]
           and not p.advance(name, legal["bid_id"], "paid", store=st)["ok"])
        paid = p.advance(name, legal["bid_id"], "paid", paid_evidence_ref="upwork_payment", store=st)
        ck("13. legal paid transition with evidence succeeds", paid["ok"])
        ck("14. terminal paid bid cannot advance again",
           not p.advance(name, legal["bid_id"], "delivered", store=st)["ok"])
        ck("15. cash only appears after the legal paid transition",
           p.board(name, st)["money"]["collected_cash_paid"] == 500)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_marketplace_resource_invariants", "green" if green else "red",
                files_observed=["anima/marketplaces/upwork/pipeline.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nMARKETPLACE-RESOURCE-INVARIANTS CERT: "
          + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
