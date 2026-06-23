"""company_operator.approvals — the Approval Queue. The board/chair controls important actions.

Vera creates an approval packet; the action cannot execute while pending; the owner
approves/rejects/revises. An approved packet is the gate the action ledger checks before
recording an external action.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from anima.company import storage

STATUS = ("pending", "approved", "rejected", "revised", "expired", "executed")
ACTION_TYPES = ("publish", "send", "spend", "legal", "account", "vendor", "product",
                "product_change", "core_change", "support", "marketing")
_ACTION_SCOPES = {
    "publish": {"publish"},
    "send": {"email", "send_message"},
    "spend": {"spend"},
    "legal": {"legal_prepare"},
    "account": {"account_create"},
    "vendor": {"vendor_contact"},
    "product": {"publish", "file_create", "product_change"},
    "product_change": {"product_change"},
    "core_change": {"core_change"},
    "support": {"support_reply"},
    "marketing": {"email", "send_message", "publish"},
}
_RISK_RANK = {"low": 0, "medium": 1, "med": 1, "high": 2, "critical": 3, "core": 3}


def _all(name, store): return storage.load(name, "approvals", store, default={"approvals": []})["approvals"]
def _save(name, a, store): storage.save(name, "approvals", {"approvals": a}, store)


def create(name: str, title: str, action_type: str, *, summary: str = "",
           requested_authority_level: int = 2, cost: float = 0.0, budget_ref: str = "",
           risk: str = "low", evidence_refs=None, rollback_plan: str = "",
           category: str = "", vendor: str = "", subject: str = "", rollback_ref: str = "",
           expires_at: str = "", store: Path | None = None) -> dict:
    rec = {"approval_id": "apr_" + uuid.uuid4().hex[:12], "title": title[:200],
           "action_type": action_type, "summary": summary[:1000],
           "requested_authority_level": requested_authority_level, "cost": float(cost),
           "budget_ref": budget_ref, "risk": risk, "evidence_refs": evidence_refs or [],
           "rollback_plan": rollback_plan, "category": category, "vendor": vendor,
           "subject": subject, "rollback_ref": rollback_ref, "expires_at": expires_at,
           "status": "pending", "created_at": storage.now(), "decided_at": None, "decided_by": None}
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


def _risk_rank(risk: str) -> int:
    return _RISK_RANK.get(str(risk or "low").lower(), 2)


def _parse_at(value: str):
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _allowed_actions(approval_type: str) -> set[str]:
    t = str(approval_type or "")
    return set(_ACTION_SCOPES.get(t, set())) | {t}


def validate_for_action(name: str, approval_id: str, action_type: str, *, cost: float = 0.0,
                        category: str = "", vendor: str = "", risk: str = "low",
                        subject: str = "", rollback_ref: str = "",
                        store: Path | None = None) -> dict:
    """Return a scoped approval verdict for the exact action envelope.

    An approval packet is not a bearer token. It must be approved, unexpired, single-use, and scoped
    to the action class plus any cost/vendor/category/subject/rollback/risk constraints the packet
    names.
    """
    rec = get(name, approval_id, store)
    if rec is None:
        return {"ok": False, "reason": "no such approval", "approval": None}
    if rec.get("status") != "approved":
        return {"ok": False, "reason": "approval is %s" % rec.get("status"), "approval": rec}

    exp = _parse_at(str(rec.get("expires_at") or ""))
    if exp and exp <= datetime.now(timezone.utc):
        return {"ok": False, "reason": "approval expired", "approval": rec}

    allowed = _allowed_actions(str(rec.get("action_type") or ""))
    if action_type not in allowed:
        return {"ok": False,
                "reason": "approval scoped for %s, not %s" % (sorted(allowed), action_type),
                "approval": rec}

    approved_cost = float(rec.get("cost") or 0.0)
    if float(cost or 0.0) > approved_cost:
        return {"ok": False,
                "reason": "approval cost ceiling $%.2f < action cost $%.2f"
                          % (approved_cost, float(cost or 0.0)),
                "approval": rec}

    for key, actual in (("category", category), ("vendor", vendor), ("subject", subject),
                        ("rollback_ref", rollback_ref)):
        expected = str(rec.get(key) or "")
        if expected and expected != str(actual or ""):
            return {"ok": False, "reason": "approval %s %r does not match action %r"
                    % (key, expected, actual), "approval": rec}

    if _risk_rank(risk) > _risk_rank(str(rec.get("risk") or "low")):
        return {"ok": False, "reason": "approval risk %r below action risk %r"
                % (rec.get("risk"), risk), "approval": rec}

    return {"ok": True, "reason": "approval scoped to action", "approval": rec}


def pending(name: str, store: Path | None = None) -> list:
    return [x for x in _all(name, store) if x["status"] == "pending"]


def mark_executed(name: str, approval_id: str, store: Path | None = None) -> None:
    a = _all(name, store)
    for x in a:
        if x["approval_id"] == approval_id and x["status"] == "approved":
            x["status"] = "executed"
    _save(name, a, store)
