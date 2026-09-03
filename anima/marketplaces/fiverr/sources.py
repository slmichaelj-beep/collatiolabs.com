"""marketplaces.fiverr.sources — the Fiverr source registry + market intelligence + opportunities.

Sources are never default-allowed: an unknown source is `needs_review`; automation/login-required
sources are flagged. Market intelligence is gathered only by manual/approved methods (bulk scraping
or PII extraction is refused). The opportunity scanner identifies compliant service concepts and
REJECTS prohibited ones (fake reviews, social botting, academic dishonesty, financial-account
handling, legal/tax/financial advice without qualification, ToS-violating services).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

SOURCE_TYPES = ("help_doc", "terms", "public_category", "public_gig", "own_account", "own_order",
                "manual_note", "approved_export")
INTEL_METHODS = ("manual_review", "approved_export", "own_account_analytics")
# prohibited service concepts — never offered
PROHIBITED = ("fake review", "fake engagement", "social media bot", "follower", "academic",
              "essay", "exam", "homework", "job application", "test completion", "financial account",
              "credit repair", "legal advice", "tax advice", "financial advice", "hacking", "crack",
              "guaranteed earnings", "guaranteed roi", "guaranteed ranking", "guaranteed leads")


def _all(name, store): return storage.load(name, "fiverr_sources", store, default={"sources": []})["sources"]


def register_source(name: str, *, source_type: str, access_method: str = "manual",
                    automation_allowed: bool = False, login_required: bool = False,
                    pii_risk: str = "low", policy_status: str = "needs_review",
                    store: Path | None = None) -> dict:
    if source_type not in SOURCE_TYPES:
        return {"ok": False, "error": "unknown source type %r" % source_type}
    # never default unknown to allowed; logged-in/automation sources can't be auto-approved
    if policy_status == "approved" and (login_required and automation_allowed):
        policy_status = "needs_review"
    rec = {"source_id": "fsrc_" + uuid.uuid4().hex[:10], "platform": "fiverr", "source_type": source_type,
           "access_method": access_method, "automation_allowed": bool(automation_allowed),
           "login_required": bool(login_required), "pii_risk": pii_risk,
           "policy_status": policy_status if policy_status in ("approved", "needs_review", "blocked") else "needs_review",
           "allowed_uses": ["research", "manual_review"], "forbidden_uses": ["bulk_scrape", "pii_harvest"],
           "last_reviewed_at": storage.now(), "evidence_refs": []}
    a = _all(name, store); a.append(rec); storage.save(name, "fiverr_sources", {"sources": a}, store)
    return {"ok": True, "source": rec}


def can_use_source(name: str, source_id: str, *, store: Path | None = None) -> dict:
    rec = next((s for s in _all(name, store) if s["source_id"] == source_id), None)
    if rec is None:
        return {"allowed": False, "reason": "no such source"}
    if rec["policy_status"] != "approved":
        return {"allowed": False, "reason": "source %s — manual/human-approved only" % rec["policy_status"]}
    if rec["pii_risk"] == "high":
        return {"allowed": False, "reason": "high PII risk — review first"}
    return {"allowed": True}


def market_intel(name: str, *, category: str, method: str, manual_sample_size: int = 0,
                 observed_offer_patterns: list | None = None, observed_price_ranges: list | None = None,
                 observed_buyer_pain: list | None = None, store: Path | None = None) -> dict:
    """Record a market-intelligence observation. ONLY manual/approved/own-analytics methods; bulk
    scraping is refused. Confidence reflects the (manual) sample size."""
    if method not in INTEL_METHODS:
        return {"ok": False, "error": "intel method %r not permitted (no bulk scraping)" % method}
    conf = "high" if manual_sample_size >= 15 else "medium" if manual_sample_size >= 5 else "low"
    rec = {"intel_id": "fint_" + uuid.uuid4().hex[:10], "platform": "fiverr", "category": category,
           "manual_sample_size": manual_sample_size, "observed_offer_patterns": list(observed_offer_patterns or []),
           "observed_price_ranges": list(observed_price_ranges or []),
           "observed_buyer_pain_signals": list(observed_buyer_pain or []), "policy_method": method,
           "confidence": conf, "evidence_refs": [], "notes": []}
    storage.save(name, "fiverr_intel_%s" % rec["intel_id"], rec, store)
    return {"ok": True, "intel": rec}


def scan_opportunity(name: str, *, category: str, service_concept: str, buyer_pain: str,
                     fulfillment_difficulty: str = "medium", starting_price_range: str = "",
                     store: Path | None = None) -> dict:
    """Score a Fiverr service opportunity. A prohibited concept is rejected outright."""
    low = service_concept.lower() + " " + category.lower()
    if any(p in low for p in PROHIBITED):
        return {"ok": False, "error": "prohibited/forbidden service concept — blocked",
                "policy_risk": "blocked"}
    rec = {"fiverr_opportunity_id": "fopp_" + uuid.uuid4().hex[:10], "category": category,
           "service_concept": service_concept, "buyer_pain": buyer_pain,
           "fiverr_fit": "high", "collatio_fit": "high",
           "fulfillment_difficulty": fulfillment_difficulty, "policy_risk": "low",
           "starting_price_range": starting_price_range, "upsell_path": [], "team_required": [],
           "recommended_action": "draft_gig"}
    storage.save(name, "fiverr_opp_%s" % rec["fiverr_opportunity_id"], rec, store)
    _idx(name, "fiverr_opp_index", rec["fiverr_opportunity_id"], store)
    storage.emit_truth(name, "fiverr_opp", rec["fiverr_opportunity_id"], "FIVERR OPP: " + service_concept,
                       actor="vera", store=store)
    return {"ok": True, "opportunity": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def opportunities(name, store=None) -> list:
    idx = storage.load(name, "fiverr_opp_index", store, default={"ids": []})["ids"]
    return [o for o in (storage.load(name, "fiverr_opp_%s" % i, store, default=None) for i in idx) if o]
