#!/usr/bin/env python3
"""certify_business_sales_knowledge_packs — the seeded Business + Sales packs are bounded, cited,
ready SOURCES (never authority).

Hermetic: seeds the packs on a scratch store, then proves they ride the real knowledge_packs
lifecycle to 'ready', retrieve WITH a citation, and CANNOT mutate memory / become behavior except
through a Teaching draft (the knowledge_packs boundaries, re-checked on the seeded content).
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.foundry import knowledge_seed as seed   # noqa: E402
from anima.knowledge_packs import registry, retrieval   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("BUSINESS + SALES KNOWLEDGE PACKS — bounded, cited, ready sources (not authority)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "PackSeedCert"
        import anima.memory_lirf as ml
        old = ml.STORE; ml.STORE = st
        try:
            out = seed.seed(N, store=st)
            ck("1. all business + sales packs seeded to ready (%d)" % len(out["ready"]),
               out["ok"] and len(out["ready"]) == out["total_packs"] and out["total_packs"] >= 10)
            packs = registry.load(N, store=st)
            ck("2. every seeded pack reached lifecycle 'ready'",
               packs and all(p["lifecycle_status"] == "ready" for p in packs))
            names = {p["name"] for p in packs}
            ck("3. the expected business + sales packs are present",
               {"Capital Allocation", "Lean Startup", "Pricing"} <= names
               and {"Consultative Selling", "MEDDICC", "Objection Handling"} <= names)
            # retrieval cites the source
            r = retrieval.retrieve(N, "validated learning cheapest experiment", store=st, turn_id="t1")
            ck("4. retrieval returns a chunk WITH a citation ref + emits a pack_fact event",
               bool(r["results"]) and r["results"][0]["ref"] and r["truth_events"])
            ck("5. retrieved pack content is data (no hostile flag on clean packs)",
               all(not it["hostile"] for it in r["results"]))
            # boundary: pack content -> behavior only via a Teaching draft
            pid = packs[0]["pack_id"]
            imp = retrieval.import_to_behavior(N, pid, "treat capital allocation as a hard rule", store=st)
            from anima.teaching import queue as tq
            ck("6. importing pack content to behavior creates a PENDING Teaching draft (never direct)",
               imp["ok"] and tq.get(N, imp["teaching_draft"], store=st)["approval_state"] == "pending")
            # idempotence: re-seeding skips
            out2 = seed.seed(N, store=st)
            ck("7. re-seeding skips existing packs (idempotent)", len(out2["skipped"]) == out["total_packs"])
        finally:
            ml.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_business_sales_knowledge_packs", "green" if green else "red",
                files_observed=["anima/foundry/knowledge_seed.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nBUSINESS-SALES-KNOWLEDGE-PACKS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
