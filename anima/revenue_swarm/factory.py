"""revenue_swarm.factory — experiment factory + offer variants + channel tests.

An experiment needs a hypothesis, success criteria, kill criteria, a budget, an approval, and a
fulfillment plan before it can run. Offer variants keep claims consistent and label price
assumptions. Channel tests are policy-checked: forbidden channels (spam, fake accounts/engagement,
bot posting, terms-violating scraping) are refused; everything else is approval-gated.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

METHODS = ("ten_lead_outreach", "landing_waitlist", "paid_consult", "audit_presale", "concierge_mvp",
           "marketplace_listing", "warm_network_offer", "content_inbound", "proposal_test", "pricing_test")
VARIANT_TYPES = ("cheap_report", "premium_audit", "done_for_you", "subscription_support",
                 "implementation", "free_core_paid_setup", "high_ticket_private")
APPROVED_CHANNELS = ("warm_intro", "direct_email_approved", "founder_network", "approved_community",
                     "content_post", "landing_page", "search_demand", "referral", "partner_outreach",
                     "inbound_lead_magnet", "manual_local_outreach")
FORBIDDEN_CHANNELS = ("spam", "fake_account", "fake_engagement", "bot_posting", "scraping_tos_violation",
                      "deceptive_community")


def create_experiment(name: str, *, opportunity_id: str, offer_id: str, hypothesis: str, method: str,
                      buyer_segment: str, budget: float, duration_days: int, success_criteria: list,
                      kill_criteria: list, fulfillment_plan: str = "", store: Path | None = None) -> dict:
    """Create a revenue experiment. Refused without success + kill criteria, a budget, and a
    fulfillment plan. Always requires approval before running."""
    if method not in METHODS:
        return {"ok": False, "error": "unknown method %r" % method}
    if not success_criteria or not kill_criteria:
        return {"ok": False, "error": "an experiment needs success + kill criteria"}
    if budget is None:
        return {"ok": False, "error": "an experiment needs a budget (even $0)"}
    if not (fulfillment_plan or "").strip():
        return {"ok": False, "error": "an experiment needs a fulfillment plan (can we deliver?)"}
    rec = {"experiment_id": "rxp_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id,
           "offer_id": offer_id, "hypothesis": hypothesis, "method": method,
           "buyer_segment": buyer_segment, "budget": float(budget), "duration_days": duration_days,
           "success_criteria": list(success_criteria), "kill_criteria": list(kill_criteria),
           "fulfillment_plan": fulfillment_plan, "approval_required": True,
           "status": "approval_pending", "results": {}, "created_at": storage.now()}
    storage.save(name, "swarm_exp_%s" % rec["experiment_id"], rec, store)
    _idx(name, rec["experiment_id"], store)
    storage.emit_truth(name, "swarm_exp", rec["experiment_id"], "EXPERIMENT: %s (%s)" % (hypothesis, method),
                       actor="vera", store=store)
    return {"ok": True, "experiment": rec}


def approve_experiment(name: str, experiment_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "running an experiment requires approval"}
    rec = storage.load(name, "swarm_exp_%s" % experiment_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such experiment"}
    rec["status"] = "approved"; rec["approval_ref"] = approval_ref
    storage.save(name, "swarm_exp_%s" % experiment_id, rec, store)
    return {"ok": True, "experiment": rec}


def offer_variant(name: str, *, experiment_id: str, variant_type: str, price: float,
                  price_is_assumption: bool = True, differentiation: str = "",
                  differentiation_proof: list | None = None, store: Path | None = None) -> dict:
    """Create an offer variant. Unsupported differentiation (a claim with no proof) is refused."""
    if variant_type not in VARIANT_TYPES:
        return {"ok": False, "error": "unknown variant type %r" % variant_type}
    if differentiation and not (differentiation_proof or []):
        return {"ok": False, "error": "unsupported differentiation claim — refused"}
    rec = {"variant_id": "var_" + uuid.uuid4().hex[:8], "experiment_id": experiment_id,
           "variant_type": variant_type, "price": price, "price_is_assumption": price_is_assumption,
           "differentiation": differentiation, "differentiation_proof": list(differentiation_proof or []),
           "performance": {"leads": 0, "replies": 0, "cash": 0.0}}
    storage.save(name, "swarm_variant_%s" % rec["variant_id"], rec, store)
    return {"ok": True, "variant": rec}


def channel_test(name: str, *, experiment_id: str, channel: str, policy_ok: bool = True,
                 approval_ref: str = "", store: Path | None = None) -> dict:
    """Define a channel test. Forbidden channels refused; a policy-violating channel refused;
    outreach channels require approval."""
    if channel in FORBIDDEN_CHANNELS or channel not in APPROVED_CHANNELS:
        return {"ok": False, "error": "channel %r is forbidden/unknown" % channel}
    if not policy_ok:
        return {"ok": False, "error": "channel violates source/platform policy — refused"}
    outreach = channel in ("direct_email_approved", "partner_outreach", "manual_local_outreach")
    if outreach and not (approval_ref or "").strip():
        return {"ok": False, "error": "outreach channel requires approval"}
    rec = {"channel_test_id": "cht_" + uuid.uuid4().hex[:8], "experiment_id": experiment_id,
           "channel": channel, "approval_ref": approval_ref or None, "results_captured": True}
    storage.save(name, "swarm_channel_%s" % rec["channel_test_id"], rec, store)
    return {"ok": True, "channel_test": rec}


def _idx(name, eid, store):
    idx = storage.load(name, "swarm_exp_index", store, default={"ids": []}); idx["ids"].append(eid)
    storage.save(name, "swarm_exp_index", idx, store)


def list_experiments(name, store=None) -> list:
    idx = storage.load(name, "swarm_exp_index", store, default={"ids": []})["ids"]
    return [e for e in (storage.load(name, "swarm_exp_%s" % i, store, default=None) for i in idx) if e]
