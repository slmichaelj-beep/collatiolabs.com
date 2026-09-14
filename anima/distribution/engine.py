"""distribution.engine — buyer database + distribution asset builder + partner channels + funnels.

The buyer database enforces source policy (approved/needs_review/blocked) and never permits contact
without approval. Distribution assets (landing/comparison/lead-magnet/SEO/content/pricing pages) are
drafts whose claims are proof-checked; publishing is a human action. Partner channels need approval;
revenue-share needs legal review. Funnels track which channel produced real leads/cash (honestly).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

APPROVED_SOURCES = ("lamar_provided", "public_company_website", "approved_directory", "warm_network",
                    "inbound_list", "manual_founder_target", "public_business_listing", "approved_crm_import")
FORBIDDEN_SOURCES = ("spam_list", "unlawful_scraping", "fake_account", "deceptive_enrichment",
                     "platform_abuse", "private_personal_data")
ASSET_TYPES = ("landing_page", "comparison_page", "free_tool", "lead_magnet", "industry_report",
               "email_sequence", "partner_pitch", "referral_offer", "case_study_page", "demo_page",
               "pricing_page", "seo_page")
PARTNER_TYPES = ("agency", "consultant", "software_vendor", "community", "marketplace", "affiliate_referral")


# ---- buyer database ----
def add_buyer(name: str, *, company: str, buyer_type: str, source: str, pain_hypothesis: str,
              role: str = "", industry: str = "", store: Path | None = None) -> dict:
    if source in FORBIDDEN_SOURCES:
        return {"ok": False, "error": "forbidden buyer source %r" % source}
    policy = "approved" if source in APPROVED_SOURCES else "needs_review"
    rec = {"buyer_profile_id": "bp_" + uuid.uuid4().hex[:10], "buyer_type": buyer_type, "industry": industry,
           "company": company, "role": role, "pain_hypothesis": pain_hypothesis, "source": source,
           "source_policy": policy, "contact_allowed": False, "approval_required": True,
           "last_contacted": None, "status": "research" if policy == "needs_review" else "qualified",
           "truth_refs": [], "observation_refs": []}
    storage.save(name, "dist_buyer_%s" % rec["buyer_profile_id"], rec, store)
    _idx(name, "dist_buyer_index", rec["buyer_profile_id"], store)
    return {"ok": True, "buyer": rec}


def can_contact(name: str, buyer_profile_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    rec = storage.load(name, "dist_buyer_%s" % buyer_profile_id, store, default=None)
    if not rec:
        return {"allowed": False, "reason": "no such buyer"}
    if rec["source_policy"] == "blocked":
        return {"allowed": False, "reason": "buyer source blocked"}
    if rec["status"] == "disqualified":
        return {"allowed": False, "reason": "buyer disqualified"}
    if rec["source_policy"] == "needs_review":
        return {"allowed": False, "reason": "source needs review before contact", "needs_review": True}
    if not (approval_ref or "").strip():
        return {"allowed": False, "reason": "contact requires approval", "approval_required": True}
    return {"allowed": True}


# ---- distribution assets ----
def build_asset(name: str, *, asset_type: str, target_buyer: str, pain: str, offer: str, cta: str,
                claims: list | None = None, proof_refs: list | None = None, store: Path | None = None) -> dict:
    """Build a draft distribution asset. A claim with no proof ref is refused. Draft only — publishing
    requires approval."""
    if asset_type not in ASSET_TYPES:
        return {"ok": False, "error": "unknown asset type %r" % asset_type}
    claims = claims or []; proof_refs = proof_refs or []
    if claims and not proof_refs:
        return {"ok": False, "error": "asset claims present but no proof — refused"}
    rec = {"asset_id": "da_" + uuid.uuid4().hex[:10], "asset_type": asset_type, "target_buyer": target_buyer,
           "pain": pain, "offer": offer, "cta": cta, "claims": list(claims), "proof_refs": list(proof_refs),
           "status": "draft", "publication_status": "NOT published — publishing requires approval"}
    storage.save(name, "dist_asset_%s" % rec["asset_id"], rec, store)
    _idx(name, "dist_asset_index", rec["asset_id"], store)
    storage.emit_truth(name, "dist_asset", rec["asset_id"], "ASSET draft: %s" % asset_type, actor="vera", store=store)
    return {"ok": True, "asset": rec}


def publish_asset(name: str, asset_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "publishing public content requires approval"}
    rec = storage.load(name, "dist_asset_%s" % asset_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such asset"}
    rec["status"] = "published"; rec["publication_status"] = "published (approved)"; rec["approval_ref"] = approval_ref
    storage.save(name, "dist_asset_%s" % asset_id, rec, store)
    return {"ok": True, "asset": rec}


# ---- partner channels ----
def add_partner(name: str, *, partner_type: str, value_proposition: str, revenue_share: bool = False,
                approval_ref: str = "", legal_review_ref: str = "", store: Path | None = None) -> dict:
    if partner_type not in PARTNER_TYPES:
        return {"ok": False, "error": "unknown partner type %r" % partner_type}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "a partner agreement requires approval"}
    if revenue_share and not (legal_review_ref or "").strip():
        return {"ok": False, "error": "revenue-share requires legal review"}
    rec = {"partner_id": "dpar_" + uuid.uuid4().hex[:8], "partner_type": partner_type,
           "value_proposition": value_proposition, "revenue_share": revenue_share,
           "approval_ref": approval_ref, "legal_review_ref": legal_review_ref or None, "no_affiliate_spam": True}
    storage.save(name, "dist_partner_%s" % rec["partner_id"], rec, store)
    return {"ok": True, "partner": rec}


def record_funnel(name: str, *, asset_id: str, leads: int = 0, cash: float = 0.0, store: Path | None = None) -> dict:
    rec = {"asset_id": asset_id, "leads": leads, "cash": cash}
    storage.save(name, "dist_funnel_%s" % asset_id, rec, store)
    return {"ok": True, "funnel": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def _list(name, idxkey, pattern, store):
    idx = storage.load(name, idxkey, store, default={"ids": []})["ids"]
    return [x for x in (storage.load(name, pattern % i, store, default=None) for i in idx) if x]


def overview(name: str, store: Path | None = None) -> dict:
    buyers = _list(name, "dist_buyer_index", "dist_buyer_%s", store)
    assets = _list(name, "dist_asset_index", "dist_asset_%s", store)
    return {"ok": True,
            "buyers": {"total": len(buyers),
                       "approved": sum(1 for b in buyers if b["source_policy"] == "approved"),
                       "needs_review": sum(1 for b in buyers if b["source_policy"] == "needs_review")},
            "assets": [{"type": a["asset_type"], "status": a["status"]} for a in assets],
            "published": [a["asset_type"] for a in assets if a["status"] == "published"],
            "honesty": "buyers are contact-gated by source policy + approval; assets are drafts until "
                       "approved; partner revenue-share needs legal review."}
