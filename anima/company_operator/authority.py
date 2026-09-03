"""company_operator.authority — the Authority Ladder. Governed autonomy, not uncontrolled.

Six levels, default L0 (think-only). An external action is permitted only if the CURRENT authority
level allows that action class AND (for L2+) an approval exists AND (for spend) budget covers it.
The default is the safe one: with no explicit grant, Vera can think/plan/draft and nothing else.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage

# level -> the action classes UNLOCKED at that level (cumulative)
LEVELS = {
    0: {"name": "think_only", "unlocks": set()},          # analyze/plan/draft/recommend only
    1: {"name": "prepare", "unlocks": {"prepare"}},        # build artifacts; nothing leaves Vera
    2: {"name": "queue_for_approval", "unlocks": {"prepare", "queue"}},
    3: {"name": "bounded_execution", "unlocks": {"prepare", "queue", "execute_low_risk"}},
    4: {"name": "budgeted_autonomy", "unlocks": {"prepare", "queue", "execute_low_risk", "spend"}},
    5: {"name": "regulated", "unlocks": {"prepare", "queue", "execute_low_risk", "spend",
                                         "regulated"}},
}

# action class required by each external action type
ACTION_CLASS = {
    "think": None, "plan": None, "draft": None, "prepare": "prepare",
    "queue_approval": "queue",
    "publish": "execute_low_risk", "send_message": "execute_low_risk",
    "support_reply": "execute_low_risk", "create_document": "execute_low_risk",
    "create_account": "regulated", "vendor_contact": "execute_low_risk",
    "spend": "spend",
    "bank_transfer": "regulated", "tax_filing": "regulated", "patent_filing": "regulated",
    "sign_contract": "regulated", "payroll": "regulated", "legal_representation": "regulated",
}

# action types that ALWAYS require explicit human action regardless of level (never Vera-executed)
HUMAN_ONLY = {"bank_transfer", "tax_filing", "patent_filing", "sign_contract", "payroll",
              "legal_representation", "create_account"}


def current_level(name: str, store: Path | None = None) -> int:
    return int(storage.load(name, "authority", store, default={"level": 0}).get("level", 0))


def set_level(name: str, level: int, *, by: str = "founder", reason: str = "",
              store: Path | None = None) -> dict:
    if level not in LEVELS:
        return {"ok": False, "error": "invalid authority level %r" % level}
    prev = current_level(name, store)
    rec = {"level": level, "level_name": LEVELS[level]["name"], "set_by": by, "reason": reason,
           "at": storage.now()}
    log = storage.load(name, "authority", store, default={"level": 0, "history": []})
    log["level"] = level
    log["level_name"] = LEVELS[level]["name"]
    log.setdefault("history", []).append({**rec, "from": prev})
    storage.save(name, "authority", log, store)
    storage.emit_truth(name, "authority", "level", "AUTHORITY level %d->%d (%s) by %s"
                       % (prev, level, LEVELS[level]["name"], by), actor="user",
                       risk="high", store=store)
    return {"ok": True, "level": level, "from": prev}


def permits(name: str, action_type: str, *, store: Path | None = None,
            killed: bool | None = None) -> dict:
    """Does the current authority level permit this action TYPE? (Approval + budget are checked
    separately by the approval/budget ledgers — this is the authority gate only.)"""
    from . import kill_switch
    if killed is None:
        killed = kill_switch.is_engaged(name, store)
    if killed:
        return {"permitted": False, "reason": "KILL SWITCH engaged — all external actions paused"}
    cls = ACTION_CLASS.get(action_type, "regulated")  # unknown action -> treat as regulated (safe)
    if cls is None:
        return {"permitted": True, "reason": "think/plan/draft is always permitted", "class": None}
    lvl = current_level(name, store)
    unlocked = LEVELS[lvl]["unlocks"]
    if cls not in unlocked:
        return {"permitted": False, "class": cls,
                "reason": "authority level %d (%s) does not unlock %r — needs a higher level"
                          % (lvl, LEVELS[lvl]["name"], cls)}
    if action_type in HUMAN_ONLY:
        return {"permitted": False, "class": cls, "human_only": True,
                "reason": "%s is HUMAN-ONLY — Vera can prepare + queue it, never execute it"
                          % action_type}
    return {"permitted": True, "class": cls, "level": lvl}
