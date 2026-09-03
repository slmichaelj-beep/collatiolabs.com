"""marketplaces.fiverr.gigs — compliant gig factory + seller profile + account governance.

Gigs are drafted with clear packages, deliverables, requirements, and limitations; copy is scanned
for prohibited claims (guaranteed earnings/ROI/rankings/leads, fake scarcity, fake case studies,
"make you rich") and a hit blocks the draft. Publishing requires approval. The profile builder
refuses a fictional human persona (no fake identity; AI/company disclosure required). The account
record stores no raw credentials and enumerates allowed vs blocked Vera actions.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage

_PROHIBITED_CLAIMS = re.compile(
    r"(?i)\b(guaranteed (earnings|income|roi|ranking|rankings|leads|results|traffic)|"
    r"make you rich|get rich|#1 ranking|guaranteed first page|100% guaranteed|risk[- ]?free|"
    r"as seen on|thousands of happy customers)\b")

# the 5 prioritized starter gigs (compliant, fast-fulfillable, AI-enabled)
STARTER_GIGS = [
    {"key": "ai_workflow_audit", "title": "I will audit your business workflows and find practical AI automation opportunities",
     "prices": (250, 750, 1500)},
    {"key": "website_teardown", "title": "I will review your website and give you a practical revenue conversion teardown",
     "prices": (150, 500, 1000)},
    {"key": "competitor_pricing", "title": "I will research your competitors and create a pricing and positioning report",
     "prices": (250, 750, 1500)},
    {"key": "workforce_blueprint", "title": "I will design an AI assistant and digital workforce blueprint for your business",
     "prices": (300, 900, 2000)},
    {"key": "sop_workflow", "title": "I will turn your business process into a clear SOP and automation-ready workflow",
     "prices": (150, 500, 1200)},
]


def draft_gig(name: str, *, title: str, category: str, prices: tuple, deliverables: dict,
              delivery_days: tuple, description: str, requirements_from_buyer: list,
              limitations: list, search_tags: list | None = None, policy_gate_ref: str = "",
              store: Path | None = None) -> dict:
    """Draft a compliant gig. Refused if copy contains a prohibited claim, or without limitations /
    buyer requirements. Starts as draft — publishing requires approval."""
    blob = " ".join([title, description] + (limitations or []) +
                    [d for pkg in deliverables.values() for d in pkg])
    if _PROHIBITED_CLAIMS.search(blob):
        return {"ok": False, "error": "prohibited/unsupported claim in gig copy — blocked", "prohibited_claims_check": "fail"}
    if not limitations:
        return {"ok": False, "error": "a gig must state its limitations"}
    if not requirements_from_buyer:
        return {"ok": False, "error": "a gig must state the buyer requirements it needs"}
    def pkg(i, n): return {"name": n, "price": prices[i], "delivery_days": delivery_days[i],
                           "deliverables": deliverables.get(n, [])}
    rec = {"gig_id": "fgig_" + uuid.uuid4().hex[:10], "title": title, "category": category,
           "search_tags": list(search_tags or []),
           "basic_package": pkg(0, "basic"), "standard_package": pkg(1, "standard"),
           "premium_package": pkg(2, "premium"), "description": description,
           "requirements_from_buyer": list(requirements_from_buyer), "limitations": list(limitations),
           "prohibited_claims_check": "pass", "policy_gate_ref": policy_gate_ref,
           "approval_required": True, "status": "draft"}
    storage.save(name, "fiverr_gig_%s" % rec["gig_id"], rec, store)
    _idx(name, "fiverr_gig_index", rec["gig_id"], store)
    storage.emit_truth(name, "fiverr_gig", rec["gig_id"], "GIG draft: " + title, actor="vera", store=store)
    return {"ok": True, "gig": rec}


def publish_gig(name: str, gig_id: str, *, approval_ref: str = "", account_active: bool = False,
                store: Path | None = None) -> dict:
    """Publish a gig. REFUSED without approval and an active (human-verified) seller account."""
    rec = storage.load(name, "fiverr_gig_%s" % gig_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such gig"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "publishing a gig requires approval"}
    if not account_active:
        return {"ok": False, "error": "no active (human-verified) seller account — cannot publish"}
    rec["status"] = "published"; rec["approval_ref"] = approval_ref
    storage.save(name, "fiverr_gig_%s" % gig_id, rec, store)
    return {"ok": True, "gig": rec}


def build_profile(name: str, *, display_name: str, bio: str, represents: str,
                  ai_disclosure: str = "", fictional_persona: bool = False, store: Path | None = None) -> dict:
    """Draft a truthful seller profile. A fictional human persona is refused; AI/company disclosure
    is required; identity verification is human-only."""
    if fictional_persona:
        return {"ok": False, "error": "no fictional human persona — the profile must truthfully represent Lamar/Collatio"}
    if represents not in ("Lamar", "Collatio Labs LLC"):
        return {"ok": False, "error": "profile must represent the real seller (Lamar or Collatio Labs LLC)"}
    if not (ai_disclosure or "").strip():
        return {"ok": False, "error": "an AI/operator disclosure is required (no implying Vera is a human employee)"}
    rec = {"display_name": display_name, "bio": bio, "represents": represents,
           "ai_disclosure_policy": ai_disclosure, "verification": "human-only",
           "profile_status": "approval_required"}
    storage.save(name, "fiverr_profile", rec, store)
    return {"ok": True, "profile": rec}


def account_record(name: str, *, status: str = "planned", two_factor_enabled: str = "unknown",
                   identity_verified: str = "unknown", store: Path | None = None) -> dict:
    rec = {"account_id": "fiverr_collatio", "platform": "fiverr", "owner": "Lamar/Collatio Labs LLC",
           "status": status, "credentials_location": "password_manager_ref_only",
           "raw_credentials_stored": False, "two_factor_enabled": two_factor_enabled,
           "identity_verified": identity_verified,
           "allowed_vera_actions": ["draft_gigs", "draft_messages", "draft_order_responses",
                                    "track_orders", "prepare_deliverables"],
           "blocked_vera_actions": ["mass_message", "scrape", "fake_review", "circumvent_payment",
                                    "create_multiple_accounts"]}
    storage.save(name, "fiverr_account", rec, store)
    return {"ok": True, "account": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def gigs(name, store=None) -> list:
    idx = storage.load(name, "fiverr_gig_index", store, default={"ids": []})["ids"]
    return [g for g in (storage.load(name, "fiverr_gig_%s" % i, store, default=None) for i in idx) if g]
