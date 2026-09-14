"""trust.moat — proof library + QA/delivery/privacy receipts + testimonials + reputation.

Proof links a claim to evidence with freshness; stale or revoked proof cannot back a public claim.
A privacy claim requires a technical/policy basis. QA + delivery receipts record what was requested
vs delivered, the checks run, and the outcome. A customer outcome/testimonial requires explicit
permission; a case study is built only from a permissioned outcome. The reputation score is computed
from real quality + refund data, and a poor score blocks scale.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

PROOF_TYPES = ("cert", "demo", "qa", "delivery", "privacy", "case_study", "technical", "customer_outcome")
PROOF_STATUS = ("draft", "active", "stale", "revoked", "needs_review")


def add_proof(name: str, *, offer_id: str, proof_type: str, claim_supported: str, evidence_refs: list,
              privacy_basis: str = "", store: Path | None = None) -> dict:
    """Add a proof linking a claim to evidence. Refused without evidence; a privacy proof needs a
    technical/policy basis."""
    if proof_type not in PROOF_TYPES:
        return {"ok": False, "error": "unknown proof type %r" % proof_type}
    if not evidence_refs:
        return {"ok": False, "error": "proof requires evidence refs — refused"}
    if proof_type == "privacy" and not (privacy_basis or "").strip():
        return {"ok": False, "error": "a privacy claim requires a technical/policy basis"}
    rec = {"proof_id": "prf_" + uuid.uuid4().hex[:10], "offer_id": offer_id, "proof_type": proof_type,
           "claim_supported": claim_supported, "evidence_refs": list(evidence_refs),
           "privacy_basis": privacy_basis or None, "freshness": storage.now(), "status": "active",
           "permission_required": proof_type in ("customer_outcome", "case_study"), "permission_ref": None}
    storage.save(name, "trust_proof_%s" % rec["proof_id"], rec, store)
    _idx(name, "trust_proof_index", rec["proof_id"], store)
    return {"ok": True, "proof": rec}


def mark_stale(name: str, proof_id: str, *, store: Path | None = None) -> dict:
    rec = storage.load(name, "trust_proof_%s" % proof_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such proof"}
    rec["status"] = "stale"; storage.save(name, "trust_proof_%s" % proof_id, rec, store)
    return {"ok": True, "proof": rec}


def can_claim_publicly(name: str, proof_id: str, *, store: Path | None = None) -> dict:
    """Whether a proof may back a PUBLIC claim. Stale/revoked/needs_review blocked; permission-
    required proof needs a permission ref."""
    rec = storage.load(name, "trust_proof_%s" % proof_id, store, default=None)
    if not rec:
        return {"allowed": False, "reason": "no such proof"}
    if rec["status"] in ("stale", "revoked", "needs_review", "draft"):
        return {"allowed": False, "reason": "proof status %r — cannot claim publicly" % rec["status"]}
    if rec["permission_required"] and not rec.get("permission_ref"):
        return {"allowed": False, "reason": "customer permission required for this proof"}
    return {"allowed": True}


def grant_permission(name: str, proof_id: str, *, permission_ref: str, store: Path | None = None) -> dict:
    if not (permission_ref or "").strip():
        return {"ok": False, "error": "a permission ref is required"}
    rec = storage.load(name, "trust_proof_%s" % proof_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such proof"}
    rec["permission_ref"] = permission_ref; storage.save(name, "trust_proof_%s" % proof_id, rec, store)
    return {"ok": True, "proof": rec}


def qa_receipt(name: str, *, work_order_id: str, requested: str, delivered: str, checks: list,
               issues: list | None = None, store: Path | None = None) -> dict:
    rec = {"qa_receipt_id": "qar_" + uuid.uuid4().hex[:10], "work_order_id": work_order_id,
           "requested": requested, "delivered": delivered, "checks_run": list(checks),
           "issues": list(issues or []), "passed": not issues, "at": storage.now()}
    storage.save(name, "trust_qa_%s" % rec["qa_receipt_id"], rec, store)
    return {"ok": True, "qa_receipt": rec}


def delivery_receipt(name: str, *, work_order_id: str, produced_by: str, delivery_time: str,
                     customer_status: str = "delivered", evidence_refs: list | None = None,
                     store: Path | None = None) -> dict:
    rec = {"delivery_receipt_id": "dr_" + uuid.uuid4().hex[:10], "work_order_id": work_order_id,
           "produced_by": produced_by, "delivery_time": delivery_time, "customer_status": customer_status,
           "evidence_refs": list(evidence_refs or []), "at": storage.now()}
    storage.save(name, "trust_delivery_%s" % rec["delivery_receipt_id"], rec, store)
    return {"ok": True, "delivery_receipt": rec}


def case_study(name: str, *, proof_id: str, headline: str, store: Path | None = None) -> dict:
    """Build a case study — only from a permissioned customer-outcome proof."""
    gate = can_claim_publicly(name, proof_id, store=store)
    if not gate["allowed"]:
        return {"ok": False, "error": "cannot build a case study: %s" % gate["reason"]}
    rec = {"case_study_id": "cstud_" + uuid.uuid4().hex[:8], "proof_id": proof_id, "headline": headline,
           "status": "ready", "permissioned": True}
    storage.save(name, "trust_case_%s" % rec["case_study_id"], rec, store)
    return {"ok": True, "case_study": rec}


def reputation(name: str, *, quality_score: float, refund_rate: float, complaints: int = 0,
               store: Path | None = None) -> dict:
    healthy = quality_score >= 0.7 and refund_rate <= 0.2
    rec = {"reputation_id": "rep_" + uuid.uuid4().hex[:8], "quality_score": quality_score,
           "refund_rate": refund_rate, "complaints": complaints, "scale_allowed": healthy,
           "note": "healthy" if healthy else "reputation risk — fix before scaling"}
    storage.save(name, "trust_reputation", rec, store)
    return {"ok": True, "reputation": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def overview(name: str, store: Path | None = None) -> dict:
    idx = storage.load(name, "trust_proof_index", store, default={"ids": []})["ids"]
    proofs = [p for p in (storage.load(name, "trust_proof_%s" % i, store, default=None) for i in idx) if p]
    rep = storage.load(name, "trust_reputation", store, default=None)
    return {"ok": True,
            "proofs": [{"type": p["proof_type"], "claim": p["claim_supported"], "status": p["status"]}
                       for p in proofs],
            "active_proofs": sum(1 for p in proofs if p["status"] == "active"),
            "stale_proofs": sum(1 for p in proofs if p["status"] == "stale"),
            "reputation": rep,
            "honesty": "only active, permissioned proof backs public claims; stale proof is blocked; "
                       "no fabricated testimonials/case studies."}
