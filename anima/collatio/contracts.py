"""collatio.contracts — contract / customer-commitment registry + professional review queue.

Vera tracks obligations and drafts. Vera never signs a contract, never makes a customer commitment
without approval, never promises support/SLA without a capacity check, and never treats a legal
interpretation as final without professional review. The professional-review queue packages
materials + questions for an attorney/CPA/patent attorney; sending requires approval.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from .entity import ENTITY_ID

CONTRACT_TYPES = ("customer", "vendor", "employment", "contractor", "software_license", "NDA",
                  "SOW", "support", "data_processing")
CONTRACT_STATUS = ("draft", "review_needed", "approval_needed", "signed", "active", "expired", "terminated")
REVIEW_TYPES = ("legal", "tax", "accounting", "patent", "trademark", "contract", "compliance", "insurance")


def _all(name, store): return storage.load(name, "collatio_contracts", store, default={"contracts": []})["contracts"]
def _save(name, a, store): storage.save(name, "collatio_contracts", {"contracts": a}, store)


def draft_contract(name: str, *, counterparty: str, contract_type: str, obligations: list | None = None,
                   payment_terms: str = "", support_terms: str = "", store: Path | None = None) -> dict:
    if contract_type not in CONTRACT_TYPES:
        return {"ok": False, "error": "unknown contract type %r" % contract_type}
    rec = {"contract_id": "ct_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID,
           "counterparty": counterparty, "contract_type": contract_type, "status": "draft",
           "obligations": list(obligations or []), "payment_terms": payment_terms,
           "support_terms": support_terms, "professional_review_required": True,
           "approval_ref": None, "truth_refs": [], "record_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    return {"ok": True, "contract": rec}


def sign_action(name: str, contract_id: str, *, approval_ref: str = "",
                professional_review_ref: str = "", store: Path | None = None) -> dict:
    """Attempt to sign. REFUSED — signing is human-only. (We record only that a human signed.)"""
    if not (approval_ref and professional_review_ref):
        return {"ok": False, "error": "signing needs approval + professional review — and Vera never signs"}
    a = _all(name, store)
    for r in a:
        if r["contract_id"] == contract_id:
            r["status"] = "signed"; r["approval_ref"] = approval_ref; _save(name, a, store)
            return {"ok": True, "contract": r, "note": "recorded as signed by human; Vera did not sign"}
    return {"ok": False, "error": "no such contract"}


def customer_commitment(name: str, *, summary: str, approval_ref: str = "", capacity_ok: bool = False,
                        store: Path | None = None) -> dict:
    """Make a customer commitment. REFUSED without approval AND a capacity check (no overpromising)."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "a customer commitment requires approval"}
    if not capacity_ok:
        return {"ok": False, "error": "a support/SLA promise requires a capacity check first"}
    return {"ok": True, "commitment": {"summary": summary, "approval_ref": approval_ref}}


def contracts(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "contracts": a,
            "approval_needed": [r["counterparty"] for r in a if r["status"] == "approval_needed"]}


# ---- professional review queue ----
def review_packet(name: str, *, review_type: str, title: str, summary: str, questions: list,
                  materials: list | None = None, urgency: str = "medium", store: Path | None = None) -> dict:
    if review_type not in REVIEW_TYPES:
        return {"ok": False, "error": "unknown review type %r" % review_type}
    if not questions:
        return {"ok": False, "error": "a review packet must list questions"}
    rec = {"review_id": "rev_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID, "review_type": review_type,
           "title": title, "summary": summary, "materials": list(materials or []),
           "questions": list(questions), "urgency": urgency, "status": "ready_for_lamar",
           "approval_ref": None, "truth_refs": []}
    storage.save(name, "collatio_review_%s" % rec["review_id"], rec, store)
    storage.emit_truth(name, "collatio_review", rec["review_id"], "REVIEW packet: " + title,
                       actor="vera", store=store)
    return {"ok": True, "review": rec}


def send_review(name: str, review_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    """Send a review packet to a professional. REFUSED without approval (external action)."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "sending to a professional requires approval"}
    rec = storage.load(name, "collatio_review_%s" % review_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such review"}
    rec["status"] = "sent_to_professional"; rec["approval_ref"] = approval_ref
    storage.save(name, "collatio_review_%s" % review_id, rec, store)
    return {"ok": True, "review": rec}
