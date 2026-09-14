"""compounding.growth — partnership + expansion + acquisition watch + reinvestment policy.

Partnerships multiply distribution but never deceptively: an agreement needs approval and revenue-
share needs legal review. Expansion scales proven winners with evidence + a capacity check + budget
approval. Acquisition watch is RESEARCH-ONLY: candidates are tracked with labeled valuation
assumptions; outreach is blocked without approval and legal/financial review. The reinvestment
policy keeps a reserve, funds winners on evidence, protects quality/support, and never spends
without approval.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

PARTNER_TYPES = ("agency", "consultant", "software_vendor", "local_business_group", "creator_community",
                 "developer_community", "professional_firm", "marketplace", "affiliate_referral")
EXPANSION_PATHS = ("new_buyer_segment", "new_geography", "new_vertical", "higher_ticket",
                   "recurring_subscription", "enterprise_deployment", "add_on_service",
                   "software_automation", "team_expansion", "partner_channel")
REINVEST_BUCKETS = ("sales_tests", "automation", "engineering", "support_qa", "content_distribution",
                    "partnerships", "professional_review", "infrastructure", "security_compliance", "cash_reserve")


def partnership(name: str, *, partner_type: str, value_proposition: str, revenue_share: bool = False,
                approval_ref: str = "", legal_review_ref: str = "", store: Path | None = None) -> dict:
    """Propose a partnership. Needs approval; revenue-share additionally needs legal review."""
    if partner_type not in PARTNER_TYPES:
        return {"ok": False, "error": "unknown partner type %r" % partner_type}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "a partnership agreement requires approval"}
    if revenue_share and not (legal_review_ref or "").strip():
        return {"ok": False, "error": "revenue-share requires legal review"}
    rec = {"partnership_id": "part_" + uuid.uuid4().hex[:8], "partner_type": partner_type,
           "value_proposition": value_proposition, "revenue_share": revenue_share,
           "approval_ref": approval_ref, "legal_review_ref": legal_review_ref or None,
           "no_affiliate_spam": True, "status": "approved"}
    storage.save(name, "comp_part_%s" % rec["partnership_id"], rec, store)
    return {"ok": True, "partnership": rec}


def expand(name: str, *, workstream_id: str, path: str, evidence_present: bool, capacity_ok: bool,
           approval_ref: str = "", quality_risk: str = "low", store: Path | None = None) -> dict:
    """Expand a proven winner. Needs evidence + a capacity check + budget approval."""
    if path not in EXPANSION_PATHS:
        return {"ok": False, "error": "unknown expansion path %r" % path}
    if not evidence_present:
        return {"ok": False, "error": "expansion needs evidence of a proven winner"}
    if not capacity_ok:
        return {"ok": False, "error": "expansion needs a capacity check"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "expansion budget requires approval"}
    rec = {"expansion_id": "exp_" + uuid.uuid4().hex[:8], "workstream_id": workstream_id, "path": path,
           "approval_ref": approval_ref, "quality_risk": quality_risk, "status": "approved"}
    storage.save(name, "comp_expand_%s" % rec["expansion_id"], rec, store)
    return {"ok": True, "expansion": rec}


def acquisition_watch(name: str, *, candidate: str, candidate_type: str, strategic_rationale: str,
                      valuation_assumptions: list, store: Path | None = None) -> dict:
    """Track an acquisition candidate — RESEARCH ONLY. Valuation is always labeled assumptions;
    outreach/legal/financial action is explicitly not performed here."""
    if not strategic_rationale:
        return {"ok": False, "error": "an acquisition candidate needs a strategic rationale"}
    rec = {"acquisition_id": "acq_" + uuid.uuid4().hex[:8], "candidate": candidate,
           "candidate_type": candidate_type, "strategic_rationale": strategic_rationale,
           "valuation_assumptions": list(valuation_assumptions or []),
           "valuation_is_assumption": True, "status": "watch",
           "outreach_status": "BLOCKED — outreach needs approval + legal/financial review",
           "legal_financial_action": "human-only"}
    storage.save(name, "comp_acq_%s" % rec["acquisition_id"], rec, store)
    _idx(name, "comp_acq_index", rec["acquisition_id"], store)
    return {"ok": True, "acquisition": rec}


def acquisition_outreach(name: str, acquisition_id: str, *, approval_ref: str = "",
                         legal_review_ref: str = "", store: Path | None = None) -> dict:
    """Attempt acquisition outreach. REFUSED without approval AND legal/financial review."""
    if not (approval_ref and legal_review_ref):
        return {"ok": False, "error": "acquisition outreach needs approval + legal/financial review"}
    return {"ok": True, "note": "outreach authorized by human; Vera does not negotiate/sign"}


def reinvest(name: str, *, period: str, allocations: dict, reserve_pct: float = 0.2,
             approval_ref: str = "", winners_evidence: bool = True, store: Path | None = None) -> dict:
    """Build a reinvestment plan. Refused without a cash reserve, without approval, or if it would
    starve quality/support, or fund unproven 'winners' without evidence."""
    if reserve_pct < 0.05:
        return {"ok": False, "error": "must keep a cash reserve"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "reinvestment requires approval"}
    if allocations.get("support_qa", 0) <= 0 and allocations.get("sales_tests", 0) > 0:
        return {"ok": False, "error": "do not starve quality/support while funding growth"}
    if allocations.get("automation", 0) > 0 and not winners_evidence:
        return {"ok": False, "error": "do not overfund unproven ideas"}
    rec = {"reinvest_id": "rein_" + uuid.uuid4().hex[:8], "period": period,
           "allocations": dict(allocations), "reserve_pct": reserve_pct, "approval_ref": approval_ref,
           "protects_quality_support": True}
    storage.save(name, "comp_reinvest_%s" % period, rec, store)
    return {"ok": True, "reinvestment": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def acquisition_watchlist(name, store=None) -> list:
    idx = storage.load(name, "comp_acq_index", store, default={"ids": []})["ids"]
    return [a for a in (storage.load(name, "comp_acq_%s" % i, store, default=None) for i in idx) if a]
