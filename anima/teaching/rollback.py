"""teaching.rollback — every persisted teaching is reversible, and the reversal is recorded.

Rollback: (1) undoes the persistence (retracts the LIRF row for memory-targeted teachings;
deactivates the policy record otherwise), (2) marks the record rolled_back, (3) emits a Truth
Ledger event, (4) records the full rollback record (rollback_id, target, previous/new state,
actor, timestamp, reason).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from anima import secure_store

from . import queue, schema


def _store(store: Path | None) -> Path:
    return store or Path(os.environ.get("ANIMA_STORE", ".anima"))


def _log_rollback(name: str, rec: dict, store: Path | None) -> None:
    secure_store.append_jsonl(_store(store) / f"{name}.rollbacks.jsonl", rec)


def rollback(name: str, teaching_id: str, *, reason: str = "user requested rollback",
             by: str = "user", store: Path | None = None) -> dict:
    rec = queue.get(name, teaching_id, store)
    if rec is None:
        return {"ok": False, "error": "no such teaching record"}
    if rec.get("approval_state") != "approved":
        return {"ok": False, "error": "only an approved teaching can be rolled back (state: %s)"
                                      % rec.get("approval_state")}
    prev_state = rec["approval_state"]
    # 1. undo persistence
    undone = "policy-record deactivated"
    if rec.get("target_store") == "memory" and rec.get("_memory_row"):
        try:
            from anima.memory_lirf import Facts
            f = Facts.load(name)
            for r in f.rows:
                if r.get("id") == rec["_memory_row"] and r.get("status") == "active":
                    f.retract(r["id"])
                    undone = "memory row %s retracted" % rec["_memory_row"]
                    break
            f.save(name)
        except Exception as e:
            return {"ok": False, "error": "memory rollback failed: %r" % e}
    # 2. mark rolled back
    rec = queue.update(name, teaching_id, to_state="rolled_back", by=by, store=store)
    # 3. truth event
    ev_id = None
    try:
        from anima.truth import ledger as tl, schema as ts
        ev = ts.make("teaching:%s" % rec["type"],
                     "ROLLED BACK teaching %s (%s)" % (teaching_id, reason), "correction",
                     provenance_kind="teaching_record", provenance_refs=[teaching_id],
                     supersedes=[rec["truth_ledger_event"]] if rec.get("truth_ledger_event") else [],
                     scope="long_term", confidence=1.0, actor="user",
                     active_status="retracted")
        tl.emit(name, ev, store=store)
        ev_id = ev["event_id"]
    except Exception:
        pass
    # 4. the rollback record
    rb = {
        "rollback_id": rec.get("rollback_id") or "rb_unallocated",
        "target_event": rec.get("truth_ledger_event"),
        "target_kind": "teaching_record",
        "target_id": teaching_id,
        "previous_state": prev_state,
        "new_state": "rolled_back",
        "actor": by,
        "timestamp": schema.now(),
        "reason": reason,
        "truth_ledger_event": ev_id,
        "undone": undone,
    }
    _log_rollback(name, rb, store)
    return {"ok": True, "record": rec, "rollback": rb}
