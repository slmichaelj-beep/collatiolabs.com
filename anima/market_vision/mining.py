"""market_vision.mining — find repeated pain, incumbent weakness, privacy abuse, pricing arbitrage.

All four analyzers share the same discipline: a claim about a competitor / a company's data
practices / a price must be backed by cited signals, never asserted. A single complaint is
low-confidence and is not a market; willingness-to-pay is never inferred from a complaint alone.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import signals as _sig


def _conf_from_count(n: int) -> str:
    return "high" if n >= 5 else "medium" if n >= 3 else "low"


def cluster_complaints(name: str, *, theme: str, signal_ids: list, industry: str = "",
                       customer_segment: str = "", store: Path | None = None) -> dict:
    """Cluster repeated complaint signals into a theme. A single signal stays low-confidence;
    willingness-to-pay is NOT inferred here."""
    sigs = _sig.by_ids(name, signal_ids, store)
    rec = {"cluster_id": "cl_" + uuid.uuid4().hex[:10], "theme": theme, "industry": industry,
           "customer_segment": customer_segment, "signals": [s["signal_id"] for s in sigs],
           "frequency": len(sigs),
           "pain_intensity": "high" if any(s["severity"] == "high" for s in sigs) else "medium" if sigs else "low",
           "representative_quotes_refs": [s["evidence_excerpt_ref"] for s in sigs if s.get("evidence_excerpt_ref")],
           "current_alternatives": list({s.get("current_solution") for s in sigs if s.get("current_solution")}),
           "opportunity_hint": "underserved: %s" % theme if len(sigs) >= 3 else "weak signal — needs more evidence",
           "willingness_to_pay": "unknown — not inferable from complaints alone",
           "confidence": _conf_from_count(len(sigs))}
    storage.save(name, "mv_cluster_%s" % rec["cluster_id"], rec, store)
    storage.emit_truth(name, "mv_cluster", rec["cluster_id"],
                       "CLUSTER %s (%d signals, %s)" % (theme, len(sigs), rec["confidence"]),
                       actor="vera", store=store)
    return rec


def analyze_competitor(name: str, *, competitor_name: str, market: str, weaknesses: list,
                       evidence_signal_ids: list, pricing_notes: list | None = None,
                       privacy_notes: list | None = None, store: Path | None = None) -> dict:
    """A competitor weakness record. Every weakness/pricing/privacy claim must be backed by cited
    signals — an unsupported claim is refused (no defamation, no uncited pricing/privacy claim)."""
    sigs = _sig.by_ids(name, evidence_signal_ids, store)
    if (weaknesses or pricing_notes or privacy_notes) and not sigs:
        return {"ok": False, "error": "competitor claims require cited evidence signals — refused"}
    rec = {"competitor_id": "cmp_" + uuid.uuid4().hex[:10], "competitor_name": competitor_name,
           "market": market, "weaknesses": list(weaknesses), "pricing_notes": list(pricing_notes or []),
           "privacy_notes": list(privacy_notes or []),
           "evidence_refs": [s["signal_id"] for s in sigs],
           "evidence_sources": list({s["source_name"] for s in sigs}),
           "opportunity_angle": ("a focused, lower-friction alternative addressing: " +
                                 ", ".join(weaknesses[:3])) if weaknesses else "",
           "confidence": _conf_from_count(len(sigs))}
    storage.save(name, "mv_competitor_%s" % rec["competitor_id"], rec, store)
    storage.emit_truth(name, "mv_competitor", rec["competitor_id"],
                       "COMPETITOR weakness: %s (%s)" % (competitor_name, rec["confidence"]),
                       actor="vera", store=store)
    return {"ok": True, "competitor": rec}


def detect_privacy_gap(name: str, *, market: str, incumbent: str, observed_practice: str,
                       user_concern_signal_ids: list, better_model: str = "local_first",
                       claims_data_sale: bool = False, store: Path | None = None) -> dict:
    """A privacy-first disruption angle. A data-SALE claim requires explicit cited evidence;
    tracking / ads / sharing / unclear-policy are distinguished, not conflated."""
    sigs = _sig.by_ids(name, user_concern_signal_ids, store)
    if not sigs:
        return {"ok": False, "error": "privacy gap requires cited user-concern signals — refused"}
    if claims_data_sale and not any(s.get("evidence_excerpt_ref") for s in sigs):
        return {"ok": False, "error": "a data-SALE claim needs specific cited evidence — refused"}
    rec = {"privacy_gap_id": "pg_" + uuid.uuid4().hex[:10], "market": market, "incumbent": incumbent,
           "observed_practice": observed_practice,
           "claim_type": "data_sale" if claims_data_sale else "concern_only",
           "user_concern_signals": [s["signal_id"] for s in sigs], "better_model": better_model,
           "evidence_refs": [s["evidence_excerpt_ref"] for s in sigs if s.get("evidence_excerpt_ref")],
           "risk": "medium",
           "opportunity_thesis": "a %s alternative to %s for %s" % (better_model, incumbent, market),
           "technical_feasibility": "flag: privacy-first claim must be technically true before any public claim"}
    storage.save(name, "mv_privacy_%s" % rec["privacy_gap_id"], rec, store)
    storage.emit_truth(name, "mv_privacy", rec["privacy_gap_id"],
                       "PRIVACY gap: %s vs %s" % (market, incumbent), actor="vera", store=store)
    return {"ok": True, "privacy_gap": rec}


def scan_pricing(name: str, *, market: str, incumbent_pricing_refs: list, pricing_pain_signal_ids: list,
                 low_cost_angle: str = "", est_cost_to_serve: float | None = None,
                 paid_layer_options: list | None = None, store: Path | None = None) -> dict:
    """A pricing-arbitrage opportunity. High price ALONE is not an opportunity: the scan is refused
    unless there is cited pricing-pain AND a cost-to-serve estimate AND a paid monetization layer
    (no race-to-zero)."""
    sigs = _sig.by_ids(name, pricing_pain_signal_ids, store)
    if not sigs:
        return {"ok": False, "error": "pricing gap requires cited pricing-pain signals — refused"}
    if est_cost_to_serve is None:
        return {"ok": False, "error": "high price alone is not an opportunity — estimate cost-to-serve"}
    if not (paid_layer_options or []):
        return {"ok": False, "error": "no monetization layer — would be race-to-zero, refused"}
    rec = {"pricing_gap_id": "prg_" + uuid.uuid4().hex[:10], "market": market,
           "incumbent_pricing_refs": list(incumbent_pricing_refs),
           "user_pricing_pain_signals": [s["signal_id"] for s in sigs],
           "low_cost_alternative_angle": low_cost_angle, "est_cost_to_serve": est_cost_to_serve,
           "free_core_viability": "medium", "paid_layer_options": list(paid_layer_options),
           "margin_potential": "medium", "confidence": _conf_from_count(len(sigs))}
    storage.save(name, "mv_pricing_%s" % rec["pricing_gap_id"], rec, store)
    storage.emit_truth(name, "mv_pricing", rec["pricing_gap_id"], "PRICING arbitrage: " + market,
                       actor="vera", store=store)
    return {"ok": True, "pricing_gap": rec}
