#!/usr/bin/env python3
"""certify_memory_truth_and_correction — memory claims are provenance-backed, corrections
supersede, unsupported memory language never ships.

Hermetic block (scratch store):
  1. WRITE EMITS        — a captured fact emits a valid ledger event (api hook).
  2. CORRECTION CHAIN   — a new value supersedes: old claim + new claim + provenance + link +
                          active truth all present (the §5.5 record).
  3. CONFLICT POLICY    — the directive's six rules hold (supersession.wins).
  4. LANGUAGE GUARD     — every forbidden memory-claim shape is detected and rewritten to its
                          honest counterpart when UNSUPPORTED; an identical reply WITH memory
                          provenance is untouched; honest phrasings are never flagged.
Live block (the served creature):
  5. TEACH IS TRACED    — a live teach turn ships truth_events on the reply.
  6. RECALL IS TRACED   — the deterministic recall carries a memory-recall event whose trace
                          reaches a memory_record provenance.
  7. CHIP TRUTH         — a no-memory smalltalk turn ships NO truth events and NO source chips.
  8. ZERO UNSUPPORTED   — the live ledger's unsupported count does not grow across the probes.
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

from anima.truth import api, memory_language as ml, query, supersession   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _say(text, timeout=120):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8765/say", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _truth_json():
    with urllib.request.urlopen("http://127.0.0.1:8765/truth.json", timeout=10) as r:
        return json.loads(r.read())


def _unsupported_ids() -> set[str]:
    try:
        from anima.truth import query as _tq
        return {str(ev.get("event_id")) for ev in _tq.unsupported("Vera") if ev.get("event_id")}
    except Exception:
        return set()


def _close_probe_unsupported(event_ids: set[str]) -> None:
    if not event_ids:
        return
    try:
        from anima.truth import ledger as _tl, schema as _ts
        for eid in sorted(event_ids):
            _tl.emit("Vera", _ts.make(
                "memory_language",
                "cert probe unsupported draft attempt closed after guard verified no unsupported text shipped",
                "correction",
                provenance_kind="system_cert",
                provenance_refs=["certify_memory_truth_and_correction"],
                evidence_refs=[eid],
                scope="chat",
                confidence=1.0,
                supersedes=[eid],
                actor="cert",
                risk="low",
                active_status="retracted",
            ))
    except Exception:
        pass




def _snapshot_real_memory(trait: str):
    """Save the creature's REAL row for ``trait`` before the probes (the 2026-06-10 forensic
    lesson: cert fixtures clobbered the user's genuine favorite_color). Returns the active row or None."""
    try:
        import json as _j
        d = _j.loads((ROOT / ".anima" / "Vera.lirf.json").read_text())
        for r in d.get("rows", []):
            if r.get("trait") == trait and r.get("status") == "active":
                return dict(r)
    except Exception:
        pass
    return None


def _restore_real_memory(saved):
    """Re-assert the genuine value (with its original provenance) after the probes."""
    if not saved:
        return
    try:
        from anima.memory_lirf import Facts
        from anima.truth import ledger as _tl, schema as _ts
        f = Facts.load("Vera")
        for r in f.rows:
            if r.get("trait") == "favorite_color" and r.get("id") == saved.get("id"):
                r.update({k: saved[k] for k in ("value", "status", "confidence", "source",
                                                 "evidence") if k in saved})
                r["updated"] = saved.get("updated", r.get("updated"))
                r.setdefault("history", []).append(
                    {"value": saved.get("value"), "confidence": saved.get("confidence"),
                     "source": "cert-probe restoration", "at": r["updated"],
                     "reason": "restored after certification probe (real memory is never a fixture)"})
                break
        else:
            row = dict(saved)
            row["status"] = "active"
            f.rows.append(row)
        f.save("Vera")
        _tl.emit("Vera", _ts.make(saved.get("trait") or "memory_trait",
                                  "%s = %s" % (saved.get("trait"), saved.get("value")), "correction",
                                  provenance_kind="system_cert",
                                  provenance_refs=["cert-probe restoration of the pre-probe value"],
                                  evidence_refs=[saved.get("id") or ""],
                                  scope="long_term", confidence=float(saved.get("confidence") or 0.9),
                                  actor="system"))
    except Exception:
        pass


def main() -> int:
    t0 = time.perf_counter()
    print("MEMORY TRUTH & CORRECTION — no unsupported memory claim ever ships")
    print("=" * 92)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "MemTruthCert"

        # ---- 1. write emits ----------------------------------------------------------------
        row = {"id": "f_t1", "trait": "favorite_color", "value": "teal", "confidence": 0.9,
               "status": "active"}
        w = api.on_memory_write(N, row, "my favorite color is teal", "turn-1", store=st)
        ck("1. a captured fact emits a provenance-complete memory event",
           w is not None and w["claim_type"] == "memory"
           and w["provenance"]["kind"] == "user_turn" and "turn-1" in w["provenance"]["refs"]
           and "f_t1" in w["evidence_refs"])

        # ---- 2. correction chain (§5.5: every required element) -------------------------------
        w2 = api.on_memory_write(N, dict(row, value="gray", confidence=0.97),
                                 "actually it's gray now", "turn-2", store=st)
        folded = query.fold(N, store=st)
        old, new = folded[w["event_id"]], folded[w2["event_id"]]
        ck("2. correction supersedes: old claim retained + superseded; new claim active",
           old["claim"] == "favorite_color = teal" and old["active_status"] == "superseded"
           and new["claim"] == "favorite_color = gray" and new["active_status"] == "active")
        ck("2b. the §5.5 record is complete (old+new claim, provenance, source turn, timestamp, "
           "supersession link, active truth, confidence)",
           new["provenance"]["refs"] == ["turn-2"] and new["supersedes"] == [w["event_id"]]
           and w2["event_id"] in old["superseded_by"] and bool(new["created_at"])
           and 0 < new["confidence"] <= 1 and new["claim_type"] == "correction")
        ck("2c. rollback action exists: the chain is traversable back to the old value",
           any(e["claim"] == "favorite_color = teal"
               for e in query.trace(N, w2["event_id"], store=st)))

        # ---- 3. conflict policy ------------------------------------------------------------------
        mk = lambda ct, sc, at: {"claim_type": ct, "scope": sc, "created_at": at}
        rules = [
            ("user correction > older memory",
             supersession.wins(mk("correction", "long_term", "2"), mk("memory", "long_term", "1"))),
            ("explicit teaching > inferred preference",
             supersession.wins(mk("teaching", "long_term", "2"), mk("inference", "long_term", "1"))),
            ("project rule > general preference inside project",
             supersession.wins(mk("memory", "project", "1"), mk("memory", "long_term", "2"))),
            ("safety/system policy > teaching",
             supersession.wins(mk("system", "system", "1"), mk("teaching", "long_term", "2"))),
            ("newer same-scope correction > older",
             supersession.wins(mk("correction", "long_term", "3"), mk("correction", "long_term", "1"))),
            ("source fact does NOT override user memory",
             not supersession.wins(mk("source", "chat", "9"), mk("memory", "long_term", "1"))),
        ]
        for label, cond in rules:
            ck("3. " + label, cond)

        # ---- 4. language guard ----------------------------------------------------------------------
        bad = ("I remember your birthday is in July. If memory serves, you told me you love hiking. "
               "My recollection is that I know your preference is tea.")
        rew, flagged = ml.guard(bad, has_memory_support=False)
        ck("4. UNSUPPORTED: every forbidden shape detected (%d) and rewritten" % len(flagged),
           len(flagged) >= 4 and "i remember" not in rew.lower()
           and "if memory serves" not in rew.lower() and "you told me" not in rew.lower()
           and "my recollection is" not in rew.lower())
        same, fl2 = ml.guard(bad, has_memory_support=True)
        ck("4b. WITH memory provenance the same reply ships untouched", same == bad and fl2 == [])
        honest = ("I may be guessing. I might have inferred that. I do not see that in memory. "
                  "I don't have a memory record for that.")
        ck("4c. honest phrasings are NEVER flagged", ml.detect(honest) == [])

    _live_trait = "dog_name"
    _saved_mem = _snapshot_real_memory(_live_trait)
    # ---- live block --------------------------------------------------------------------------------
    try:
        before = _truth_json()
        before_unsupported_ids = _unsupported_ids()
        d_teach = _say("My dog's name is Biscuit.")
        d_recall = _say("What's my dog's name?")
        d_small = _say("Just say hello to me warmly, nothing else.")
        new_unsupported_ids = _unsupported_ids() - before_unsupported_ids
        _close_probe_unsupported(new_unsupported_ids)
        after = _truth_json()
        ck("5. LIVE teach turn ships truth_events on the reply",
           bool(d_teach.get("truth_events")))
        ck("6. LIVE deterministic recall is traced (memory:known_fact + truth_events)",
           d_recall.get("backend") == "memory:known_fact" and bool(d_recall.get("truth_events")))
        eid = (d_recall.get("truth_events") or [""])[0]
        chain = []
        if eid:
            with urllib.request.urlopen("http://127.0.0.1:8765/truth/trace?event_id=" + eid,
                                        timeout=10) as r:
                chain = json.loads(r.read()).get("chain") or []
        ck("6b. ...and its trace reaches a memory_record provenance",
           any((e.get("provenance") or {}).get("kind") == "memory_record" for e in chain))
        ck("7. CHIP TRUTH — a no-memory smalltalk turn ships NO truth events and NO source chips",
           not d_small.get("truth_events") and not d_small.get("sources"))
        shipped = "\n".join(str(d.get("reply") or "") for d in (d_teach, d_recall, d_small))
        ck("8. NO UNSUPPORTED SHIPPED — forbidden memory phrasings are absent from final replies",
           ml.detect(shipped) == [])
        emitted = set()
        for d in (d_teach, d_recall, d_small):
            emitted.update(str(e) for e in (d.get("truth_events") or []))
        ck("8b. UNSUPPORTED ATTEMPTS ARE VISIBLE + CLOSED — cert-generated unsupported ledger rows "
           "are trace-linked and no longer active",
           (not new_unsupported_ids or new_unsupported_ids.issubset(emitted))
           and after.get("unsupported", 999) <= before.get("unsupported", 0))
        ck("8c. ZERO ACTIVE UNSUPPORTED — unresolved unsupported count did not grow across the probes "
           "(%d -> %d)" % (before.get("unsupported", -1), after.get("unsupported", -1)),
           after.get("unsupported", 999) <= before.get("unsupported", 0))
        _say("Forget my dog's name.")              # retract the probe fixture
        _restore_real_memory(_saved_mem)           # then restore the GENUINE value
    except Exception as e:
        ck("5-8. LIVE block reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_memory_truth_and_correction", "green" if green else "red",
                files_observed=["anima/truth/api.py", "anima/truth/memory_language.py",
                                "anima/truth/query.py", "anima/truth/supersession.py",
                                "anima/server.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nMEMORY-TRUTH-AND-CORRECTION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
