"""revenue.strike — cash-wedge finder + 24h offer packager + buyer shortlist + sales sprint + fulfillment.

Find ranked immediate-income opportunities (blocked / unknown-ownership assets excluded; sell_now
requires proof + a delivery plan), package one offer (unsupported claims blocked; launch needs
approval), build a buyer shortlist from APPROVED sources only (forbidden sources refused;
disqualified buyers never contacted; outreach approval-gated), draft a sales sprint (claims
proof-checked; spam/fake-urgency blocked; send blocked without approval), and require a fulfillment
packet BEFORE any sale.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage
from anima.commercial import assets as _assets, ip_license as _ip

OFFER_TYPES = ("audit", "report", "service", "implementation", "software", "hybrid")
TIME_TO_PACKAGE = ("same_day", "24h", "72h", "1_week")
APPROVED_BUYER_SOURCES = ("lamar_provided", "public_company_website", "approved_directory",
                          "warm_network", "inbound_list", "manual_founder_target",
                          "public_business_listing", "approved_crm_import")
FORBIDDEN_BUYER_SOURCES = ("spam_list", "unlawful_scraping", "fake_account", "deceptive_enrichment",
                           "platform_abuse", "private_personal_data")
_SPAM = re.compile(r"\b(?:act now|limited time|100% free|guaranteed|risk[- ]?free|buy now|urgent!!!)\b", re.I)
_FAKE = re.compile(r"\b(?:thousands of happy customers|everyone is switching|#1 in the world|as seen on)\b", re.I)


# ---- cash wedge finder ----
def find_cash_wedge(name: str, *, wedge_name: str, offer_type: str, buyer: str, pain: str,
                    deliverable: str, price_range: str, time_to_package: str = "72h",
                    fulfillment_complexity: str = "low", proof_available: list | None = None,
                    asset_id: str | None = None, store: Path | None = None) -> dict:
    """Register a cash wedge. If it's tied to an asset, the asset must be IP/license clear. sell_now
    requires proof; otherwise the recommendation is package_today / validate_first."""
    proof = proof_available or []
    if asset_id:
        gate = _ip.can_sell(name, asset_id, store=store)
        if not gate["allowed"]:
            return {"ok": False, "error": "asset not sellable (IP/license)", "blockers": gate["blockers"]}
    rec_action = ("sell_now" if (proof and fulfillment_complexity == "low") else
                  "package_today" if proof else "validate_first")
    rec = {"cash_wedge_id": "cw_" + uuid.uuid4().hex[:10], "name": wedge_name,
           "offer_type": offer_type if offer_type in OFFER_TYPES else "service", "buyer": buyer,
           "pain": pain, "deliverable": deliverable, "price_range": price_range,
           "time_to_package": time_to_package if time_to_package in TIME_TO_PACKAGE else "72h",
           "fulfillment_complexity": fulfillment_complexity, "proof_available": list(proof),
           "assets_used": [asset_id] if asset_id else [], "risks": [],
           "required_approvals": ["launch", "outreach"], "estimated_margin": "estimate pending",
           "recommended_action": rec_action, "created_at": storage.now()}
    storage.save(name, "rev_wedge_%s" % rec["cash_wedge_id"], rec, store)
    _idx(name, "rev_wedge_index", rec["cash_wedge_id"], store)
    storage.emit_truth(name, "rev_wedge", rec["cash_wedge_id"], "CASH WEDGE: %s (%s)" % (wedge_name, rec_action),
                       actor="vera", store=store)
    return {"ok": True, "cash_wedge": rec}


def rank_wedges(name: str, store: Path | None = None) -> list:
    ws = _list(name, "rev_wedge_index", "rev_wedge_%s", store)
    order = {"sell_now": 0, "package_today": 1, "validate_first": 2, "hold": 3, "kill": 4}
    ws.sort(key=lambda w: (order.get(w["recommended_action"], 5), -len(w["proof_available"])))
    return ws


# ---- 24h offer packager ----
def package_offer(name: str, cash_wedge_id: str, *, promise: str, price: float, timeline: str,
                  limitations: list, inputs_required: list, proof: list, qa_checklist: list,
                  claims: list | None = None, store: Path | None = None) -> dict:
    """Package a full sellable offer. Refused if a claim is unsupported (claim with no proof), or
    without limitations / a QA checklist. Starts as draft — launch requires approval."""
    w = storage.load(name, "rev_wedge_%s" % cash_wedge_id, store, default=None)
    if not w:
        return {"ok": False, "error": "no such cash wedge"}
    if not limitations:
        return {"ok": False, "error": "an offer must state its limitations (no overpromising)"}
    if not qa_checklist:
        return {"ok": False, "error": "an offer needs a QA checklist before sale"}
    if (claims or []) and not proof:
        return {"ok": False, "error": "claims present but no proof — unsupported claim refused"}
    rec = {"offer_id": "rof_" + uuid.uuid4().hex[:10], "cash_wedge_id": cash_wedge_id,
           "offer_name": w["name"], "buyer": w["buyer"], "pain": w["pain"], "promise": promise,
           "deliverable": w["deliverable"], "price": price, "timeline": timeline,
           "limitations": list(limitations), "inputs_required": list(inputs_required),
           "proof": list(proof), "claims": list(claims or []), "qa_checklist": list(qa_checklist),
           "refund_policy": "refund on QA-confirmed defect", "status": "draft",
           "launch_requires_approval": True}
    storage.save(name, "rev_offer_%s" % rec["offer_id"], rec, store)
    return {"ok": True, "offer": rec}


def launch_offer(name: str, offer_id: str, *, approval_ref: str = "", fulfillment_ready: bool = False,
                 store: Path | None = None) -> dict:
    """Launch (publish/sell) an offer. REFUSED without approval AND a ready fulfillment packet."""
    rec = storage.load(name, "rev_offer_%s" % offer_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such offer"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "launching a customer-facing offer requires approval"}
    if not fulfillment_ready:
        return {"ok": False, "error": "cannot launch without a ready fulfillment packet"}
    rec["status"] = "selling"; rec["approval_ref"] = approval_ref
    storage.save(name, "rev_offer_%s" % offer_id, rec, store)
    return {"ok": True, "offer": rec}


# ---- buyer shortlist ----
def add_buyer(name: str, *, company_or_person: str, source: str, pain_hypothesis: str,
              approved_channel: str = "", fit_score: int = 0, store: Path | None = None) -> dict:
    if source in FORBIDDEN_BUYER_SOURCES or source not in APPROVED_BUYER_SOURCES:
        return {"ok": False, "error": "buyer source %r not approved (no spam/scraping/fake)" % source}
    if not (pain_hypothesis or "").strip():
        return {"ok": False, "error": "a buyer needs a pain hypothesis"}
    rec = {"buyer_id": "buy_" + uuid.uuid4().hex[:10], "company_or_person": company_or_person,
           "source": source, "pain_hypothesis": pain_hypothesis, "fit_score": fit_score,
           "approved_channel": approved_channel, "risk": "low",
           "status": "qualified" if fit_score >= 2 else "research"}
    storage.save(name, "rev_buyer_%s" % rec["buyer_id"], rec, store)
    _idx(name, "rev_buyer_index", rec["buyer_id"], store)
    return {"ok": True, "buyer": rec}


def can_contact_buyer(name: str, buyer_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    """Gate for contacting a buyer. Disqualified buyers are never contacted; outreach needs approval."""
    rec = storage.load(name, "rev_buyer_%s" % buyer_id, store, default=None)
    if not rec:
        return {"allowed": False, "reason": "no such buyer"}
    if rec["status"] == "disqualified":
        return {"allowed": False, "reason": "buyer disqualified — do not contact"}
    if not (approval_ref or "").strip():
        return {"allowed": False, "reason": "outreach requires approval", "approval_required": True}
    return {"allowed": True}


# ---- immediate sales sprint ----
def build_sprint(name: str, offer_id: str, *, messages: list, proof_points: list, claims: list,
                 success_criteria: list, kill_criteria: list, send_limit: int = 20,
                 store: Path | None = None) -> dict:
    """Draft a sales sprint. Refused if a claim has no proof, if a message contains spam/fake-urgency,
    or without success/kill criteria. Sending is always approval-gated."""
    if not success_criteria or not kill_criteria:
        return {"ok": False, "error": "a sprint needs success + kill criteria"}
    if claims and not proof_points:
        return {"ok": False, "error": "claims with no proof points — refused"}
    for m in messages:
        if _SPAM.search(m):
            return {"ok": False, "error": "spam/fake-urgency language in a message — refused"}
        if _FAKE.search(m):
            return {"ok": False, "error": "fake social proof in a message — refused"}
    rec = {"sales_sprint_id": "rsp_" + uuid.uuid4().hex[:10], "offer_id": offer_id,
           "messages": list(messages), "proof_points": list(proof_points), "claims": list(claims),
           "success_criteria": list(success_criteria), "kill_criteria": list(kill_criteria),
           "send_limit": send_limit, "followup_limit": 3, "approval_required": True,
           "risk_controls": ["max-touch cap", "opt-out honored", "no fake urgency"], "status": "drafted"}
    storage.save(name, "rev_sprint_%s" % rec["sales_sprint_id"], rec, store)
    return {"ok": True, "sales_sprint": rec}


# ---- fulfillment packet ----
def fulfillment_packet(name: str, offer_id: str, *, customer_inputs: list, workflow_steps: list,
                       qa_checklist: list, delivery_format: str, time_estimate: str,
                       cost_estimate: float, regulated: bool = False, store: Path | None = None) -> dict:
    """A fulfillment packet that must exist before selling. Refused without inputs/workflow/QA/
    delivery format. Regulated work is flagged for professional/human escalation."""
    for field, val in (("customer_inputs", customer_inputs), ("workflow_steps", workflow_steps),
                       ("qa_checklist", qa_checklist)):
        if not val:
            return {"ok": False, "error": "fulfillment packet needs %s" % field}
    if not delivery_format:
        return {"ok": False, "error": "fulfillment packet needs a delivery format"}
    rec = {"fulfillment_id": "rfp_" + uuid.uuid4().hex[:10], "offer_id": offer_id,
           "customer_inputs": list(customer_inputs), "workflow_steps": list(workflow_steps),
           "qa_checklist": list(qa_checklist), "delivery_format": delivery_format,
           "time_estimate": time_estimate, "cost_estimate": cost_estimate,
           "margin_estimate": "estimate (price - cost)",
           "escalation": "regulated work -> professional/human review" if regulated else None,
           "ready": True}
    storage.save(name, "rev_fulfillment_%s" % offer_id, rec, store)
    return {"ok": True, "fulfillment": rec}


# ---- helpers ----
def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def _list(name, idxkey, pattern, store):
    idx = storage.load(name, idxkey, store, default={"ids": []})["ids"]
    return [x for x in (storage.load(name, pattern % i, store, default=None) for i in idx) if x]
