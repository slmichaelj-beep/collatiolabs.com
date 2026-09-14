"""market_vision.briefing — Vera proactively briefs Lamar on what she sees.

Summarizes the scan: source classes scanned, signal count, strongest patterns/gaps, privacy-first
angles, asset-monetization matches, validation recommendations, and the approvals Vera needs. No
unsupported claims: every highlighted opportunity carries its evidence refs and its honest next
step. Activity (signals/theses) is never presented as revenue.
"""
from __future__ import annotations

from pathlib import Path

from . import source_registry as _src, signals as _sig, thesis as _thesis, portfolio as _pf, \
    asset_monetization as _mon, validation as _val


def build(name: str, store: Path | None = None) -> dict:
    inv = _src.inventory(name, store)
    sigs = _sig.list_signals(name, store=store)
    opps = _thesis.list_opportunities(name, store)
    pf = _pf.portfolio(name, store)
    monetization = _mon.list_maps(name, store)

    scored = [o for o in opps if o.get("score")]
    scored.sort(key=lambda o: o["score"]["total_score"], reverse=True)
    strongest = scored[0] if scored else None

    validations = []
    for o in opps:
        ex = _val.get(name, o["opportunity_id"], store)
        if ex and ex.get("status") == "recommended":
            validations.append({"title": o["title"], "method": ex["method"], "budget": ex["budget"],
                                "approval": ex["approval_note"]})

    # honest next move across the funnel
    if not inv["sources"]:
        nxt = "register approved sources"
    elif not sigs:
        nxt = "extract signals from approved sources"
    elif not opps:
        nxt = "cluster signals and generate opportunity theses"
    elif not scored:
        nxt = "score the open theses"
    elif validations:
        nxt = "approve a validation experiment for the strongest opportunity"
    else:
        nxt = "recommend the cheapest validation for the top opportunity"

    return {
        "ok": True,
        "scan": {"source_classes_scanned": sorted({s["source_type"] for s in inv["sources"]}),
                 "sources_total": len(inv["sources"]), "sources_approved": len(inv["approved"]),
                 "signals_found": len(sigs)},
        "patterns_and_gaps": {"opportunities": len(opps), "scored": len(scored)},
        "strongest_opportunity": ({"title": strongest["title"],
                                   "one_line": strongest["one_line_thesis"],
                                   "score": strongest["score"]["total_score"],
                                   "recommendation": strongest["score"]["recommendation"],
                                   "evidence_refs": strongest.get("evidence_refs", [])}
                                  if strongest else None),
        "privacy_first_opportunities": [o["title"] for o in opps if o.get("privacy_first_angle")],
        "asset_monetization_matches": [{"asset": m["asset_name"], "best_path": m["best_path"]}
                                       for m in monetization],
        "validation_recommendations": validations,
        "watchlist": pf["watchlist"], "kill_list": pf["kill_list"],
        "approvals_needed": [v["title"] for v in validations],
        "highest_leverage_next_move": nxt,
        "honesty": "signals and theses are activity, not revenue; nothing is built or sold without "
                   "validation + approval.",
    }
