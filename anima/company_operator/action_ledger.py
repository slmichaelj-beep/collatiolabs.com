"""company_operator.action_ledger — every external action is gated and recorded.

This is the single choke point for company external actions. perform() checks, in order:
  1. kill switch not engaged
  2. authority level permits the action class (and it's not human-only)
  3. if the action requires approval, an APPROVED approval_ref exists
  4. if the action spends, the budget ledger allows it (and records the spend)
Only then is the action recorded as performed. Any gate failing => BLOCKED + recorded as blocked.

NOTE: in v1 there are NO real external integrations wired. perform() records the governed
*intent/result*; the actual side effect (sending an email, creating an account, moving money) is
deliberately not implemented — those stay human-executed. This ledger proves the governance holds.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import approvals, authority, budget, kill_switch

ACTION_TYPES = ("email", "publish", "spend", "account_create", "vendor_contact", "legal_prepare",
                "support_reply", "file_create", "send_message")
# which ledger action maps to which authority action_type
_AUTH_MAP = {"email": "send_message", "send_message": "send_message", "publish": "publish",
             "spend": "spend", "account_create": "create_account", "vendor_contact": "vendor_contact",
             "legal_prepare": "draft", "support_reply": "support_reply", "file_create": "create_document"}
# actions that require an approval before they can be performed (L2+ gating)
_NEEDS_APPROVAL = {"email", "publish", "spend", "account_create", "vendor_contact", "send_message"}


def _all(name, store): return storage.load(name, "action_ledger", store, default={"actions": []})["actions"]
def _save(name, a, store): storage.save(name, "action_ledger", {"actions": a}, store)


def perform(name: str, action_type: str, description: str, *, approval_ref: str = "",
            cost: float = 0.0, category: str = "", vendor: str = "", risk: str = "low",
            subject: str = "", performed_by: str = "vera", store: Path | None = None) -> dict:
    """Attempt a governed external action. Returns {ok, action} on success, {ok:False, blocked, reason}
    otherwise. Always writes an Action Ledger record (success OR blocked)."""
    aid = "act_" + uuid.uuid4().hex[:12]
    auth_type = _AUTH_MAP.get(action_type, "regulated")

    def _record(result, reason, authority_ok, approval_ok, budget_ok):
        rec = {"action_id": aid, "action_type": action_type, "description": description[:1000],
               "performed_by": performed_by, "auth_type": auth_type,
               "authority_ref": "L%d" % authority.current_level(name, store),
               "approval_ref": approval_ref, "cost": float(cost), "category": category,
               "vendor": vendor, "subject": subject, "risk": risk, "result": result, "reason": reason,
               "rollback_ref": None, "created_at": storage.now(),
               "gates": {"authority": authority_ok, "approval": approval_ok, "budget": budget_ok}}
        a = _all(name, store); a.append(rec); _save(name, a, store)
        storage.emit_truth(name, "action", aid, "ACTION[%s] %s: %s" % (action_type, result, description[:120]),
                           actor=performed_by, risk=risk,
                           active_status="active" if result == "success" else "retracted", store=store)
        return rec

    # 1 + 2. kill switch + authority
    perm = authority.permits(name, auth_type, store=store)
    if not perm["permitted"]:
        return {"ok": False, "blocked": True, "reason": perm["reason"],
                "action": _record("blocked", perm["reason"], False, None, None)}

    # 3. approval
    approval_ok = None
    if action_type in _NEEDS_APPROVAL:
        if not approval_ref:
            r = "requires an APPROVED approval packet (got none)"
            return {"ok": False, "blocked": True, "reason": r,
                    "action": _record("blocked", r, True, False, None)}
        verdict = approvals.validate_for_action(
            name, approval_ref, action_type, cost=cost, category=category, vendor=vendor,
            risk=risk, subject=subject, store=store,
        )
        if not verdict["ok"]:
            r = "approval rejected: " + verdict["reason"]
            return {"ok": False, "blocked": True, "reason": r,
                    "action": _record("blocked", r, True, False, None)}
        approval_ok = True

    # 4. budget (for spend)
    budget_ok = None
    if action_type == "spend":
        sp = budget.record_spend(name, cost, category=category, vendor=vendor,
                                 description=description, approval_ref=approval_ref, store=store)
        if not sp["ok"]:
            return {"ok": False, "blocked": True, "reason": sp["error"],
                    "action": _record("blocked", sp["error"], True, approval_ok, False)}
        budget_ok = True

    if approval_ref:
        approvals.mark_executed(name, approval_ref, store)
    return {"ok": True, "action": _record("success", "all gates passed", True, approval_ok, budget_ok)}


def history(name: str, store: Path | None = None) -> list:
    return _all(name, store)
