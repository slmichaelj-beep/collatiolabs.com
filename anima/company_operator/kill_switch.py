"""company_operator.kill_switch — the owner can stop Vera's external actions instantly.

When engaged, every external action is blocked (authority.permits returns False), spending is
blocked, publishing/messaging/account creation blocked. Queued approvals are preserved. Restart
requires an explicit disengage (an approval-equivalent action by the owner).
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage

SCOPES = ("all", "spending", "publishing", "messaging", "account_creation", "agent_execution")


def state(name: str, store: Path | None = None) -> dict:
    return storage.load(name, "kill_switch", store,
                        default={"engaged": False, "scopes": [], "history": []})


def is_engaged(name: str, store: Path | None = None, scope: str = "all") -> bool:
    s = state(name, store)
    if not s.get("engaged"):
        return False
    sc = s.get("scopes") or ["all"]
    return "all" in sc or scope in sc


def engage(name: str, *, scopes=None, by: str = "owner", reason: str = "",
           store: Path | None = None) -> dict:
    s = state(name, store)
    s["engaged"] = True
    s["scopes"] = [x for x in (scopes or ["all"]) if x in SCOPES] or ["all"]
    s.setdefault("history", []).append({"action": "engage", "scopes": s["scopes"], "by": by,
                                        "reason": reason, "at": storage.now()})
    storage.save(name, "kill_switch", s, store)
    storage.emit_truth(name, "kill_switch", "engage", "KILL SWITCH engaged (%s) by %s"
                       % (",".join(s["scopes"]), by), actor="user", risk="high", store=store)
    return {"ok": True, "engaged": True, "scopes": s["scopes"]}


def disengage(name: str, *, by: str = "owner", confirm: bool = False, reason: str = "",
              store: Path | None = None) -> dict:
    if not confirm:
        return {"ok": False, "error": "disengaging the kill switch requires explicit confirm=True"}
    s = state(name, store)
    s["engaged"] = False
    s["scopes"] = []
    s.setdefault("history", []).append({"action": "disengage", "by": by, "reason": reason,
                                        "at": storage.now()})
    storage.save(name, "kill_switch", s, store)
    storage.emit_truth(name, "kill_switch", "disengage", "KILL SWITCH disengaged by %s" % by,
                       actor="user", risk="high", store=store)
    return {"ok": True, "engaged": False}
