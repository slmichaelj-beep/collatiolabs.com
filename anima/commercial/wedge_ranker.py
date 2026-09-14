"""commercial.wedge_ranker — rank sellable candidates, recommend the first wedge.

Ranks audited, sellable-cleared assets by the directive's factors and recommends the first wedge
with rationale. Blocked / unknown-ownership / internal-only assets are EXCLUDED. The recommendation
requires founder approval before packaging begins.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import assets as _assets, ip_license

FACTORS = ("buyer_pain", "ability_to_pay", "proof_available", "speed_to_package", "legal_clarity",
           "support_burden_inverse", "pricing_power", "differentiation", "sales_cycle_short",
           "strategic_fit", "first_revenue_30_90d")


def rank(name: str, factor_scores: dict | None = None, *, write: bool = True,
         store: Path | None = None) -> dict:
    """factor_scores: asset_id -> {factor: 0..3}. Candidates must be sellable-cleared + not
    internal_only + verdict in (sell_now, package_first). Returns a ranked report. write=False
    computes the recommendation without touching the report file or the ledger (read-only view)."""
    factor_scores = factor_scores or {}
    inv = _assets.inventory(name, store)
    candidates, excluded = [], []
    for a in inv["assets"]:
        aid = a["asset_id"]
        sellv = ip_license.can_sell(name, aid, store=store)
        verdict = a.get("readiness_verdict")
        if not sellv["allowed"]:
            excluded.append({"asset": a["asset_name"], "why": "; ".join(sellv["blockers"])})
            continue
        if a.get("commercial_status") == "internal_only" or verdict == "internal_only":
            excluded.append({"asset": a["asset_name"], "why": "internal-only"})
            continue
        if verdict not in ("sell_now", "package_first"):
            excluded.append({"asset": a["asset_name"], "why": "readiness verdict %r (not sellable yet)"
                             % (verdict or "unaudited")})
            continue
        fs = factor_scores.get(aid, {})
        score = sum(int(fs.get(f, 0)) for f in FACTORS)
        candidates.append({"asset_id": aid, "asset_name": a["asset_name"], "score": score,
                           "verdict": verdict, "readiness": a.get("readiness_score", 0)})
    candidates.sort(key=lambda c: (-c["score"], -c["readiness"]))
    rec = {
        "wedge_report_id": "wr_" + uuid.uuid4().hex[:12],
        "ranked_candidates": candidates,
        "recommended_first_wedge": candidates[0]["asset_name"] if candidates else None,
        "recommended_asset_id": candidates[0]["asset_id"] if candidates else None,
        "why_this_first": ("highest combined buyer-pain/pay/proof/speed score among sellable-cleared, "
                           "audited assets" if candidates else "no sellable-cleared candidate yet"),
        "why_not_the_others": excluded,
        "blocking_issues": [e for e in excluded if "blocked" in e["why"].lower()
                            or "unknown" in e["why"].lower()],
        "next_10_actions": (["audit + clear IP/license for the top excluded assets",
                             "build the offer package for the recommended wedge (after approval)"]
                            if candidates else
                            ["audit assets", "clear IP/license/ownership", "score readiness"]),
        "approval_required": True,
        "created_at": storage.now(),
    }
    if write:
        REPORTS = Path(__file__).resolve().parent.parent.parent / "reports"
        REPORTS.mkdir(exist_ok=True)
        import json
        (REPORTS / "first_sellable_wedge.json").write_text(json.dumps(rec, indent=1))
        md = ["# First sellable wedge", "", "Recommended: **%s**" % (rec["recommended_first_wedge"] or "none yet"),
              "", "Why this first: " + rec["why_this_first"], "", "## Ranked candidates"]
        md += ["- %s — score %d (%s, readiness %d%%)" % (c["asset_name"], c["score"], c["verdict"],
                                                         c["readiness"]) for c in candidates] or ["(none)"]
        md += ["", "## Excluded"] + ["- %s — %s" % (e["asset"], e["why"]) for e in excluded]
        (REPORTS / "first_sellable_wedge.md").write_text("\n".join(md) + "\n")
        storage.emit_truth(name, "wedge_rank", rec["wedge_report_id"],
                           "WEDGE RANK: first=%s" % (rec["recommended_first_wedge"] or "none"),
                           actor="vera", store=store)
    return rec
