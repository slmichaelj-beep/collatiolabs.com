#!/usr/bin/env python3
"""certify_product_doctrine_registry — doctrines stored, traced, and used to flag drift."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company import doctrine as doc   # noqa: E402
from anima.truth import query as tq   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("PRODUCT DOCTRINE REGISTRY — preserve philosophy, prevent drift")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "DocCert"
        acts = doc.active(N, store=st)
        names = {d["name"] for d in acts}
        ck("1. seed doctrines stored (incl. 'No fake green')", "No fake green" in names and len(acts) >= 8)
        ck("2. doctrines trace to the Truth Ledger (company:doctrine subject)",
           any((e.get("subject") or "").startswith("company:doctrine") for e in tq.fold(N, store=st).values()))
        # conflict flagging: a proposal that hides a deferred feature
        hits = doc.check_conflict(N, "Let's just remove audiobook from the UI silently so it's hidden.", store=st)
        ck("3. a drift-y proposal is flagged against a doctrine (conflict surfaced)",
           any("visible" in h["doctrine"].lower() or "deferred" in h["concern"].lower() for h in hits))
        # a fake-green proposal flagged
        hits2 = doc.check_conflict(N, "Add a hardcoded green badge on the dashboard.", store=st)
        ck("4. a 'fake green' proposal is flagged",
           any(h["doctrine"] == "No fake green" for h in hits2))
        # a clean proposal is not falsely flagged
        clean = doc.check_conflict(N, "Add a friendly greeting to the chat header.", store=st)
        ck("5. a clean proposal is NOT falsely flagged", clean == [])
        # add a doctrine
        a = doc.add(N, "Local-first by default", "Nothing leaves the Mac without approval.", store=st)
        ck("6. a new doctrine can be added (traced)", a["ok"] and bool(a["doctrine"]["truth_ledger_event"]))
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_product_doctrine_registry", "green" if green else "red",
                files_observed=["anima/company/doctrine.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nPRODUCT-DOCTRINE-REGISTRY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
