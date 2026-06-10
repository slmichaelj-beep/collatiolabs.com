"""commercial.sales_sprint — a governed sales sprint with a human-approval queue.

A sprint bundles prepared outreach actions (each a drafted message to a qualified lead) into ONE
approval queue. Nothing sends. Every item is queued for explicit human approval; sending is a human
action. Lead sourcing is prepared lists only — no scraping, no spam, no fabricated contacts. The
sprint tracks status and feeds the pipeline command center.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from .sales_mastery import core as _core, engagement as _eng

ITEM_STATUS = ("queued", "approved", "sent_by_human", "skipped")


def open_sprint(name: str, *, goal: str, offer_id: str = "", store: Path | None = None) -> dict:
    rec = {"sprint_id": "sp_" + uuid.uuid4().hex[:10], "goal": goal, "offer_id": offer_id,
           "status": "open", "items": [], "created_at": storage.now()}
    _save(name, rec, store)
    storage.emit_truth(name, "sales_sprint", rec["sprint_id"], "SPRINT opened: " + goal,
                       actor="user", store=store)
    return rec


def _save(name, rec, store): storage.save(name, "sales_sprint_%s" % rec["sprint_id"], rec, store)
def _load(name, sprint_id, store): return storage.load(name, "sales_sprint_%s" % sprint_id, store, default=None)


def queue_outreach(name: str, sprint_id: str, *, lead_id: str, message_rec: dict,
                   store: Path | None = None) -> dict:
    """Queue a drafted outreach item. Refuses if the lead can't be contacted (consent/qualify gate).
    The item is QUEUED — it is never auto-sent."""
    rec = _load(name, sprint_id, store)
    if rec is None:
        return {"ok": False, "error": "no such sprint"}
    contact = _core.can_contact(name, lead_id, store=store)
    if not contact.get("allowed"):
        return {"ok": False, "error": "lead not contactable", "reason": contact}
    item = {"item_id": "it_" + uuid.uuid4().hex[:8], "lead_id": lead_id,
            "message": message_rec, "status": "queued", "approval_ref": None,
            "queued_at": storage.now()}
    rec["items"].append(item)
    _save(name, rec, store)
    storage.emit_truth(name, "sales_sprint", sprint_id, "OUTREACH queued (not sent) for " + lead_id,
                       actor="vera", store=store)
    return {"ok": True, "item": item}


def approval_queue(name: str, sprint_id: str, *, store: Path | None = None) -> dict:
    """The human-approval queue: every queued item a human must approve before any send."""
    rec = _load(name, sprint_id, store)
    if rec is None:
        return {"ok": False, "error": "no such sprint"}
    pending = [i for i in rec["items"] if i["status"] == "queued"]
    return {"ok": True, "sprint_id": sprint_id, "goal": rec["goal"],
            "pending_approval": pending, "total_items": len(rec["items"]),
            "send_policy": "every item is human-approved before send; Vera never sends"}


def approve_item(name: str, sprint_id: str, item_id: str, *, approver: str,
                 store: Path | None = None) -> dict:
    """A human approves an item for THEM to send. This does NOT send — it records human authorization."""
    rec = _load(name, sprint_id, store)
    if rec is None:
        return {"ok": False, "error": "no such sprint"}
    if not (approver or "").strip():
        return {"ok": False, "error": "human approver required"}
    for i in rec["items"]:
        if i["item_id"] == item_id:
            i["status"] = "approved"
            i["approval_ref"] = approver
            i["approved_at"] = storage.now()
            _save(name, rec, store)
            storage.emit_truth(name, "sales_sprint", sprint_id,
                               "OUTREACH approved by %s (human sends it)" % approver,
                               actor=approver, store=store)
            return {"ok": True, "item": i,
                    "note": "approved for a human to send; Vera does not send"}
    return {"ok": False, "error": "no such item"}


def mark_sent(name: str, sprint_id: str, item_id: str, *, sent_by: str, store: Path | None = None) -> dict:
    """A human records that THEY sent an approved item. Refuses unapproved items."""
    rec = _load(name, sprint_id, store)
    if rec is None:
        return {"ok": False, "error": "no such sprint"}
    for i in rec["items"]:
        if i["item_id"] == item_id:
            if i["status"] != "approved":
                return {"ok": False, "error": "item not approved — cannot mark sent"}
            i["status"] = "sent_by_human"
            i["sent_by"] = sent_by
            _save(name, rec, store)
            return {"ok": True, "item": i}
    return {"ok": False, "error": "no such item"}
