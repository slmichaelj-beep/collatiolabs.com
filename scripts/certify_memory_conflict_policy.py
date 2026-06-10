#!/usr/bin/env python3
"""certify_memory_conflict_policy — the conflict ordering is exactly the directive's, and a
conflict is surfaced (never silently resolved).

Hermetic over truth.supersession.wins + a live conflict construction:
  1. safety/system policy > everything
  2. user correction > older memory
  3. explicit teaching > inferred preference
  4. project rule > general preference inside the project
  5. newer same-scope correction > older same-scope record
  6. a source fact does NOT override personal memory
  7. transitivity sanity (system > teaching > inference)
  8. a genuine conflict event surfaces in the learning view's conflicts section (not auto-hidden)
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.truth import supersession as sup   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def mk(ct, sc="long_term", at="2"):
    return {"claim_type": ct, "scope": sc, "created_at": at}


def main() -> int:
    t0 = time.perf_counter()
    print("MEMORY CONFLICT POLICY — the priority ladder is exact, conflicts are surfaced")
    print("=" * 92)

    ck("1. safety/system policy beats teaching, correction, memory, source, inference",
       all(sup.wins(mk("system", "system"), mk(x)) for x in
           ("teaching", "correction", "memory", "source", "inference")))
    ck("2. user correction > older memory",
       sup.wins(mk("correction", "long_term", "3"), mk("memory", "long_term", "1")))
    ck("3. explicit teaching > inferred preference",
       sup.wins(mk("teaching"), mk("inference")))
    ck("4. project rule > general preference inside the project",
       sup.wins(mk("memory", "project", "1"), mk("memory", "long_term", "2")))
    ck("5. newer same-scope correction > older same-scope record",
       sup.wins(mk("correction", "long_term", "5"), mk("correction", "long_term", "1")))
    ck("6. a source fact does NOT override personal memory",
       not sup.wins(mk("source", "chat", "9"), mk("memory", "long_term", "1")))
    ck("7. transitivity: system > teaching and teaching > inference => system > inference",
       sup.wins(mk("system", "system"), mk("teaching")) and sup.wins(mk("teaching"), mk("inference"))
       and sup.wins(mk("system", "system"), mk("inference")))

    # ---- 8. a conflict event surfaces in the learning view -----------------------------------
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "ConflictCert"
        from anima.truth import ledger as tl, schema as ts, learning_view as lv
        ev = ts.make("favorite_color", "favorite_color = teal vs gray (unresolved)", "memory",
                     provenance_kind="user_turn", scope="long_term", active_status="conflict",
                     actor="user")
        tl.emit(N, ev, store=st)
        view = lv.build(N, store=st)
        ck("8. a conflict event appears in the learning view's conflicts section (surfaced, not hidden)",
           any(r["event_id"] == ev["event_id"] for r in view["sections"]["conflicts"]))

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_memory_conflict_policy", "green" if green else "red",
                files_observed=["anima/truth/supersession.py", "anima/truth/learning_view.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nMEMORY-CONFLICT-POLICY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
