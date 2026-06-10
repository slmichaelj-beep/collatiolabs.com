"""company_operator.approvals — the Approval Queue. The board/chair controls important actions.

Vera creates an approval packet; the action cannot execute while pending; the owner
approves/rejects/revises. An approved packet is the gate the action ledger checks before
recording an external action.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

STATUS = ("pending", "approved", "rejected", "revised", "expired", "executed")
ACTION_TYPES = ("publish", "send", "spend", "legal", "account", "vendor", "product", "support",
                "marketing")


def _all(name, store): return storage.load(name, "approvals", store, default={"approvals": []})["approvals"]
def _save(name, a, store): storage.save(name, "approvals", {"approvals": a}, store)


def create(name: str, title: str, action_type: str, *, summary: str = "",
           requested_authority_level: int = 2, cost: float = 0.0, budget_ref: str = "",
           risk: str = "low", evidence_refs=None, rollback_plan: str = "",
           store: Path | None = None) -> dict:
    rec = {"approval_id": "apr_" + uuid.uuid4().hex[:12], "title": title[:200],
           "action_type": action_type, "summary": summary[:1000],
           "requested_authority_level": requested_authority_level, "cost": float(cost),
           "budget_ref": budget_ref, "risk": risk, "evidence_refs": evidence_refs or [],
           "rollback_plan": rollback_plan, "status": "pending", "created_at": storage.now(),
           "decided_at": None, "decided_by": None}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    storage.emit_truth(name, "approval", rec["approval_id"], "APPROVAL REQUESTED[%s]: %s"
                       % (action_type, title[:140]), actor="vera",
                       risk=risk, store=store)
    return {"ok": True, "approval": rec}


def get(name, approval_id, store): return next((x for x in _all(name, store)
                                                if x["approval_id"] == approval_id), None)


def decide(name: str, approval_id: str, decision: str, *, by: str = "owner",
           store: Path | None = None) -> dict:
    if decision not in ("approved", "rejected", "revised"):
        return {"ok": False, "error": "decision must be approved/rejected/revised"}
    a = _all(name, store)
    rec = next((x for x in a if x["approval_id"] == approval_id), None)
    if rec is None:
        return {"ok": False, "error": "no such approval"}
    if rec["status"] != "pending":
        return {"ok": False, "error": "approval is %s" % rec["status"]}
    rec["status"] = decision
    rec["decided_at"] = storage.now()
    rec["decided_by"] = by
    _save(name, a, store)
    storage.emit_truth(name, "approval", approval_id, "APPROVAL %s by %s" % (decision.upper(), by),
                       actor="user", store=store)
    return {"ok": True, "approval": rec}


def is_approved(name: str, approval_id: str, store: Path | None = None) -> bool:
    rec = get(name, approval_id, store)
    return bool(rec) and rec["status"] == "approved"


def pending(name: str, store: Path | None = None) -> list:
    return [x for x in _all(name, store) if x["status"] == "pending"]


def mark_executed(name: str, approval_id: str, store: Path | None = None) -> None:
    a = _all(name, store)
    for x in a:
        if x["approval_id"] == approval_id and x["status"] == "approved":
            x["status"] = "executed"
    _save(name, a, store)
