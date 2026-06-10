"""commercial.readiness — multi-dimensional commercial readiness scoring + verdict.

Scores each asset across the directive's dimensions and assigns a verdict. A prototype can never be
sell_now; a blocked IP/license asset can never proceed; sell_now requires proof + clear ownership.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import ip_license

DIMENSIONS = ("problem_clarity", "buyer_clarity", "proof_strength", "technical_readiness",
              "demo_readiness", "onboarding", "support_burden_inverse", "security_ok",
              "ip_clarity", "pricing_clarity", "differentiation", "speed_to_revenue")
VERDICTS = ("sell_now", "package_first", "validate_first", "internal_only",
            "needs_legal_review", "needs_security_review", "kill")


def audit(name: str, asset_id: str, *, scores: dict, proof_present: bool = False,
          store: Path | None = None) -> dict:
    """scores: dim -> 0..3. Returns the verdict + the recorded audit (gated by IP/license/security)."""
    a = storage.load(name, "commercial_assets", store, default={"assets": []})["assets"]
    rec = next((x for x in a if x["asset_id"] == asset_id), None)
    if rec is None:
        return {"ok": False, "error": "no such asset"}
    total = sum(int(scores.get(d, 0)) for d in DIMENSIONS)
    maxs = len(DIMENSIONS) * 3
    pct = round(100 * total / maxs)
    sellv = ip_license.can_sell(name, asset_id, store=store)
    maturity = rec.get("maturity", "")

    if not sellv["allowed"]:
        verdict = "kill" if any("blocked" in b for b in sellv["blockers"]) else "needs_legal_review"
    elif sellv["legal_review_required"]:
        verdict = "needs_legal_review"
    elif rec.get("security_status") == "needs_review":
        verdict = "needs_security_review"
    elif "prototype" in str(maturity).lower() or "research" in str(maturity).lower():
        verdict = "validate_first"          # a prototype can never be sell_now
    elif rec.get("commercial_status") == "internal_only":
        verdict = "internal_only"
    elif pct >= 75 and proof_present:
        verdict = "sell_now"                # sell_now requires proof + (above) clear ownership
    elif pct >= 50:
        verdict = "package_first"
    else:
        verdict = "validate_first"

    rec["readiness_score"] = pct
    rec["readiness_verdict"] = verdict
    rec["readiness_scores"] = {d: int(scores.get(d, 0)) for d in DIMENSIONS}
    storage.save(name, "commercial_assets", {"assets": a}, store)
    storage.emit_truth(name, "readiness", asset_id, "READINESS %s (%d%%): %s"
                       % (rec["asset_name"], pct, verdict), actor="vera", store=store)
    return {"ok": True, "asset_id": asset_id, "score": pct, "verdict": verdict,
            "ip_license": sellv}
