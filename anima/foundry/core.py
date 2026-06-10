"""foundry.core — venture + portfolio records, preflight envelope, per-venture isolation.

The Venture Foundry runs a PORTFOLIO of ventures, each isolated, all under the same governance
spine (company_operator: authority + approvals + budget + action ledger + kill switch). A venture's
state lives under its OWN store namespace (foundry/<venture_id>/*) so no venture can read another's
memory, budget, accounts, or customer data. No venture work happens without a portfolio preflight.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

VENTURE_STATUS = ("idea", "validation", "experiment", "approved_launch", "operating", "paused",
                  "killed", "pivoted", "scaled", "closed")
PORTFOLIO_RISK = ("low", "medium", "high")


def now() -> str:
    return storage.now()


# ---- preflight ------------------------------------------------------------------------------
PREFLIGHT_REQUIRED = ("total_capital", "max_loss", "allowed_jurisdictions", "authority_level",
                      "max_active_ventures")


def set_preflight(name: str, *, total_capital: float, max_loss: float, allowed_jurisdictions,
                  authority_level: int = 0, prohibited_industries=None, max_active_ventures: int = 3,
                  spend_requires_approval_above: float = 0.0, store: Path | None = None) -> dict:
    rec = {"total_capital": float(total_capital), "max_loss": float(max_loss),
           "allowed_jurisdictions": list(allowed_jurisdictions or []),
           "prohibited_industries": list(prohibited_industries or []),
           "authority_level": int(authority_level),
           "max_active_ventures": int(max_active_ventures),
           "spend_requires_approval_above": float(spend_requires_approval_above),
           "set_at": now()}
    storage.save(name, "foundry_preflight", rec, store)
    storage.emit_truth(name, "foundry", "preflight", "FOUNDRY preflight set: $%.0f cap, %d ventures"
                       % (total_capital, max_active_ventures), actor="user", risk="high", store=store)
    return {"ok": True, "preflight": rec}


def preflight(name: str, store: Path | None = None) -> dict | None:
    return storage.load(name, "foundry_preflight", store, default=None)


def can_operate(name: str, store: Path | None = None) -> dict:
    """The Foundry cannot do venture work without a preflight envelope."""
    pf = preflight(name, store)
    if not pf:
        return {"ok": False, "reason": "no Foundry preflight — set the operating envelope first "
                                       "(capital, loss tolerance, jurisdictions, authority, venture cap)"}
    if not all(pf.get(k) not in (None, "", []) for k in ("total_capital", "allowed_jurisdictions",
                                                          "max_active_ventures")):
        return {"ok": False, "reason": "preflight incomplete (capital/jurisdictions/venture-cap required)"}
    return {"ok": True}


# ---- ventures + portfolio -------------------------------------------------------------------
def _ventures(name, store): return storage.load(name, "foundry_ventures", store, default={"ventures": []})["ventures"]
def _save_ventures(name, v, store): storage.save(name, "foundry_ventures", {"ventures": v}, store)


def create_venture(name: str, vname: str, idea_ref: str, *, jurisdiction: str = "",
                   target_customer: str = "", revenue_goal: float = 0.0,
                   risk_tolerance: str = "medium", store: Path | None = None) -> dict:
    op = can_operate(name, store)
    if not op["ok"]:
        return {"ok": False, "error": op["reason"]}
    pf = preflight(name, store)
    if jurisdiction and pf["allowed_jurisdictions"] and jurisdiction not in pf["allowed_jurisdictions"]:
        return {"ok": False, "error": "jurisdiction %r not in the allowed list" % jurisdiction}
    active = [v for v in _ventures(name, store)
              if v["status"] in ("idea", "validation", "experiment", "approved_launch", "operating")]
    if len(active) >= pf["max_active_ventures"]:
        return {"ok": False, "error": "active-venture cap (%d) reached — kill/close one first"
                                      % pf["max_active_ventures"]}
    rec = {"venture_id": "vent_" + uuid.uuid4().hex[:12], "name": vname, "status": "idea",
           "owner": "user", "operator": "vera", "idea_ref": idea_ref, "jurisdiction": jurisdiction,
           "target_customer": target_customer, "revenue_goal": float(revenue_goal),
           "risk_tolerance": risk_tolerance, "current_phase": "idea",
           "budget": 0.0, "spent": 0.0,
           "kill_criteria": [], "pivot_criteria": [], "scale_criteria": [],
           "truth_refs": [], "experiment_refs": [], "created_at": now(), "last_reviewed_at": now()}
    vs = _ventures(name, store); vs.append(rec); _save_ventures(name, vs, store)
    ev = storage.emit_truth(name, "venture", rec["venture_id"], "VENTURE created: " + vname,
                            actor="user", store=store)
    rec["truth_refs"].append(ev)
    _save_ventures(name, vs, store)
    return {"ok": True, "venture": rec}


def get_venture(name, venture_id, store): return next(
    (v for v in _ventures(name, store) if v["venture_id"] == venture_id), None)


def update_venture(name, venture_id, patch, store: Path | None = None) -> dict | None:
    vs = _ventures(name, store)
    for v in vs:
        if v["venture_id"] == venture_id:
            v.update(patch)
            v["last_reviewed_at"] = now()
            _save_ventures(name, vs, store)
            return v
    return None


# ---- isolation --------------------------------------------------------------------------------
def venture_store_key(venture_id: str, kind: str) -> str:
    """The isolated store key for a venture's private data — namespaced by venture_id so no two
    ventures can ever share a memory/budget/account/customer file."""
    return "foundry_%s_%s" % (venture_id, kind)


def write_venture_data(name, venture_id, kind, data, store: Path | None = None) -> None:
    storage.save(name, venture_store_key(venture_id, kind), data, store)


def read_venture_data(name, venture_id, kind, store: Path | None = None, default=None):
    return storage.load(name, venture_store_key(venture_id, kind), store, default=default or {})


def cross_venture_read_blocked(reader_venture: str, target_venture: str) -> bool:
    """A venture may only read its OWN data. Any read of another venture's namespace is blocked
    unless an explicit, approved import is performed (a separate, audited action)."""
    return reader_venture != target_venture


def portfolio(name: str, store: Path | None = None) -> dict:
    pf = preflight(name, store) or {}
    vs = _ventures(name, store)
    allocated = sum(v.get("budget", 0) for v in vs)
    return {
        "ok": True,
        "total_budget": pf.get("total_capital", 0),
        "allocated_budget": allocated,
        "unallocated_budget": max(0.0, pf.get("total_capital", 0) - allocated),
        "ventures": vs,
        "by_status": {s: [v["venture_id"] for v in vs if v["status"] == s] for s in VENTURE_STATUS
                      if any(v["status"] == s for v in vs)},
        "active_count": len([v for v in vs if v["status"] in
                             ("idea", "validation", "experiment", "approved_launch", "operating")]),
        "max_active": pf.get("max_active_ventures"),
    }
