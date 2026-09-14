"""marketplaces.fiverr.fulfillment — fulfillment cells + order intake + delivery QA + messaging.

Each active gig maps to a fulfillment cell (roles + workflow + QA checklist + delivery template).
Orders can't start without requirements and never solicit unnecessary sensitive data or off-platform
payment. Delivery is BLOCKED until QA passes; unsupported claims / missing requirements / regulated
advice fail or escalate. Messaging allows inbound responses but blocks mass messaging, review
manipulation, and off-platform payment solicitation; sending is approval-gated.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage

ORDER_STATUS = ("new", "waiting_requirements", "in_progress", "qa", "delivered", "revision", "complete", "cancelled")
QA_CHECKS = ("scope_match", "requirements_satisfied", "accuracy", "format", "evidence_support",
             "no_unsupported_roi", "no_regulated_advice", "no_private_data_exposure", "complete")
_OFF_PLATFORM = re.compile(r"(?i)\b(paypal|venmo|zelle|cash app|wire|bank transfer|whatsapp|telegram|"
                           r"my email|email me at|pay (me )?directly|off[- ]?fiverr)\b")
_REVIEW_PRESSURE = re.compile(r"(?i)\b(leave (me )?a (5|five)[- ]?star|positive review|please review|rate me)\b")


def build_cell(name: str, *, gig_id: str, roles: list, qa_checklist: list, delivery_template: str,
               capacity_per_day: int = 0, human_review_required: bool = False, store: Path | None = None) -> dict:
    if not roles or not qa_checklist or not delivery_template:
        return {"ok": False, "error": "a cell needs roles + a QA checklist + a delivery template"}
    rec = {"cell_id": "fcell_" + uuid.uuid4().hex[:8], "gig_id": gig_id, "roles": list(roles),
           "qa_checklist": list(qa_checklist), "delivery_template": delivery_template,
           "revision_policy": "one revision included", "capacity_per_day": capacity_per_day,
           "human_review_required": human_review_required}
    storage.save(name, "fiverr_cell_%s" % gig_id, rec, store)
    return {"ok": True, "cell": rec}


def intake_order(name: str, *, gig_id: str, buyer_handle: str, package: str, price: float,
                 requirements_received: list, store: Path | None = None) -> dict:
    """Intake an order. Work can't begin without requirements (status waits)."""
    cell = storage.load(name, "fiverr_cell_%s" % gig_id, store, default=None)
    if not cell:
        return {"ok": False, "error": "no fulfillment cell for this gig — build one first"}
    fee = round(price * 0.20, 2)   # Fiverr ~20% seller fee (estimate, labeled)
    rec = {"order_id": "ford_" + uuid.uuid4().hex[:10], "gig_id": gig_id, "buyer_handle": buyer_handle,
           "package": package, "price": float(price), "platform_fee_estimate": fee,
           "net_revenue_estimate": round(price - fee, 2), "requirements_received": list(requirements_received),
           "missing_requirements": [], "risk_level": "low",
           "status": "in_progress" if requirements_received else "waiting_requirements",
           "qa_passed": False}
    storage.save(name, "fiverr_order_%s" % rec["order_id"], rec, store)
    _idx(name, "fiverr_order_index", rec["order_id"], store)
    storage.emit_truth(name, "fiverr_order", rec["order_id"], "ORDER intake %s (%s)" % (buyer_handle, package),
                       actor="user", store=store)
    return {"ok": True, "order": rec}


def run_qa(name: str, order_id: str, *, checks: dict, reviewer: str = "vera", regulated: bool = False,
           store: Path | None = None) -> dict:
    rec = storage.load(name, "fiverr_order_%s" % order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such order"}
    if rec["status"] == "waiting_requirements":
        return {"ok": False, "error": "missing requirements — cannot QA/deliver"}
    issues = [k for k in QA_CHECKS if not checks.get(k, False)]
    result = "pass" if not issues else "fail"
    if regulated and reviewer not in ("professional", "lamar"):
        result = "professional_review_required"; issues.append("regulated advice needs professional review")
    qa = {"qa_id": "fqa_" + uuid.uuid4().hex[:8], "order_id": order_id, "result": result, "issues": issues,
          "reviewer": reviewer, "accepted_for_delivery": result == "pass"}
    storage.save(name, "fiverr_qa_%s" % order_id, qa, store)
    if result == "pass":
        rec["qa_passed"] = True; rec["status"] = "qa"; storage.save(name, "fiverr_order_%s" % order_id, rec, store)
    return {"ok": True, "qa": qa}


def deliver(name: str, order_id: str, *, deliverable_refs: list, store: Path | None = None) -> dict:
    """Deliver to the buyer — BLOCKED until QA passes."""
    rec = storage.load(name, "fiverr_order_%s" % order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such order"}
    if not rec.get("qa_passed"):
        return {"ok": False, "error": "delivery blocked — QA has not passed"}
    rec["status"] = "delivered"; rec["deliverable_refs"] = list(deliverable_refs)
    storage.save(name, "fiverr_order_%s" % order_id, rec, store)
    return {"ok": True, "order": rec}


def draft_message(name: str, *, context: str, recipient: str, draft: str, mass: bool = False,
                  store: Path | None = None) -> dict:
    """Draft a Fiverr message. Mass messaging, review pressure, and off-platform payment solicitation
    are refused. Sending is human-approved."""
    if mass:
        return {"ok": False, "error": "mass/unsolicited messaging is forbidden"}
    if _REVIEW_PRESSURE.search(draft):
        return {"ok": False, "error": "review-manipulation language is forbidden"}
    if _OFF_PLATFORM.search(draft):
        return {"ok": False, "error": "off-platform payment/contact solicitation is forbidden"}
    rec = {"message_id": "fmsg_" + uuid.uuid4().hex[:10], "context": context, "recipient": recipient,
           "draft": draft, "policy_check": "pass", "approval_required": True, "status": "draft"}
    storage.save(name, "fiverr_msg_%s" % rec["message_id"], rec, store)
    return {"ok": True, "message": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def orders(name, store=None) -> list:
    idx = storage.load(name, "fiverr_order_index", store, default={"ids": []})["ids"]
    return [o for o in (storage.load(name, "fiverr_order_%s" % i, store, default=None) for i in idx) if o]
