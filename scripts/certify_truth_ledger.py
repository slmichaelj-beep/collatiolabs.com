#!/usr/bin/env python3
"""certify_truth_ledger — the append-only Truth Ledger holds.

Proves (hermetic scratch store; the real .anima untouched by the hermetic block):
  1. SCHEMA BITES        — make() builds a valid event; every vocabulary violation raises;
                           emit() refuses an invalid event.
  2. APPEND-ONLY         — events accumulate in order; nothing is rewritten; a corrupt line is
                           SURFACED (conflict marker), never silently dropped.
  3. SUPERSESSION FOLDS  — a correction supersedes the old event (old -> superseded, new active,
                           superseded_by filled); a retraction closes the chain (old -> retracted)
                           with no replacement value asserted.
  4. TRACE IS COMPLETE   — trace() returns the whole chain through any link, oldest first.
  5. CONFLICT POLICY     — wins() encodes: user correction > older memory; teaching > inference;
                           project rule > general preference in-project; system > teaching;
                           newer same-scope > older; source NEVER silently beats user memory.
  6. EVERY CLAIM TYPE    — all eight claim_types round-trip; unsupported() counts exactly the
                           unsupported ones.
  7. LIVE ROUTES         — /truth.json and /truth/trace serve the real creature's ledger
                           (skipped honestly if the server is down).
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

from anima.truth import api, ledger, query, schema, supersession   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("TRUTH LEDGER — every claim traceable, append-only, conflict-ordered")
    print("=" * 92)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "TruthCert"

        # ---- 1. schema bites -----------------------------------------------------------------
        ev = schema.make("favorite_color", "favorite_color = teal", "memory",
                         provenance_kind="user_turn", provenance_refs=["turn-1"],
                         evidence_refs=["f_row1"], scope="long_term", confidence=0.9, actor="user")
        ck("1. make() builds a schema-valid event", schema.validate(ev) == [])
        raised = 0
        for bad in (dict(claim_type="vibes"), dict(provenance_kind="rumor"), dict(scope="cosmos"),
                    dict(actor="ghost"), dict(risk="spicy")):
            try:
                kw = dict(provenance_kind="user_turn")
                kw.update({k: v for k, v in bad.items() if k != "claim_type"})
                schema.make("s", "c", bad.get("claim_type", "memory"), **kw)
            except ValueError:
                raised += 1
        ck("1b. every vocabulary violation raises (%d/5)" % raised, raised == 5)
        try:
            ledger.emit(N, {"event_id": "nope", "status": "green"}, store=st)
            refused = False
        except ValueError:
            refused = True
        ck("1c. emit() refuses an invalid event", refused)

        # ---- 2. append-only -------------------------------------------------------------------
        e1 = ledger.record(N, "favorite_color", "favorite_color = teal", "memory",
                           provenance_kind="user_turn", scope="long_term", actor="user", store=st)
        e2 = ledger.record(N, "dog_name", "dog_name = Rex", "memory",
                           provenance_kind="user_turn", scope="long_term", actor="user", store=st)
        evs = ledger.load(N, store=st)
        ck("2. events accumulate in append order",
           [e["event_id"] for e in evs] == [e1["event_id"], e2["event_id"]])
        with ledger.path_for(N, st).open("a") as f:
            f.write("NOT JSON AT ALL\n")
        evs = ledger.load(N, store=st)
        ck("2b. a corrupt line is SURFACED as a conflict marker, never silently dropped",
           len(evs) == 3 and evs[-1].get("_corrupt") is True
           and evs[-1]["active_status"] == "conflict")

        # ---- 3. supersession + retraction folds -------------------------------------------------
        e3 = supersession.supersede(N, [e1["event_id"]], "favorite_color",
                                    "favorite_color = gray", provenance_refs=["turn-2"], store=st)
        folded = query.fold(N, store=st)
        ck("3. correction: old -> superseded, superseded_by filled, new active",
           folded[e1["event_id"]]["active_status"] == "superseded"
           and e3["event_id"] in folded[e1["event_id"]]["superseded_by"]
           and folded[e3["event_id"]]["active_status"] == "active")
        e4 = supersession.retract(N, [e3["event_id"]], "favorite_color",
                                  reason="user asked to forget", store=st)
        folded = query.fold(N, store=st)
        ck("3b. retraction: the chain closes with NO replacement value asserted",
           folded[e3["event_id"]]["active_status"] == "retracted"
           and folded[e4["event_id"]]["active_status"] == "retracted"
           and "RETRACTED" in folded[e4["event_id"]]["claim"])
        ck("3c. active() shows NOTHING for the retracted trait",
           query.active(N, subject="favorite_color", store=st) == [])

        # ---- 4. trace ----------------------------------------------------------------------------
        chain = query.trace(N, e1["event_id"], store=st)
        ck("4. trace() returns the WHOLE chain through any link (%d links, oldest first)"
           % len(chain),
           [c["event_id"] for c in chain] == [e1["event_id"], e3["event_id"], e4["event_id"]])

        # ---- 5. conflict policy --------------------------------------------------------------------
        mk = lambda ct, sc, at: {"claim_type": ct, "scope": sc, "created_at": at}
        ck("5. user correction > older memory",
           supersession.wins(mk("correction", "long_term", "2"), mk("memory", "long_term", "1")))
        ck("5b. explicit teaching > inferred preference",
           supersession.wins(mk("teaching", "long_term", "2"), mk("inference", "long_term", "1")))
        ck("5c. project rule > general preference inside the project",
           supersession.wins(mk("memory", "project", "1"), mk("memory", "long_term", "2")))
        ck("5d. safety/system policy > teaching",
           supersession.wins(mk("system", "system", "1"), mk("teaching", "long_term", "2")))
        ck("5e. newer same-scope correction > older same-scope record",
           supersession.wins(mk("correction", "long_term", "3"), mk("correction", "long_term", "1")))
        ck("5f. a source fact does NOT override user memory",
           not supersession.wins(mk("source", "chat", "9"), mk("memory", "long_term", "1")))

        # ---- 6. every claim type --------------------------------------------------------------------
        okt = 0
        for ct in schema.CLAIM_TYPES:
            try:
                ledger.record(N, "s_" + ct, "claim of type " + ct, ct,
                              provenance_kind="system_cert", scope="system", actor="cert", store=st)
                okt += 1
            except Exception:
                pass
        ck("6. all %d claim types round-trip" % len(schema.CLAIM_TYPES), okt == len(schema.CLAIM_TYPES))
        u = ledger.record(N, "memory_language", "unsupported claim", "unsupported",
                          provenance_kind="assistant_turn", scope="chat", actor="vera",
                          active_status="unsupported", store=st)
        ck("6b. unsupported() counts exactly the unsupported events",
           [x["event_id"] for x in query.unsupported(N, store=st)].count(u["event_id"]) == 1)

        # ---- api hooks (scratch) ---------------------------------------------------------------------
        row = {"id": "f_abc", "trait": "lives", "value": "Portland", "confidence": 0.9,
               "status": "active"}
        w = api.on_memory_write("ApiCert", row, "I live in Portland", "turn-9", store=st)
        ck("A. api.on_memory_write emits a valid memory event",
           w is not None and schema.validate(w) == [] and w["claim_type"] == "memory")
        w2 = api.on_memory_write("ApiCert", dict(row, value="Salem"), "I moved to Salem", "turn-10",
                                 store=st)
        folded = query.fold("ApiCert", store=st)
        ck("A2. a NEW VALUE for the same trait supersedes (correction event, old superseded)",
           w2["claim_type"] == "correction"
           and folded[w["event_id"]]["active_status"] == "superseded")
        r = api.on_memory_retraction("ApiCert", "lives", "f_abc", "forget where I live", "turn-11",
                                     store=st)
        ck("A3. api retraction closes every active event for the trait",
           r is not None and query.active("ApiCert", subject="lives", store=st) == [])
        ck("A4. a retraction with NOTHING on record creates nothing",
           api.on_memory_retraction("ApiCert", "ghost_trait", None, "forget it", "turn-12",
                                    store=st) is None)

    # ---- 7. live routes ------------------------------------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/truth.json", timeout=10) as resp:
            tj = json.loads(resp.read())
        ck("7. LIVE /truth.json serves the real ledger (events_total=%s)" % tj.get("events_total"),
           tj.get("ok") is True and isinstance(tj.get("events_total"), int))
        eid = (tj.get("active") or [{}])[-1].get("event_id") or ""
        if not eid:
            # no active events (everything retracted is a legal state) — trace an arbitrary id
            eid = "te_000000000000"
        with urllib.request.urlopen("http://127.0.0.1:8765/truth/trace?event_id=" + eid,
                                    timeout=10) as resp:
            tr = json.loads(resp.read())
        ck("7b. LIVE /truth/trace serves a chain for a ledger event", tr.get("ok") is True)
    except Exception as e:
        ck("7. LIVE routes reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_truth_ledger", "green" if green else "red",
                files_observed=["anima/truth/schema.py", "anima/truth/ledger.py",
                                "anima/truth/query.py", "anima/truth/supersession.py",
                                "anima/truth/api.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nTRUTH-LEDGER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
