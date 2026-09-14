"""company.founder_queue — what requires Lamar. Vera never silently decides a founder-only question.

An open question is raised; answering it CREATES a decision record (decisions.py) and closes the
queue item. A blocking item is surfaced first. Vera proposes a recommended option but does not
self-approve.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import decisions, storage

URGENCY = ("low", "medium", "high", "blocking")


def _all(name, store): return storage.load(name, "founder_queue", store, default={"items": []})["items"]
def _save(name, items, store): storage.save(name, "founder_queue", {"items": items}, store)


def raise_question(name, question, *, why_it_matters="", decision_type="product",
                   urgency="medium", options=None, recommended_option=None, evidence_refs=None,
                   needed_by=None, store: Path | None = None) -> dict:
    rec = {"item_id": "fq_" + uuid.uuid4().hex[:12], "question": question[:500],
           "why_it_matters": why_it_matters[:1000], "decision_type": decision_type,
           "urgency": urgency if urgency in URGENCY else "medium",
           "options": options or [], "recommended_option": recommended_option,
           "evidence_refs": evidence_refs or [], "status": "open",
           "created_at": storage.now(), "needed_by": needed_by, "decision_id": None}
    items = _all(name, store); items.append(rec); _save(name, items, store)
    storage.emit_truth(name, "founder_question", rec["item_id"], "FOUNDER Q: " + question[:160],
                       actor="vera", store=store)
    return {"ok": True, "item": rec}


def get(name, item_id, store): return next((i for i in _all(name, store) if i["item_id"] == item_id), None)


def answer(name, item_id, *, decision_text, rationale="", reversibility="two_way",
           store: Path | None = None) -> dict:
    """Answering a founder question CREATES + APPROVES a decision record (founder authority) and
    closes the item. Vera cannot call this itself for a founder-only question — the caller is the
    founder action surface."""
    items = _all(name, store)
    rec = next((i for i in items if i["item_id"] == item_id), None)
    if rec is None:
        return {"ok": False, "error": "no such question"}
    if rec["status"] != "open":
        return {"ok": False, "error": "question is %s" % rec["status"]}
    p = decisions.propose(name, rec["question"][:200], decision_text,
                          dtype=rec["decision_type"], rationale=rationale,
                          reversibility=reversibility, evidence_refs=rec["evidence_refs"], store=store)
    a = decisions.approve(name, p["decision"]["decision_id"], store=store)
    rec["status"] = "answered"
    rec["decision_id"] = p["decision"]["decision_id"]
    _save(name, items, store)
    return {"ok": True, "decision_id": rec["decision_id"], "truth_ledger_event": a.get("truth_ledger_event")}


def defer(name, item_id, store: Path | None = None) -> dict:
    items = _all(name, store)
    for i in items:
        if i["item_id"] == item_id:
            i["status"] = "deferred"
            _save(name, items, store)
            return {"ok": True}
    return {"ok": False, "error": "no such question"}


def open_items(name, store: Path | None = None) -> list:
    order = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
    return sorted([i for i in _all(name, store) if i["status"] in ("open", "deferred")],
                  key=lambda i: order.get(i["urgency"], 9))
