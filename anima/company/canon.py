"""company.canon — the structured company self-model. Not a freeform memory file.

Canon changes are never silent: each requires an explicit approval (founder teaching / approved
update / certified source import / manual edit), emits a Truth Ledger event, and is reversible.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import storage

REQUIRED_FIELDS = ("company_name", "founder", "mission", "product_name", "product_category",
                   "core_doctrine", "current_product_state", "target_users", "non_goals",
                   "active_release_tier", "known_deferred_features", "known_enterprise_only_features",
                   "current_host_strategy", "privacy_position", "trust_position",
                   "last_reviewed_at", "truth_ledger_refs")

_DEFAULT = {
    "company_name": "Collatio Labs",
    "founder": "Lamar",
    "mission": "(set via canon update)",
    "product_name": "Vera",
    "product_category": "local-first personal/company intelligence layer",
    "core_doctrine": ["No fake green", "Build reality, prove reality, show reality",
                      "Memory claims need provenance"],
    "current_product_state": "(set via canon update)",
    "target_users": [],
    "non_goals": [],
    "active_release_tier": "Local/Internal",
    "known_deferred_features": ["audiobook_intake"],
    "known_enterprise_only_features": ["enterprise_readiness"],
    "current_host_strategy": "capability-certified Host Fit, not chip generation",
    "privacy_position": "local-first; nothing leaves the Mac without approval",
    "trust_position": "every claim traces to a Truth Ledger event",
    "last_reviewed_at": None,
    "truth_ledger_refs": [],
    "_pending": [],
    "_history": [],
}


def load(name: str, store: Path | None = None) -> dict:
    c = storage.load(name, "canon", store, default=None)
    if not c:
        c = dict(_DEFAULT)
        storage.save(name, "canon", c, store)
    return c


def validate(c: dict) -> list[str]:
    return [f"missing {k!r}" for k in REQUIRED_FIELDS if k not in c]


def propose_change(name: str, field: str, value, *, reason: str = "", store: Path | None = None) -> dict:
    """Stage a canon change. Nothing durable until approved."""
    if field not in REQUIRED_FIELDS:
        return {"ok": False, "error": "unknown canon field %r" % field}
    c = load(name, store)
    pid = "cc_" + uuid.uuid4().hex[:12]
    c["_pending"].append({"pending_id": pid, "field": field, "value": value, "reason": reason,
                          "at": storage.now(), "status": "pending"})
    storage.save(name, "canon", c, store)
    return {"ok": True, "pending_id": pid}


def approve_change(name: str, pending_id: str, *, by: str = "founder", store: Path | None = None) -> dict:
    c = load(name, store)
    pend = next((p for p in c["_pending"] if p["pending_id"] == pending_id), None)
    if pend is None or pend["status"] != "pending":
        return {"ok": False, "error": "no pending canon change %r" % pending_id}
    old = c.get(pend["field"])
    c["_history"].append({"field": pend["field"], "old": old, "new": pend["value"],
                          "at": storage.now(), "by": by, "pending_id": pending_id})
    c[pend["field"]] = pend["value"]
    c["last_reviewed_at"] = storage.now()
    pend["status"] = "approved"
    ev = storage.emit_truth(name, "canon", pend["field"],
                            "canon.%s = %r" % (pend["field"], pend["value"]),
                            provenance_kind="user_turn", actor="user", store=store)
    if ev:
        c.setdefault("truth_ledger_refs", []).append(ev)
    storage.save(name, "canon", c, store)
    return {"ok": True, "field": pend["field"], "truth_ledger_event": ev}


def rollback_change(name: str, field: str, *, store: Path | None = None) -> dict:
    """Revert a field to its prior value from history."""
    c = load(name, store)
    hist = [h for h in c["_history"] if h["field"] == field]
    if not hist:
        return {"ok": False, "error": "no history for %r" % field}
    last = hist[-1]
    c[field] = last["old"]
    c["_history"].append({"field": field, "old": last["new"], "new": last["old"],
                          "at": storage.now(), "by": "rollback", "rolled_back": True})
    ev = storage.emit_truth(name, "canon", field, "ROLLBACK canon.%s -> %r" % (field, last["old"]),
                            actor="user", active_status="retracted", store=store)
    storage.save(name, "canon", c, store)
    return {"ok": True, "field": field, "restored": last["old"], "truth_ledger_event": ev}
