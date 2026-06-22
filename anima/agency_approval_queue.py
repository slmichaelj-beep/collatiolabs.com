"""agency_approval_queue — the Founder Approval Queue. Suggestions wait here; NOTHING executes.

Flow:  submit(suggestion) -> logs the intent + queues it (status 'proposed')
       approve(id)        -> records the founder's YES (audited)  -- does NOT execute, does NOT flip execution_allowed
       reject(id)         -> records the founder's NO  (audited)
       pending()/status() -> what's waiting / the tallies

THE LOAD-BEARING INVARIANT: approval records a decision, it never grants execution. ``execution_allowed``
is pinned False on every transition in this module. Execution is Wave 2B, a separate certified path with
its own preview->approve->execute->audit->undo gate. The queue persists across restart, per-creature.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import secure_store
from . import agency_intent_ledger as _ledger

STORE = Path(".anima")


def _path(name: str) -> Path:
    return STORE / f"{name}.agency_queue.json"


def _load(name: str) -> list:
    data = secure_store.load_json(_path(name), []) or []
    return data if isinstance(data, list) else []


def _save(name: str, items: list) -> None:
    try:
        secure_store.save_json(_path(name), items)
    except Exception:
        pass


def _audit(kind: str, detail: str, **extra) -> None:
    try:
        from . import incident
        incident.security_event(kind, detail, **extra)
    except Exception:
        pass


def submit(name: str, suggestion: dict) -> dict:
    """Log the intent and place the suggestion in the queue (status 'proposed'). Executes nothing."""
    _ledger.log_intent(name, suggestion)
    items = _load(name)
    items.append(suggestion)
    _save(name, items)
    _audit("agency_suggestion", "Vera proposed an action (suggest-only, awaiting founder approval)",
           intent_id=suggestion.get("intent_id"), action_type=suggestion.get("action_type"),
           risk=suggestion.get("risk"))
    return suggestion


def get(name: str, intent_id: str):
    for it in _load(name):
        if it.get("intent_id") == intent_id:
            return it
    return None


def pending(name: str) -> list:
    return [it for it in _load(name) if it.get("status") in ("proposed", "pending")]


def _decide(name: str, intent_id: str, status: str, by: str):
    items = _load(name)
    hit = None
    for it in items:
        if it.get("intent_id") == intent_id:
            it["status"] = status
            it["decided_by"] = str(by)
            it["execution_allowed"] = False     # INVARIANT: approval NEVER grants execution here
            hit = it
    if hit is not None:
        _save(name, items)
    return hit


def approve(name: str, intent_id: str, *, by: str = "founder"):
    """Record the founder's approval. Does NOT execute and does NOT flip execution_allowed."""
    it = _decide(name, intent_id, "approved", by)
    if it is not None:
        _audit("agency_approve", "Founder approved a suggestion (execution still gated to Wave 2B)",
               intent_id=intent_id, by=by, action_type=it.get("action_type"))
    return it


def reject(name: str, intent_id: str, *, by: str = "founder"):
    """Record the founder's rejection. The suggestion can never execute."""
    it = _decide(name, intent_id, "rejected", by)
    if it is not None:
        _audit("agency_reject", "Founder rejected a suggestion", intent_id=intent_id, by=by)
    return it


def status(name: str) -> dict:
    items = _load(name)
    return {"counts": dict(Counter(it.get("status") for it in items)),
            "pending": pending(name), "total": len(items)}
