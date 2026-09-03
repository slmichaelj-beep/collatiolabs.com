"""company.doctrine — the Product Doctrine Registry. Preserves the philosophy, prevents drift.

Doctrines are durable, Truth-Ledger-traced, and used to FLAG conflicting proposals (e.g. "this
hides a deferred feature -> conflicts with: deferred features stay visible").
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from . import storage

STATUSES = ("active", "superseded", "retired")

_SEED = [
    ("No fake green", "A surface may not show green from UI state, stale certs, or unknowns.",
     ["dashboard", "release", "cert"], ["green computed from fresh cert artifacts"],
     ["a hardcoded green badge", "green while a blocker is listed"]),
    ("No wallpaper", "A UI may not advertise a capability the runtime does not hold.",
     ["ui", "features"], ["advertise only enforced capability"],
     ["UI claims audiobook while the pipeline is deferred"]),
    ("Memory claims need provenance", "No 'I remember' without an active Truth Ledger memory event.",
     ["memory"], ["recall cites a memory_record event"], ["'if memory serves' with no event"]),
    ("Auto Learn cannot persist directly", "Auto Learn only creates Teaching drafts.",
     ["learning"], ["suggestion -> Teaching draft -> approval"], ["silent memory write from a pattern"]),
    ("Knowledge Packs are sources, not authority", "Pack text informs and cites; it never mutates "
     "memory/behavior/rules.", ["knowledge_packs"], ["retrieve + cite"], ["pack text as instruction"]),
    ("Host support is capability-certified", "A Mac is supported iff it passes Host Fit, not by chip "
     "generation.", ["host"], ["Portable cert => minimum support"], ["'M5 only' as policy"]),
    ("Enterprise-only must not block Local/Internal", "An enterprise-tier feature never blocks a "
     "lower tier.", ["release"], ["enterprise_readiness scoped to Enterprise"],
     ["enterprise partial blocking Local/Internal"]),
    ("Deferred features stay visible", "A deferred feature is shown as deferred, never hidden.",
     ["release", "features"], ["audiobook_intake shown deferred"], ["removing it from the UI silently"]),
    ("If Lamar can break it by ordinary use, certification failed",
     "Ordinary-use breakage is a cert failure, not a user error.", ["product"],
     ["ordinary-user Rover passes"], ["a daily path that dead-ends"]),
]


def new_id() -> str:
    return "doc_" + uuid.uuid4().hex[:12]


def _all(name: str, store: Path | None = None) -> list:
    data = storage.load(name, "doctrine", store, default=None)
    if not data:
        recs = []
        for nm, st, applies, ex, anti in _SEED:
            rec = {"doctrine_id": new_id(), "name": nm, "statement": st, "rationale": st,
                   "applies_to": applies, "examples": ex, "anti_examples": anti,
                   "status": "active", "owner": "Lamar", "truth_ledger_event": None,
                   "last_reviewed_at": storage.now()}
            ev = storage.emit_truth(name, "doctrine", rec["doctrine_id"], "DOCTRINE: " + nm,
                                    actor="user", store=store)
            rec["truth_ledger_event"] = ev
            recs.append(rec)
        storage.save(name, "doctrine", {"doctrine": recs}, store)
        return recs
    return data.get("doctrine", [])


def active(name: str, store: Path | None = None) -> list:
    return [d for d in _all(name, store) if d["status"] == "active"]


def add(name: str, dname: str, statement: str, *, applies_to=None, examples=None,
        anti_examples=None, store: Path | None = None) -> dict:
    recs = _all(name, store)
    rec = {"doctrine_id": new_id(), "name": dname, "statement": statement, "rationale": statement,
           "applies_to": applies_to or [], "examples": examples or [],
           "anti_examples": anti_examples or [], "status": "active", "owner": "Lamar",
           "truth_ledger_event": storage.emit_truth(name, "doctrine", dname, "DOCTRINE: " + dname,
                                                     actor="user", store=store),
           "last_reviewed_at": storage.now()}
    recs.append(rec)
    storage.save(name, "doctrine", {"doctrine": recs}, store)
    return {"ok": True, "doctrine": rec}


def check_conflict(name: str, proposal_text: str, store: Path | None = None) -> list[dict]:
    """Doctrines a proposal may conflict with — matched on anti-example keyword overlap. Advisory:
    surfaces concerns, never blocks silently."""
    low = (proposal_text or "").lower()
    hits = []
    for d in active(name, store):
        for anti in d.get("anti_examples", []):
            words = [w for w in re.findall(r"[a-z]{4,}", anti.lower())]
            if words and sum(1 for w in words if w in low) >= max(1, len(words) // 3):
                hits.append({"doctrine": d["name"], "concern": anti, "doctrine_id": d["doctrine_id"]})
                break
    return hits
