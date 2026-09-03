"""truth.learning_view — the Learning Integrity aggregator.

One read-only view over the truth ledger + teaching queue + auto-learn queue + knowledge-pack
facts + rollback history, so the /learning surface can show what Vera knows, why, what changed,
and what was reversed — every row tied to a Truth Ledger event id (the "why do you think that?"
answer). Pure read; never mutates.
"""
from __future__ import annotations

from pathlib import Path

from . import query


def _row(ev: dict) -> dict:
    return {
        "event_id": ev.get("event_id"),
        "subject": ev.get("subject"),
        "claim": ev.get("claim"),
        "type": ev.get("claim_type"),
        "scope": ev.get("scope"),
        "status": ev.get("active_status"),
        "confidence": ev.get("confidence"),
        "evidence": ev.get("evidence_refs") or [],
        "source": (ev.get("provenance") or {}).get("kind"),
        "created_at": ev.get("created_at"),
        "supersedes": ev.get("supersedes") or [],
        "superseded_by": ev.get("superseded_by") or [],
    }


def build(name: str, store: Path | None = None) -> dict:
    """Every learning-integrity section, evidence-linked. Degrades gracefully if a subsystem
    has no data yet (empty list, never invented content)."""
    folded = list(query.fold(name, store).values())
    by_status = {}
    for ev in folded:
        by_status.setdefault(ev.get("active_status", "?"), []).append(ev)

    active = [_row(e) for e in by_status.get("active", [])]
    corrections = [_row(e) for e in folded if e.get("claim_type") == "correction"
                   and e.get("active_status") != "retracted"]
    retracted = [_row(e) for e in by_status.get("retracted", [])]
    conflicts = [_row(e) for e in by_status.get("conflict", [])]
    unsupported = [_row(e) for e in query.unsupported(name, store)]

    teaching_drafts, auto_learn, pack_facts, rollback_hist = [], [], [], []
    try:
        from anima.teaching import queue as tq
        teaching_drafts = [{"id": r.get("teaching_id"), "type": r.get("type"),
                            "content": (r.get("content") or "")[:200],
                            "state": r.get("approval_state"), "scope": r.get("scope"),
                            "truth_event": r.get("truth_ledger_event")}
                           for r in tq.load(name, store)]
    except Exception:
        pass
    try:
        from anima.auto_learn import queue as alq
        auto_learn = [{"id": r.get("auto_learn_id"), "proposed": (r.get("proposed_learning") or "")[:200],
                       "status": r.get("status"), "risk": r.get("risk"),
                       "confidence": r.get("confidence")}
                      for r in alq.load(name, store)]
    except Exception:
        pass
    pack_facts = [_row(e) for e in folded if e.get("claim_type") == "pack_fact"]
    try:
        from anima.rollback import apply as rb
        rollback_hist = rb.history(name, store)
    except Exception:
        pass

    return {
        "ok": True,
        "sections": {
            "active_memories": [r for r in active if r["type"] == "memory"],
            "corrections": corrections,
            "retracted_memories": retracted,
            "unsupported_claims": unsupported,
            "conflicts": conflicts,
            "teaching_drafts": teaching_drafts,
            "auto_learn_suggestions": auto_learn,
            "knowledge_pack_facts": pack_facts,
            "rollback_history": rollback_hist,
        },
        "counts": {
            "active": len(active), "corrections": len(corrections),
            "retracted": len(retracted), "unsupported": len(unsupported),
            "conflicts": len(conflicts), "teaching_drafts": len(teaching_drafts),
            "auto_learn": len(auto_learn), "pack_facts": len(pack_facts),
            "rollbacks": len(rollback_hist),
        },
        "integrity": {
            "unsupported_claims": len(unsupported),
            "unproven_active_memory": len([r for r in active
                                           if r["type"] == "memory" and not r["evidence"]]),
        },
    }
