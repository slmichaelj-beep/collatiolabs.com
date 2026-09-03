"""market_vision.product_gap — turn signals/clusters into specific product gaps + patterns.

A product gap is a specific, evidence-backed "this is missing for this buyer." It must draw on
multiple signal classes, name a customer segment, propose a solution, and cite evidence; its
confidence reflects evidence strength. The pattern clusterer and cross-industry analogy engine
connect repeated structures across markets — but an analogy is a research lead, never a build
decision.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

GAP_TYPES = ("lightweight_version", "privacy_first", "free_core", "vertical_workflow",
             "better_onboarding", "local_first", "open_source_plus_polish", "automation_layer",
             "trust_certification", "support_service_wrapper", "developer_tool",
             "internal_tool_commercialized")


def detect(name: str, *, gap_name: str, market: str, customer_segment: str, proposed_solution: str,
           pain_cluster_refs: list | None = None, competitor_refs: list | None = None,
           privacy_gap_refs: list | None = None, pricing_gap_refs: list | None = None,
           why_now: str = "", why_lamar_can_win: str = "", store: Path | None = None) -> dict:
    """A product gap. Refused unless it draws on >=2 evidence classes and names a customer segment +
    proposed solution. Confidence scales with how many evidence classes back it."""
    classes = [r for r in (pain_cluster_refs, competitor_refs, privacy_gap_refs, pricing_gap_refs) if r]
    n_classes = len(classes)
    if n_classes < 2:
        return {"ok": False, "error": "a product gap needs >=2 evidence classes (cluster/competitor/"
                                       "privacy/pricing) — refused"}
    if not (customer_segment or "").strip() or not (proposed_solution or "").strip():
        return {"ok": False, "error": "a product gap needs a customer segment + a proposed solution"}
    all_refs = [x for r in classes for x in r]
    rec = {"gap_id": "gap_" + uuid.uuid4().hex[:10], "name": gap_name, "market": market,
           "customer_segment": customer_segment, "pain_cluster_refs": list(pain_cluster_refs or []),
           "competitor_refs": list(competitor_refs or []), "privacy_gap_refs": list(privacy_gap_refs or []),
           "pricing_gap_refs": list(pricing_gap_refs or []), "proposed_solution": proposed_solution,
           "why_now": why_now, "why_lamar_can_win": why_lamar_can_win, "evidence_refs": all_refs,
           "confidence": "high" if n_classes >= 3 else "medium"}
    storage.save(name, "mv_gap_%s" % rec["gap_id"], rec, store)
    storage.emit_truth(name, "mv_gap", rec["gap_id"], "PRODUCT GAP: %s (%s)" % (gap_name, rec["confidence"]),
                       actor="vera", store=store)
    return {"ok": True, "gap": rec}


def cluster_pattern(name: str, *, pattern_name: str, description: str, markets: list,
                    signal_ids: list | None = None, asset_fit: list | None = None,
                    store: Path | None = None) -> dict:
    """A repeated structure across one or more markets (e.g. 'expensive SaaS, simple core')."""
    rec = {"pattern_id": "pat_" + uuid.uuid4().hex[:10], "pattern_name": pattern_name,
           "description": description, "markets": list(markets), "signals": list(signal_ids or []),
           "repeated_structure": description, "fit_to_lamar_assets": list(asset_fit or []),
           "cross_market": len(markets) > 1,
           "confidence": "medium" if (signal_ids and len(signal_ids) >= 2) else "low"}
    storage.save(name, "mv_pattern_%s" % rec["pattern_id"], rec, store)
    storage.emit_truth(name, "mv_pattern", rec["pattern_id"], "PATTERN: " + pattern_name,
                       actor="vera", store=store)
    return rec


def cross_industry(name: str, *, source_market: str, target_market: str, shared_pattern: str,
                   transferable_solution: str, limits: list | None = None, evidence_ids: list | None = None,
                   store: Path | None = None) -> dict:
    """A cross-industry analogy. An analogy is NOT proof: it routes to research/validation, never a
    direct build. Limits of the analogy must be listed."""
    rec = {"analogy_id": "an_" + uuid.uuid4().hex[:10], "source_market": source_market,
           "target_market": target_market, "shared_pattern": shared_pattern,
           "transferable_solution": transferable_solution,
           "limits_of_analogy": list(limits or ["analogy is not proof — must be validated"]),
           "evidence_refs": list(evidence_ids or []),
           "routes_to": "research_or_validation",   # never direct build
           "confidence": "low"}
    storage.save(name, "mv_analogy_%s" % rec["analogy_id"], rec, store)
    storage.emit_truth(name, "mv_analogy", rec["analogy_id"],
                       "ANALOGY %s -> %s" % (source_market, target_market), actor="vera", store=store)
    return rec
