"""workforce.execution — work-order factory + fulfillment execution + QA + delivery outcomes.

A work order is created only from an APPROVED (selling) service with customer inputs. Work runs
through steps; customer delivery is BLOCKED before a QA pass; regulated output needs professional
review. Delivery tracks customer status honestly; a testimonial is blocked without permission; and
revenue is recognized ONLY with payment/acceptance evidence (no pipeline counted as revenue).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import fulfillment as _ff

WO_STATUS = ("created", "waiting_for_inputs", "in_progress", "qa", "revision", "delivered",
             "accepted", "refunded", "failed")
QA_CATEGORIES = ("accuracy", "completeness", "format", "source_citation", "customer_instructions",
                 "legal_safety_risk", "brand_quality", "pricing_claim_compliance", "privacy_security",
                 "delivery_readiness")


def create_work_order(name: str, service_id: str, *, customer_id: str, inputs_received: list,
                      price: float, cost_estimate: float = 0.0, deadline: str = "",
                      store: Path | None = None) -> dict:
    """Create a work order from an approved service. Refused if the service isn't selling, or if
    inputs/customer are missing."""
    svc = storage.load(name, "wf_service_%s" % service_id, store, default=None)
    if not svc:
        return {"ok": False, "error": "no such service"}
    if svc["status"] != "selling":
        return {"ok": False, "error": "service is not approved-to-sell — cannot take an order"}
    if not customer_id or not inputs_received:
        return {"ok": False, "error": "a work order needs a customer + inputs"}
    rec = {"work_order_id": "wfo_" + uuid.uuid4().hex[:10], "service_id": service_id,
           "customer_id": customer_id, "inputs_received": list(inputs_received),
           "assigned_team_id": svc["team_id"], "steps": [], "status": "in_progress",
           "deadline": deadline, "price": price, "cost_estimate": cost_estimate,
           "margin_estimate": round(price - cost_estimate, 2),
           "qa_passed": False, "action_refs": [], "truth_refs": [], "observation_refs": []}
    storage.save(name, "wf_order_%s" % rec["work_order_id"], rec, store)
    _idx(name, rec["work_order_id"], store)
    storage.emit_truth(name, "wf_order", rec["work_order_id"], "WORK ORDER for " + customer_id,
                       actor="user", store=store)
    return {"ok": True, "work_order": rec}


def run_qa(name: str, work_order_id: str, *, checks: dict, reviewer: str = "vera",
           regulated: bool = False, store: Path | None = None) -> dict:
    """Run QA. Missing source citations fail a research deliverable; regulated work requires a
    professional reviewer. Sets accepted_for_delivery only on a clean pass."""
    rec = storage.load(name, "wf_order_%s" % work_order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such work order"}
    issues = [k for k, v in checks.items() if k in QA_CATEGORIES and not v]
    result = "pass" if not issues else "needs_revision"
    if "source_citation" in issues:
        result = "fail"
    if regulated and reviewer not in ("professional", "lamar"):
        result = "professional_review_required"; issues.append("regulated output needs professional review")
    qa = {"qa_id": "wqa_" + uuid.uuid4().hex[:10], "work_order_id": work_order_id,
          "checks": {k: bool(v) for k, v in checks.items()}, "result": result, "issues": issues,
          "reviewer": reviewer, "accepted_for_delivery": result == "pass"}
    storage.save(name, "wf_qa_%s" % work_order_id, qa, store)
    if result == "pass":
        rec["qa_passed"] = True; rec["status"] = "qa"; storage.save(name, "wf_order_%s" % work_order_id, rec, store)
    return {"ok": True, "qa": qa}


def deliver(name: str, work_order_id: str, *, deliverable_refs: list, store: Path | None = None) -> dict:
    """Deliver to the customer. BLOCKED until QA has passed."""
    rec = storage.load(name, "wf_order_%s" % work_order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such work order"}
    if not rec.get("qa_passed"):
        return {"ok": False, "error": "delivery blocked — QA has not passed"}
    rec["status"] = "delivered"; rec["deliverable_refs"] = list(deliverable_refs)
    rec["delivered_at"] = storage.now()
    rec["revenue_recognition_status"] = "pending"   # not revenue until paid/accepted
    rec["customer_status"] = "delivered"; rec["testimonial_allowed"] = False
    storage.save(name, "wf_order_%s" % work_order_id, rec, store)
    return {"ok": True, "work_order": rec}


def record_outcome(name: str, work_order_id: str, *, customer_status: str, payment_evidence_ref: str = "",
                   testimonial_permission: bool = False, store: Path | None = None) -> dict:
    """Record the customer outcome. Revenue is recognized ONLY with payment/acceptance evidence;
    a testimonial is allowed only with explicit permission."""
    rec = storage.load(name, "wf_order_%s" % work_order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such work order"}
    rec["customer_status"] = customer_status
    if customer_status == "accepted" and (payment_evidence_ref or "").strip():
        rec["revenue_recognition_status"] = "recognized"; rec["status"] = "accepted"
        rec["payment_evidence_ref"] = payment_evidence_ref
    elif customer_status == "refunded":
        rec["revenue_recognition_status"] = "refunded"; rec["status"] = "refunded"
    else:
        rec["revenue_recognition_status"] = "not_revenue"
    rec["testimonial_allowed"] = bool(testimonial_permission)
    storage.save(name, "wf_order_%s" % work_order_id, rec, store)
    return {"ok": True, "work_order": rec}


def _idx(name, wid, store):
    idx = storage.load(name, "wf_order_index", store, default={"ids": []}); idx["ids"].append(wid)
    storage.save(name, "wf_order_index", idx, store)


def list_orders(name, store=None) -> list:
    idx = storage.load(name, "wf_order_index", store, default={"ids": []})["ids"]
    return [o for o in (storage.load(name, "wf_order_%s" % i, store, default=None) for i in idx) if o]
