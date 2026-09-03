"""revenue_swarm.portfolio — swarm portfolio + kill/scale/pivot + budget allocator.

The portfolio tracks many experiments without losing truth (pipeline vs cash separated; dead
experiments shown). The kill/scale/pivot engine enforces evidence: kill on no signal; pivot when
pain exists but offer wrong; scale ONLY with demand + margin + capacity proof; pause when
fulfillment breaks. The budget allocator funds by band, refuses spend without approval, refuses
scale budget without evidence, and blocks doubling down on a loss-maker.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import factory as _f

BUDGET_BANDS = {"organic": 0, "micro": 50, "validation": 250, "serious": 1000, "scale": 5000, "venture": 25000}


def record_results(name: str, experiment_id: str, *, leads: int = 0, replies: int = 0,
                   meetings: int = 0, cash: float = 0.0, store: Path | None = None) -> dict:
    rec = storage.load(name, "swarm_exp_%s" % experiment_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such experiment"}
    rec["results"] = {"leads": leads, "replies": replies, "meetings": meetings, "cash": cash}
    rec["status"] = "complete"
    storage.save(name, "swarm_exp_%s" % experiment_id, rec, store)
    return {"ok": True, "experiment": rec}


def kill_scale_pivot(name: str, experiment_id: str, *, demand_proven: bool = False,
                     margin_proven: bool = False, capacity_proven: bool = False,
                     fulfillment_broken: bool = False, store: Path | None = None) -> dict:
    """Decide kill/scale/pivot/pause. Scale is blocked unless demand AND margin AND capacity are all
    proven."""
    rec = storage.load(name, "swarm_exp_%s" % experiment_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such experiment"}
    r = rec.get("results", {})
    signal = (r.get("replies", 0) > 0 or r.get("meetings", 0) > 0 or r.get("cash", 0) > 0)
    if fulfillment_broken:
        action, why = "pause", "fulfillment broke — pause before more selling"
    elif not signal:
        action, why = "kill", "no signal after the test"
    elif demand_proven and margin_proven and capacity_proven:
        action, why = "scale", "demand + margin + capacity all proven"
    elif signal and not margin_proven:
        action, why = "pivot", "buyer pain exists but margin/offer not proven — pivot/raise price"
    else:
        action, why = "hold", "some signal; need more proof before scaling"
    rec["recommendation"] = {"action": action, "why": why,
                             "scale_blocked_reason": (None if action == "scale" else
                                                      "scale needs demand+margin+capacity proof")}
    rec["status"] = {"kill": "killed", "scale": "scaled"}.get(action, rec["status"])
    storage.save(name, "swarm_exp_%s" % experiment_id, rec, store)
    storage.emit_truth(name, "swarm_exp", experiment_id, "KILL/SCALE: %s" % action, actor="user", store=store)
    return {"ok": True, "recommendation": rec["recommendation"]}


def allocate_budget(name: str, experiment_id: str, *, band: str, approval_ref: str = "",
                    evidence_present: bool = False, margin_positive: bool = True,
                    store: Path | None = None) -> dict:
    """Allocate a budget band. Refused without approval; scale/venture bands need evidence; a
    loss-making experiment cannot get scale budget."""
    if band not in BUDGET_BANDS:
        return {"ok": False, "error": "unknown budget band %r" % band}
    amount = BUDGET_BANDS[band]
    if amount > 0 and not (approval_ref or "").strip():
        return {"ok": False, "error": "spend requires budget approval"}
    if band in ("scale", "venture") and not evidence_present:
        return {"ok": False, "error": "scale/venture budget requires evidence"}
    if band in ("scale", "venture") and not margin_positive:
        return {"ok": False, "error": "cannot scale a loss-making experiment"}
    rec = {"allocation_id": "alloc_" + uuid.uuid4().hex[:8], "experiment_id": experiment_id,
           "band": band, "amount": amount, "approval_ref": approval_ref or None, "approved": True}
    storage.save(name, "swarm_alloc_%s" % experiment_id, rec, store)
    return {"ok": True, "allocation": rec}


def portfolio(name: str, store: Path | None = None) -> dict:
    exps = _f.list_experiments(name, store)
    def cash(e): return e.get("results", {}).get("cash", 0)
    return {
        "ok": True, "experiments": len(exps),
        "by_status": {s: sum(1 for e in exps if e.get("status") == s)
                      for s in ("approval_pending", "approved", "running", "complete", "killed", "scaled")
                      if any(e.get("status") == s for e in exps)},
        "running": [{"hypothesis": e["hypothesis"], "method": e["method"], "budget": e["budget"]}
                    for e in exps if e.get("status") in ("approved", "running")],
        "killed": [e["hypothesis"] for e in exps if e.get("status") == "killed"],
        "scaled": [e["hypothesis"] for e in exps if e.get("status") == "scaled"],
        "pipeline_meetings": sum(e.get("results", {}).get("meetings", 0) for e in exps),
        "cash_collected": round(sum(cash(e) for e in exps), 2),
        "honesty": "experiments are activity; meetings are pipeline; only collected cash is revenue; "
                   "dead experiments are shown, not hidden.",
    }
