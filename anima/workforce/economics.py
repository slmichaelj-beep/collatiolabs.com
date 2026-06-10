"""workforce.economics — unit economics + demand capture. No opportunity advances without math.

Computes per-unit margin from price, AI/human/tool cost, CAC, support, and rework. A negative-margin
opportunity is blocked; micro-work whose fulfillment cost isn't far below price is blocked; high-
support low-ticket work is blocked. Margins are always labeled estimates. Demand capture names a
buyer + channel + proof needed; outreach is approval-gated and platform-policy-bound.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

SALES_MOTIONS = ("self_serve", "outbound", "inbound", "marketplace", "partnership", "referral",
                 "community", "content")


def unit_economics(name: str, work_gap_id: str, *, price_per_unit: float, ai_cost: float = 0.0,
                   human_review_cost: float = 0.0, tool_api_cost: float = 0.0, cac: float = 0.0,
                   support_cost: float = 0.0, rework_refund_rate: float = 0.0,
                   capacity_limit: int = 0, store: Path | None = None) -> dict:
    """Compute and gate unit economics. Returns refusal if the unit cannot be profitable."""
    fulfill = ai_cost + human_review_cost + tool_api_cost + support_cost
    gross = price_per_unit - fulfill
    net = gross - cac - (price_per_unit * rework_refund_rate)
    gm = round(gross / price_per_unit, 3) if price_per_unit > 0 else -1
    if net <= 0:
        return {"ok": False, "error": "negative net margin — opportunity blocked", "net": round(net, 3)}
    if price_per_unit <= 5 and fulfill > price_per_unit * 0.5:
        return {"ok": False, "error": "micro/small-ticket fulfillment cost too high — blocked"}
    rec = {"unit_economics_id": "ue_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id,
           "price_per_unit": price_per_unit, "ai_cost_per_unit": ai_cost,
           "human_review_cost_per_unit": human_review_cost, "tool_api_cost_per_unit": tool_api_cost,
           "customer_acquisition_cost_estimate": cac, "support_cost_per_unit": support_cost,
           "rework_refund_rate_estimate": rework_refund_rate,
           "gross_margin_estimate": gm, "net_margin_estimate": round(net, 3),
           "break_even_volume": (round(cac / net) if net > 0 and cac > 0 else 0),
           "capacity_limit": capacity_limit,
           "assumptions": ["all costs are estimates pending real delivery data"],
           "margins_are_estimates": True, "confidence": "medium"}
    storage.save(name, "wf_econ_%s" % work_gap_id, rec, store)
    storage.emit_truth(name, "wf_econ", rec["unit_economics_id"],
                       "UNIT ECON %s: GM %.0f%%" % (work_gap_id, gm * 100), actor="vera", store=store)
    return {"ok": True, "unit_economics": rec}


def demand_capture(name: str, work_gap_id: str, *, buyer: str, where_to_find_buyers: list,
                   sales_motion: str, proof_needed: list, channel_policy_ok: bool = True,
                   store: Path | None = None) -> dict:
    """Define the path to buyers. No demand path → no business. Outreach is approval-gated; a
    channel that violates source/platform policy is refused."""
    if not where_to_find_buyers:
        return {"ok": False, "error": "no demand path (no buyers identified) — no business"}
    if not channel_policy_ok:
        return {"ok": False, "error": "channel violates source/platform policy — refused"}
    rec = {"demand_id": "dem_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id, "buyer": buyer,
           "where_to_find_buyers": list(where_to_find_buyers),
           "sales_motion": sales_motion if sales_motion in SALES_MOTIONS else "outbound",
           "proof_needed": list(proof_needed), "ethical_outreach_allowed": True,
           "approval_required": True,
           "approval_note": "any outreach/spend requires human approval; no fake urgency/proof"}
    storage.save(name, "wf_demand_%s" % work_gap_id, rec, store)
    return {"ok": True, "demand": rec}
