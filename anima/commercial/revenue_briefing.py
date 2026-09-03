"""commercial.revenue_briefing — the board revenue briefing for the commercialization loop.

Ties the whole loop together for the chairman: asset readiness -> wedge -> offer readiness ->
sales pipeline -> approvals needed -> revenue truth. Distinguishes activity / pipeline / closed
revenue (never fakes revenue), shows the governance posture, and names the next action.
"""
from __future__ import annotations

from pathlib import Path

from . import assets as _assets, wedge as _wedge, offer as _offer
from .sales_mastery import pipeline as _pl


def build(name: str, store: Path | None = None) -> dict:
    inv = _assets.inventory(name, store)
    wedges = _wedge.list_wedges(name, store)
    offers = _offer.list_offers(name, store)
    pipe = _pl.briefing(name, store)
    rev = _pl.revenue_truth(name, store)

    # governance posture
    try:
        from anima.observation import emit as _obe
        gov = _obe.governance_snapshot(name, store)
    except Exception:
        gov = {}

    approved_wedges = [w for w in wedges if w["status"] == "approved"]
    ready_offers = [o for o in offers if _offer.audit_readiness(name, o["offer_id"], store=store).get("ready")]

    # next action across the loop (honest, evidence-driven)
    if not inv["assets"]:
        nxt = "inventory your software assets"
    elif inv["needs_audit"]:
        nxt = "audit readiness for: " + ", ".join(inv["needs_audit"][:3])
    elif not approved_wedges:
        nxt = "propose + approve a first sellable wedge from an audited asset"
    elif not offers:
        nxt = "build an offer package for the approved wedge"
    elif not ready_offers:
        nxt = "close the offer gaps (ICP / value prop / proof)"
    elif pipe["closed_revenue"] == 0 and not pipe.get("by_stage"):
        nxt = "start qualified outreach on the ready offer (governed: approval before send)"
    else:
        nxt = "advance the pipeline; review approvals; report revenue truth"

    return {
        "ok": True,
        "loop": {
            "asset_inventory": {"total": len(inv["assets"]), "sellable": inv["sellable"],
                                "needs_audit": inv["needs_audit"]},
            "wedge": {"proposed": len(wedges), "approved": [w["narrow_use_case"] for w in approved_wedges]},
            "offer": {"drafted": len(offers), "ready": [o["asset_name"] for o in ready_offers]},
            "pipeline": {"by_stage": pipe["by_stage"], "pipeline_value": pipe["pipeline_value"],
                         "approvals_needed": pipe["approvals_needed"]},
            "revenue_truth": {"activity": rev["activity"],
                              "pipeline_value_forecast": rev["pipeline_value_forecast"],
                              "closed_revenue": rev["closed_revenue"]},
        },
        "governance": gov,
        "highest_leverage_next_move": nxt,
        "honesty": "pipeline value is a forecast (assumption); only closed_revenue is revenue.",
    }
