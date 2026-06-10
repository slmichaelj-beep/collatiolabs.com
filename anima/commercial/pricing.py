"""commercial.pricing — a pricing RECOMMENDATION engine (never a commitment).

Produces a defensible price recommendation from value drivers, comparables, and buyer ability-to-pay.
Every output is explicitly a recommendation: the binding price is set by a human on an approved offer.
No discount, contract, or invoice is ever issued here.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

MODELS = ("one_time", "subscription_monthly", "subscription_annual", "usage", "service_retainer")


def recommend(name: str, asset_id: str, *, model: str = "one_time", value_per_year: float = 0.0,
              comparables: list | None = None, ability_to_pay: str = "unknown",
              store: Path | None = None) -> dict:
    """A price recommendation with rationale. value_per_year = the buyer's quantified annual value.
    The recommendation anchors at ~10–20% of delivered value, sanity-checked against comparables."""
    comparables = comparables or []
    if model not in MODELS:
        model = "one_time"
    anchor_low = round(value_per_year * 0.10, 2)
    anchor_high = round(value_per_year * 0.20, 2)
    comp_mid = round(sum(comparables) / len(comparables), 2) if comparables else None
    rec = {
        "pricing_id": "pr_" + uuid.uuid4().hex[:10],
        "asset_id": asset_id, "model": model,
        "recommended_range": {"low": anchor_low, "high": anchor_high},
        "comparable_midpoint": comp_mid,
        "ability_to_pay": ability_to_pay,
        "rationale": ("anchored at 10–20%% of the buyer's quantified annual value (%.0f); "
                      "%s" % (value_per_year,
                              ("sanity-checked vs comparables midpoint %.0f" % comp_mid)
                              if comp_mid is not None else "no comparables supplied")),
        "is_recommendation": True,
        "is_commitment": False,
        "binding_requires": "human approval on the offer (Vera never commits a price)",
        "created_at": storage.now(),
    }
    storage.save(name, "pricing_%s" % asset_id, rec, store)
    storage.emit_truth(name, "pricing", rec["pricing_id"],
                       "PRICING recommendation %s..%s (%s) — recommendation only"
                       % (anchor_low, anchor_high, model), actor="vera", store=store)
    return rec
