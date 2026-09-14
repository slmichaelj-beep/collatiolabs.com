#!/usr/bin/env python3
"""certify_learning_integrity_dashboard — the user can inspect what Vera knows and why.

Hermetic build of a scratch creature's learning state + the live page/route:
  1. ACTIVE CLAIM        — an active memory appears in Active Memories with its event id.
  2. CORRECTION CHAIN    — a correction appears; the superseded original is NOT active.
  3. RETRACTED VISIBLE   — a retracted memory appears as retracted, not active.
  4. UNSUPPORTED VISIBLE — an unsupported claim appears in Unsupported.
  5. CONFLICT VISIBLE    — a conflict appears in Conflicts.
  6. NO INVENTED GREEN   — integrity counts are computed from the ledger (unsupported count real).
  7. ROW -> EVENT        — every claim row carries an event_id (the trace handle).
  8. LIVE ROUTE + PAGE   — /learning.json serves; /learning page exists and links to /truth/trace.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.truth import ledger as tl, schema as ts, supersession as sup, learning_view as lv  # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("LEARNING INTEGRITY DASHBOARD — inspect what Vera knows, why, and what changed")
    print("=" * 92)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "LearnDashCert"
        # active memory
        m1 = ts.make("lives", "lives = Portland", "memory", provenance_kind="user_turn",
                     evidence_refs=["f1"], scope="long_term", actor="user")
        tl.emit(N, m1, store=st)
        # correction superseding an original
        orig = ts.make("favorite_color", "favorite_color = teal", "memory",
                       provenance_kind="user_turn", evidence_refs=["f2"], scope="long_term",
                       actor="user")
        tl.emit(N, orig, store=st)
        corr = sup.supersede(N, [orig["event_id"]], "favorite_color", "favorite_color = gray",
                             provenance_refs=["turn-9"], evidence_refs=["f3"], store=st)
        # retraction
        m3 = ts.make("dog_name", "dog_name = Rex", "memory", provenance_kind="user_turn",
                     evidence_refs=["f4"], scope="long_term", actor="user")
        tl.emit(N, m3, store=st)
        sup.retract(N, [m3["event_id"]], "dog_name", reason="forget", store=st)
        # unsupported + conflict
        tl.emit(N, ts.make("memory_language", "unsupported recollection", "unsupported",
                           provenance_kind="assistant_turn", scope="chat", actor="vera",
                           active_status="unsupported"), store=st)
        tl.emit(N, ts.make("employer", "employer = A vs B", "memory", provenance_kind="user_turn",
                           scope="long_term", active_status="conflict", actor="user"), store=st)

        view = lv.build(N, store=st)
        S = view["sections"]
        ck("1. active memory appears in Active Memories with its event id",
           any(r["event_id"] == m1["event_id"] for r in S["active_memories"]))
        ck("2. correction appears; superseded original is NOT active",
           any(r["event_id"] == corr["event_id"] for r in S["corrections"])
           and not any(r["event_id"] == orig["event_id"] for r in S["active_memories"]))
        ck("3. retracted memory appears as retracted (not active)",
           any(r["event_id"] == m3["event_id"] for r in S["retracted_memories"])
           and not any(r["subject"] == "dog_name" for r in S["active_memories"]))
        ck("4. unsupported claim appears in Unsupported", len(S["unsupported_claims"]) >= 1)
        ck("5. conflict appears in Conflicts",
           any(r["subject"] == "employer" for r in S["conflicts"]))
        ck("6. integrity counts computed from the ledger (unsupported real)",
           view["integrity"]["unsupported_claims"] == len(S["unsupported_claims"]))
        ck("7. every claim row carries an event_id (trace handle)",
           all(r.get("event_id") for r in S["active_memories"] + S["corrections"]
               + S["retracted_memories"] + S["conflicts"]))

    # ---- 8. live route + page -----------------------------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/learning.json", timeout=10) as r:
            lj = json.loads(r.read())
        ck("8. LIVE /learning.json serves the sections", lj.get("ok") is True and "sections" in lj)
        page = (ROOT / "anima" / "web" / "learning.html").read_text()
        ck("8b. the /learning page exists and links each row to /truth/trace",
           "Learning Integrity" in page and "/truth/trace?event_id=" in page
           and "/learning.json" in page)
        src = (ROOT / "anima" / "server.py").read_text()
        ck("8c. the /learning page + data routes are wired in the server",
           '"/learning"' in src and '"/learning.json"' in src)
    except Exception as e:
        ck("8. live learning surface reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_learning_integrity_dashboard", "green" if green else "red",
                files_observed=["anima/truth/learning_view.py", "anima/web/learning.html"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nLEARNING-INTEGRITY-DASHBOARD CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
