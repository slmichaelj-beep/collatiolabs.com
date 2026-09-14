"""teaching.apply — the ONLY path from a teaching record to durable persistence.

Approval is explicit; sensitive risk requires a second explicit confirmation; rejection persists
nothing; an edit persists the edited form only; everything persisted emits a Truth Ledger event
and allocates a rollback id. Teaching cannot bypass Memory Truth: a memory-targeted teaching
rides the SAME LIRF merge path every user fact takes.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import queue, review, schema


def _truth(name, rec, store: Path | None):
    """Emit the teaching event into the Truth Ledger; returns the event id (or None, guarded)."""
    try:
        from anima.truth import ledger as tl, schema as ts
        ev = ts.make(("teaching:%s" % rec["type"]), rec["content"][:500], "teaching",
                     provenance_kind="teaching_record",
                     provenance_refs=[rec["teaching_id"]] + list(rec.get("evidence_turns") or []),
                     evidence_refs=[rec["teaching_id"]],
                     scope=("project" if rec["scope"] == "project"
                            else ("chat" if rec["scope"] == "chat" else "long_term")),
                     confidence=0.95, actor="user",
                     risk=rec.get("risk", "low"))
        tl.emit(name, ev, store=store)
        return ev["event_id"]
    except Exception:
        return None


def approve(name: str, teaching_id: str, *, edited_content: str | None = None,
            confirm_sensitive: bool = False, by: str = "user",
            store: Path | None = None) -> dict:
    """Approve (optionally with an edit). Returns {ok, record|error, conflicts}."""
    rec = queue.get(name, teaching_id, store)
    if rec is None:
        return {"ok": False, "error": "no such teaching record"}
    if rec["approval_state"] not in ("pending", "edited"):
        return {"ok": False, "error": "record is %s — only pending/edited can be approved"
                                      % rec["approval_state"]}
    if rec.get("risk") == "sensitive" and not confirm_sensitive:
        return {"ok": False, "error": "sensitive teaching requires explicit confirmation "
                                      "(confirm_sensitive)", "needs_confirmation": True}
    if edited_content is not None and edited_content.strip() != rec["content"].strip():
        rec = queue.update(name, teaching_id, to_state="edited", by=by,
                           patch={"content": edited_content.strip()}, store=store)
    conflicts = review.conflicts(name, rec, store=store)
    # persist to the target store
    rollback_id = "rb_" + uuid.uuid4().hex[:12]
    if rec["scope"] == "chat":
        # chat-only: approved but deliberately NON-durable — nothing written to any store
        ev = _truth(name, rec, store)
        rec = queue.update(name, teaching_id, to_state="approved", by=by,
                           patch={"truth_ledger_event": ev, "rollback_id": rollback_id},
                           store=store)
        return {"ok": True, "record": rec, "durable": False, "conflicts": conflicts}
    if rec["target_store"] == "memory":
        try:
            from anima.memory_lirf import Facts, canon_trait
            f = Facts.load(name)
            # the SAME merge path every user fact rides — teaching cannot bypass Memory Truth
            row = f.merge({"trait": canon_trait(rec["type"] if rec["type"] != "preference"
                                                else "preference"),
                           "value": rec["content"][:400],
                           "evidence": "teaching %s" % rec["teaching_id"],
                           "correction": True,
                           "source": "teaching %s" % rec["teaching_id"]})
            f.save(name)
            rec = queue.update(name, teaching_id, patch={"_memory_row": row.get("id")},
                               store=store)
        except Exception as e:
            return {"ok": False, "error": "memory persistence failed: %r" % e}
    elif rec["target_store"] in ("behavior_policy", "project_context"):
        pass            # the approved teaching record itself IS the durable policy store (v1)
    elif rec["target_store"] == "knowledge_pack":
        return {"ok": False, "error": "knowledge_pack targets land in Increment 5 — propose as "
                                      "domain_note/behavior until the pack registry exists"}
    ev = _truth(name, rec, store)
    rec = queue.update(name, teaching_id, to_state="approved", by=by,
                       patch={"truth_ledger_event": ev, "rollback_id": rollback_id}, store=store)
    return {"ok": True, "record": rec, "durable": True, "conflicts": conflicts}


def reject(name: str, teaching_id: str, by: str = "user", store: Path | None = None) -> dict:
    rec = queue.update(name, teaching_id, to_state="rejected", by=by, store=store)
    return {"ok": rec is not None, "record": rec}
