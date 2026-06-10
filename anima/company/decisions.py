"""company.decisions — the Decision Ledger. Vera remembers decisions like a founder operator.

A decision is proposed, approved (becomes durable + emits a Truth Ledger event), can be
superseded by a newer decision, or reopened. "Why did we decide this?" is answerable from the
record (rationale + options + tradeoffs + evidence + supersession chain).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import storage

TYPES = ("product", "architecture", "release", "host_support", "memory_policy",
         "knowledge_pack_policy", "security", "business", "marketing", "pricing", "hiring",
         "customer", "investor")
STATUSES = ("proposed", "decided", "superseded", "reopened", "retracted")
REVERSIBILITY = ("one_way", "two_way", "expensive_to_reverse", "unknown")


def new_id() -> str:
    return "dec_" + uuid.uuid4().hex[:12]


def _all(name: str, store: Path | None = None) -> list:
    return storage.load(name, "decisions", store, default={"decisions": []}).get("decisions", [])


def _save(name: str, recs: list, store: Path | None = None) -> None:
    storage.save(name, "decisions", {"decisions": recs}, store)


def propose(name: str, title: str, decision: str, *, dtype: str = "product", context: str = "",
            options_considered=None, rationale: str = "", tradeoffs=None, risks=None,
            reversibility: str = "two_way", evidence_refs=None, store: Path | None = None) -> dict:
    if dtype not in TYPES:
        return {"ok": False, "error": "unknown decision type %r" % dtype}
    if reversibility not in REVERSIBILITY:
        reversibility = "unknown"
    rec = {
        "decision_id": new_id(), "title": title[:200], "decision": decision[:2000],
        "type": dtype, "context": context[:2000], "options_considered": options_considered or [],
        "rationale": rationale[:2000], "tradeoffs": tradeoffs or [], "risks": risks or [],
        "reversibility": reversibility, "owner": "Lamar", "status": "proposed",
        "date_decided": None, "review_date": None, "evidence_refs": evidence_refs or [],
        "truth_ledger_event": None, "supersedes": [], "superseded_by": [],
        "created_at": storage.now(),
    }
    recs = _all(name, store)
    recs.append(rec)
    _save(name, recs, store)
    return {"ok": True, "decision": rec}


def get(name: str, decision_id: str, store: Path | None = None) -> dict | None:
    return next((d for d in _all(name, store) if d["decision_id"] == decision_id), None)


def approve(name: str, decision_id: str, *, supersedes=None, by: str = "founder",
            store: Path | None = None) -> dict:
    recs = _all(name, store)
    rec = next((d for d in recs if d["decision_id"] == decision_id), None)
    if rec is None:
        return {"ok": False, "error": "no such decision"}
    if rec["status"] not in ("proposed", "reopened"):
        return {"ok": False, "error": "decision is %s" % rec["status"]}
    rec["status"] = "decided"
    rec["date_decided"] = storage.now()
    sup_ids = list(supersedes or [])
    if sup_ids:
        rec["supersedes"] = sup_ids
        for d in recs:
            if d["decision_id"] in sup_ids and d["status"] == "decided":
                d["status"] = "superseded"
                d.setdefault("superseded_by", []).append(decision_id)
    ev = storage.emit_truth(name, "decision", decision_id, "DECIDED: %s — %s"
                            % (rec["title"], rec["decision"][:200]),
                            provenance_kind="user_turn", actor="user",
                            evidence_refs=rec.get("evidence_refs"),
                            supersedes=[d.get("truth_ledger_event") for d in recs
                                        if d["decision_id"] in sup_ids and d.get("truth_ledger_event")],
                            store=store)
    rec["truth_ledger_event"] = ev
    _save(name, recs, store)
    return {"ok": True, "decision": rec, "truth_ledger_event": ev}


def reopen(name: str, decision_id: str, *, reason: str = "", store: Path | None = None) -> dict:
    recs = _all(name, store)
    rec = next((d for d in recs if d["decision_id"] == decision_id), None)
    if rec is None:
        return {"ok": False, "error": "no such decision"}
    rec["status"] = "reopened"
    rec.setdefault("reopen_reasons", []).append({"at": storage.now(), "reason": reason})
    _save(name, recs, store)
    return {"ok": True, "decision": rec}


def views(name: str, store: Path | None = None) -> dict:
    recs = _all(name, store)
    return {
        "recent": sorted(recs, key=lambda d: d["created_at"], reverse=True)[:20],
        "open": [d for d in recs if d["status"] in ("proposed", "reopened")],
        "needing_review": [d for d in recs if d.get("review_date") and d["status"] == "decided"],
        "superseded": [d for d in recs if d["status"] == "superseded"],
        "high_risk": [d for d in recs if d.get("risks")],
        "one_way": [d for d in recs if d.get("reversibility") == "one_way"],
        "all": recs,
    }
