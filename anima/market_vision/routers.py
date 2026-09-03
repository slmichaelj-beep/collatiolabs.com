"""market_vision.routers — route scored opportunities into Commercialization or Venture Foundry.

An opportunity that maps to an EXISTING, IP-clear asset routes into the commercialization engine
(readiness audit / offer / sales). An opportunity needing a NEW venture routes into the Venture
Foundry — but only as a governed proposal: approval + budget + a validation experiment are required,
and no venture is launched here. A blocked/unknown-ownership asset is never routed.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from anima.commercial import ip_license as _ip
from . import thesis as _thesis, validation as _val

COMMERCIAL_STEPS = ("readiness_audit", "offer_design", "proof_builder", "sales_sprint")


def route_to_commercial(name: str, opportunity_id: str, asset_id: str, *,
                        commercial_next_step: str = "readiness_audit", reason: str = "",
                        store: Path | None = None) -> dict:
    """Route an asset-fit opportunity into the commercialization engine. Refused if the asset's
    IP/license gate is not clear."""
    opp = _thesis.get(name, opportunity_id, store)
    if opp is None:
        return {"ok": False, "error": "no such opportunity"}
    gate = _ip.can_sell(name, asset_id, store=store)
    if not gate["allowed"]:
        return {"ok": False, "error": "asset not IP/license clear — not routed",
                "blockers": gate["blockers"]}
    step = commercial_next_step if commercial_next_step in COMMERCIAL_STEPS else "readiness_audit"
    rec = {"route_id": "rtc_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id,
           "asset_id": asset_id, "route": "commercialize_existing_asset",
           "commercial_next_step": step, "reason": reason, "evidence_refs": opp.get("evidence_refs", [])}
    storage.save(name, "mv_route_commercial_%s" % opportunity_id, rec, store)
    storage.emit_truth(name, "mv_route", rec["route_id"],
                       "ROUTE->commercial: %s (%s)" % (opportunity_id, step), actor="user", store=store)
    return {"ok": True, "route": rec}


def route_to_venture(name: str, opportunity_id: str, *, approval_ref: str = "", budget: float | None = None,
                     validation_present: bool | None = None, store: Path | None = None) -> dict:
    """Route a new-venture opportunity into the Foundry as a governed proposal. Refused without
    approval + a budget + a validation experiment. NEVER launches a venture here."""
    opp = _thesis.get(name, opportunity_id, store)
    if opp is None:
        return {"ok": False, "error": "no such opportunity"}
    if validation_present is None:
        validation_present = _val.get(name, opportunity_id, store) is not None
    if not validation_present:
        return {"ok": False, "error": "no validation experiment — a venture route needs one first"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "venture route requires human approval — refused"}
    if budget is None:
        return {"ok": False, "error": "venture route requires a budget envelope — refused"}
    rec = {"route_id": "rtv_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id,
           "route": "launch_venture_proposal", "approval_ref": approval_ref, "budget": float(budget),
           "status": "proposed_to_foundry", "launched": False,
           "note": "proposal only — no venture launched; Foundry preflight + approval still apply",
           "evidence_refs": opp.get("evidence_refs", [])}
    storage.save(name, "mv_route_venture_%s" % opportunity_id, rec, store)
    storage.emit_truth(name, "mv_route", rec["route_id"],
                       "ROUTE->foundry proposal: %s (approved by %s)" % (opportunity_id, approval_ref),
                       actor="user", store=store)
    return {"ok": True, "route": rec}
