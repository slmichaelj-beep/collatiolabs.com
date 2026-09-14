"""sales_mastery.core — buyer psychology + ICP/lead sourcing + qualification + discovery.

Sales is a core, governed responsibility. Vera understands WHY a buyer buys before reaching out;
sources leads only from approved channels (never scraping/spam); qualifies before pitching; and
runs real discovery. No outreach without buyer pain defined; disqualified leads are not contacted.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage

FIT = ("low", "medium", "high")
LEAD_NEXT = ("research", "draft_outreach", "disqualify", "ask_founder", "nurture")
# sources that are never acceptable (spam infra / abuse)
_BAD_SOURCES = re.compile(r"\b(?:scraped list|purchased list|spam list|bot[- ]?harvest|"
                          r"unlawful scrap|email append vendor)\b", re.I)
APPROVED_SOURCES = ("founder_provided", "inbound_website", "referral", "event", "approved_research",
                    "existing_customer", "approved_crm_import", "community_optin")


def buyer_psychology(name, offer_id, *, persona, economic_pain="", emotional_pain="",
                     current_alternative="", cost_of_inaction="", desired_outcome="",
                     objections=None, proof_needed=None, decision_makers=None,
                     store: Path | None = None) -> dict:
    rec = {"offer_id": offer_id, "buyer_persona": persona, "economic_pain": economic_pain,
           "emotional_pain": emotional_pain, "current_alternative": current_alternative,
           "cost_of_inaction": cost_of_inaction, "desired_outcome": desired_outcome,
           "objections": objections or [], "proof_needed": proof_needed or [],
           "decision_makers": decision_makers or [], "created_at": storage.now()}
    storage.save(name, "sales_buyer_%s" % offer_id, rec, store)
    return {"ok": True, "buyer_psychology": rec}


def outreach_ready(name, offer_id, *, store: Path | None = None) -> dict:
    """Outreach is blocked until buyer pain is defined (no blind pitching)."""
    bp = storage.load(name, "sales_buyer_%s" % offer_id, store, default=None)
    if not bp or not bp.get("economic_pain"):
        return {"ready": False, "reason": "define the buyer's economic pain before any outreach"}
    return {"ready": True}


def add_lead(name, offer_id, *, source, company="", contact="", store: Path | None = None) -> dict:
    if source not in APPROVED_SOURCES or _BAD_SOURCES.search(source):
        return {"ok": False, "error": "lead source %r is not an approved source (no scraping/spam)" % source}
    rec = {"lead_id": "lead_" + uuid.uuid4().hex[:12], "offer_id": offer_id, "source": source,
           "company": company, "contact": contact, "fit_score": 0, "pain_fit": "unknown",
           "budget_fit": "unknown", "authority_fit": "unknown", "timing": "unknown",
           "status": "new", "next_action": "research", "created_at": storage.now()}
    leads = storage.load(name, "sales_leads", store, default={"leads": []})["leads"]
    leads.append(rec)
    storage.save(name, "sales_leads", {"leads": leads}, store)
    return {"ok": True, "lead": rec}


def qualify(name, lead_id, *, pain_fit="low", budget_fit="unknown", authority_fit="unknown",
            timing="unknown", store: Path | None = None) -> dict:
    leads = storage.load(name, "sales_leads", store, default={"leads": []})["leads"]
    rec = next((l for l in leads if l["lead_id"] == lead_id), None)
    if rec is None:
        return {"ok": False, "error": "no such lead"}
    score = sum({"low": 0, "medium": 1, "high": 2}.get(x, 0)
                for x in (pain_fit, budget_fit, authority_fit))
    rec.update({"pain_fit": pain_fit, "budget_fit": budget_fit, "authority_fit": authority_fit,
                "timing": timing, "fit_score": score})
    if pain_fit == "low":
        rec["status"], rec["next_action"] = "disqualified", "disqualify"
    elif "unknown" in (budget_fit, authority_fit) or timing == "unknown":
        rec["status"], rec["next_action"] = "needs_research", "research"
    else:
        rec["status"], rec["next_action"] = "qualified", "draft_outreach"
    storage.save(name, "sales_leads", {"leads": leads}, store)
    return {"ok": True, "lead": rec}


def can_contact(name, lead_id, *, store: Path | None = None) -> dict:
    leads = storage.load(name, "sales_leads", store, default={"leads": []})["leads"]
    rec = next((l for l in leads if l["lead_id"] == lead_id), None)
    if rec is None:
        return {"allowed": False, "reason": "no such lead"}
    if rec["status"] == "disqualified":
        return {"allowed": False, "reason": "lead is disqualified — do not contact"}
    if rec["status"] != "qualified":
        return {"allowed": False, "reason": "lead not yet qualified — research first"}
    return {"allowed": True}


def discovery_plan(name, opportunity_id, *, store: Path | None = None) -> dict:
    rec = {"opportunity_id": opportunity_id,
           "objectives": ["confirm pain", "confirm buyer", "confirm budget", "confirm timeline",
                          "confirm decision process", "confirm success criteria", "next step"],
           "question_types": ["situation", "problem", "impact", "cost_of_inaction",
                              "decision_process", "success_criteria", "budget", "timeline"],
           "qualification": "needs_more_discovery", "created_at": storage.now()}
    storage.save(name, "sales_discovery_%s" % opportunity_id, rec, store)
    return {"ok": True, "discovery": rec}


def discovery_complete(name, opportunity_id, *, pain_confirmed, budget_status="unknown",
                       timeline="unknown", store: Path | None = None) -> dict:
    rec = storage.load(name, "sales_discovery_%s" % opportunity_id, store, default={})
    qualified = bool(pain_confirmed) and budget_status != "unknown" and timeline != "unknown"
    rec.update({"pain_confirmed": bool(pain_confirmed), "budget_status": budget_status,
                "timeline": timeline,
                "qualification": "qualified" if qualified else "needs_more_discovery"})
    storage.save(name, "sales_discovery_%s" % opportunity_id, rec, store)
    return {"ok": True, "discovery": rec, "advances": qualified}
