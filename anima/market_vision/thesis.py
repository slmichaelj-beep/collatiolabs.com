"""market_vision.thesis — a board-reviewable opportunity thesis.

A thesis must cite evidence, list assumptions, and list risks. It cannot recommend `build_mvp` or
`launch_venture` unless a validation plan exists OR the underlying asset is already packaged/proven
(via the commercialization readiness verdict). No build-from-vibes.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

NEXT_STEPS = ("ignore", "watch", "research", "validate", "commercialize_asset", "build_mvp",
              "launch_venture")
_BUILD_STEPS = ("build_mvp", "launch_venture")


def generate(name: str, *, title, one_line_thesis, customer, pain, product_gap, proposed_product,
             business_model, evidence_refs: list, assumptions: list, risks: list,
             validation_plan: str = "", current_alternatives: list | None = None,
             privacy_first_angle: str = "", free_core_angle: str = "", paid_layer: list | None = None,
             why_lamar_can_win: str = "", recommended_next_step: str = "research",
             asset_proven: bool = False, store: Path | None = None) -> dict:
    """Generate a thesis. Refused without evidence, assumptions, and risks. A build recommendation is
    downgraded to `validate` unless there's a validation plan or the asset is already proven."""
    if not evidence_refs:
        return {"ok": False, "error": "a thesis must cite evidence — refused"}
    if not assumptions:
        return {"ok": False, "error": "a thesis must list assumptions — refused"}
    if not risks:
        return {"ok": False, "error": "a thesis must list risks — refused"}
    step = recommended_next_step if recommended_next_step in NEXT_STEPS else "research"
    downgraded = False
    if step in _BUILD_STEPS and not (validation_plan.strip() or asset_proven):
        step = "validate"; downgraded = True
    rec = {"opportunity_id": "opp_" + uuid.uuid4().hex[:10], "title": title,
           "one_line_thesis": one_line_thesis, "customer": customer, "pain": pain,
           "current_alternatives": list(current_alternatives or []), "product_gap": product_gap,
           "proposed_product": proposed_product, "business_model": business_model,
           "privacy_first_angle": privacy_first_angle, "free_core_angle": free_core_angle,
           "paid_layer": list(paid_layer or []), "why_lamar_can_win": why_lamar_can_win,
           "evidence_refs": list(evidence_refs), "assumptions": list(assumptions), "risks": list(risks),
           "validation_plan": validation_plan, "recommended_next_step": step,
           "build_downgraded_pending_validation": downgraded, "status": "thesis",
           "created_at": storage.now()}
    storage.save(name, "mv_opportunity_%s" % rec["opportunity_id"], rec, store)
    idx = storage.load(name, "mv_opportunity_index", store, default={"ids": []})
    idx["ids"].append(rec["opportunity_id"]); storage.save(name, "mv_opportunity_index", idx, store)
    storage.emit_truth(name, "mv_opportunity", rec["opportunity_id"],
                       "THESIS: %s (next=%s)" % (title, step), actor="vera", store=store)
    return {"ok": True, "thesis": rec}


def get(name, opportunity_id, store=None):
    return storage.load(name, "mv_opportunity_%s" % opportunity_id, store, default=None)


def save(name, rec, store=None):
    storage.save(name, "mv_opportunity_%s" % rec["opportunity_id"], rec, store)


def list_opportunities(name, store=None) -> list:
    # opportunities are stored per-id; we keep an index in mv_opportunity_index
    idx = storage.load(name, "mv_opportunity_index", store, default={"ids": []})["ids"]
    out = [storage.load(name, "mv_opportunity_%s" % i, store, default=None) for i in idx]
    return [o for o in out if o]
