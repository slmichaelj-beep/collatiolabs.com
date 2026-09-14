"""company_operator.legal_ip — legal/compliance coordinator + patent/IP prep.

Vera prepares checklists, drafts, and attorney/counsel handoff packets. Vera is NOT counsel,
cannot sign contracts, and cannot file legal/IP documents — filings are blocked and routed to a
human/professional. Every legal artifact carries its review requirement.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

LEGAL_AREAS = ("entity_formation", "business_license", "tax_registration", "trademark",
               "patent", "privacy_policy", "terms_of_service", "contract", "employment",
               "data_protection", "industry_regulation")
ACTION_LEVELS = ("draft_only", "attorney_review_required", "founder_approval_required",
                 "filing_blocked")


def legal_checklist(name: str, jurisdiction: str, areas=None, *, store: Path | None = None) -> dict:
    if not jurisdiction:
        return {"ok": False, "error": "jurisdiction required before a legal checklist"}
    items = []
    for area in (areas or LEGAL_AREAS):
        a = area if area in LEGAL_AREAS else "industry_regulation"
        lvl = ("filing_blocked" if a in ("entity_formation", "tax_registration", "trademark", "patent")
               else "attorney_review_required" if a in ("contract", "employment", "privacy_policy",
                                                         "terms_of_service", "data_protection")
               else "draft_only")
        items.append({"area": a, "action_level": lvl,
                      "note": "Vera prepares; %s" % lvl.replace("_", " ")})
    rec = {"checklist_id": "lc_" + uuid.uuid4().hex[:12], "jurisdiction": jurisdiction,
           "items": items, "disclaimer": "Vera is not legal counsel. Nothing here is filed or "
                                         "signed by Vera.", "created_at": storage.now()}
    storage.save(name, "legal_checklist", rec, store)
    storage.emit_truth(name, "legal", rec["checklist_id"], "LEGAL checklist (%s)" % jurisdiction,
                       actor="vera", store=store)
    return {"ok": True, "checklist": rec}


def can_file(name: str, area: str) -> dict:
    """Vera can NEVER file — always returns blocked."""
    return {"allowed": False, "reason": "legal/IP filings are human/professional-only — Vera "
                                        "prepares the packet, a person files it"}


def can_sign_contract(name: str) -> dict:
    return {"allowed": False, "reason": "Vera cannot sign contracts — founder/human signature only"}


def invention_disclosure(name: str, title: str, *, problem: str = "", mechanism: str = "",
                         description: str = "", embodiments=None, store: Path | None = None) -> dict:
    rec = {"disclosure_id": "inv_" + uuid.uuid4().hex[:12], "title": title,
           "problem_solved": problem, "novel_mechanism": mechanism,
           "technical_description": description, "alternative_embodiments": embodiments or [],
           "diagrams_needed": ["system overview", "data flow"],
           "prior_art_search_packet": "(prepared for attorney)",
           "claim_brainstorm": [], "patentability": "UNCERTAIN — attorney must assess",
           "attorney_handoff": "ready", "filing_status": "blocked_pending_human",
           "created_at": storage.now()}
    storage.save(name, "invention_%s" % rec["disclosure_id"], rec, store)
    storage.emit_truth(name, "ip", rec["disclosure_id"], "INVENTION disclosure: " + title[:140],
                       actor="vera", store=store)
    return {"ok": True, "disclosure": rec}
