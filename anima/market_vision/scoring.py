"""market_vision.scoring — rank opportunities ruthlessly and honestly.

Scores an opportunity across many dimensions and emits a recommendation. Hard rules: a high market
size cannot automatically override a high legal/regulatory risk; high pain cannot override
impossible distribution; low confidence CAPS the total score (you cannot score high on weak
evidence). Asset fit boosts speed-to-revenue.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import thesis as _thesis

DIMENSIONS = ("pain_intensity", "market_size", "willingness_to_pay", "incumbent_weakness",
              "privacy_angle", "pricing_arbitrage", "asset_fit", "margin_potential",
              "speed_to_validation", "speed_to_first_revenue", "defensibility", "ethical_advantage")
RISK_DIMS = ("build_difficulty", "distribution_difficulty", "legal_regulatory_risk",
             "support_burden", "capital_requirement", "operator_complexity")
_CONF_CAP = {"low": 40, "medium": 70, "high": 100}


def score(name: str, opportunity_id: str, *, scores: dict, risks: dict, confidence: str = "low",
          store: Path | None = None) -> dict:
    """scores: dim->0..3 (higher=better). risks: risk_dim->0..3 (higher=worse). Returns total + rec."""
    opp = _thesis.get(name, opportunity_id, store)
    if opp is None:
        return {"ok": False, "error": "no such opportunity"}
    pos = sum(min(3, max(0, int(scores.get(d, 0)))) for d in DIMENSIONS)
    pos_pct = round(100 * pos / (len(DIMENSIONS) * 3))
    risk_raw = sum(min(3, max(0, int(risks.get(d, 0)))) for d in RISK_DIMS)
    risk_pct = round(100 * risk_raw / (len(RISK_DIMS) * 3))
    # legal/regulatory risk and distribution difficulty are hard ceilings
    legal = int(risks.get("legal_regulatory_risk", 0))
    dist = int(risks.get("distribution_difficulty", 0))
    total = max(0, pos_pct - round(risk_pct * 0.6))
    cap = _CONF_CAP.get(confidence, 40)
    capped = min(total, cap)

    if legal >= 3:
        rec = "research"      # high legal risk -> never auto-advance past research regardless of size
        why = "high legal/regulatory risk caps this to research until professional review"
    elif dist >= 3 and int(scores.get("pain_intensity", 0)) >= 2:
        rec = "validate"
        why = "strong pain but very hard distribution — validate the channel before anything"
    elif capped >= 70 and confidence == "high":
        rec = "commercialize_asset" if int(scores.get("asset_fit", 0)) >= 2 else "validate"
        why = "high score + high confidence" + (" + asset fit" if rec == "commercialize_asset" else "")
    elif capped >= 50:
        rec = "validate"; why = "promising — earn the next dollar of evidence cheaply"
    elif capped >= 30:
        rec = "watch"; why = "weak/early — watch for stronger signals"
    else:
        rec = "ignore"; why = "low score / low confidence — ignore for now"

    out = {"opportunity_id": opportunity_id, "total_score": capped, "raw_positive": pos_pct,
           "risk_pct": risk_pct, "confidence": confidence, "confidence_cap": cap,
           "recommendation": rec, "why": why,
           "evidence_refs": opp.get("evidence_refs", [])}
    opp["score"] = out; opp["status"] = "scored"; opp["recommendation"] = rec
    _thesis.save(name, opp, store)
    storage.emit_truth(name, "mv_score", opportunity_id, "SCORE %d (%s) -> %s"
                       % (capped, confidence, rec), actor="vera", store=store)
    return {"ok": True, "score": out}
