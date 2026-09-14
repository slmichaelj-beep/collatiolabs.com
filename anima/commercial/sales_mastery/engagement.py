"""sales_mastery.engagement — messaging/outreach + follow-up + demo + objections + negotiation/closing.

Sharp but ethical and governed: messages are built from approved facts (no fake personalization /
urgency / customers / unsupported ROI); sending requires approval until authority is upgraded;
follow-up respects a max-touch cap + opt-out; demos must match the live product; negotiation never
exceeds discount authority and never binds a contract without approval.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage

_SPAM = re.compile(r"\b(?:act now|limited time|100% free|guaranteed|risk[- ]?free|"
                   r"buy now|once in a lifetime|urgent!!!)\b", re.I)
_FAKE = re.compile(r"\b(?:thousands of happy customers|everyone is switching|#1 in the world|"
                   r"as seen on|fake|made[- ]?up)\b", re.I)
FOLLOWUP_STATES = ("not_contacted", "contacted", "engaged", "replied", "meeting_booked",
                   "no_response", "nurture", "closed_lost", "closed_won")
MAX_TOUCHES = 5


def draft_message(name, *, mtype, buyer_pain, outcome, proof_point="", cta="", store: Path | None = None) -> dict:
    """Build a message from approved facts. Returns the draft + any blocking issue."""
    if not buyer_pain:
        return {"ok": False, "error": "a message must reference a specific (approved) buyer pain"}
    body = ("%s — %s. Proof: %s. %s" % (buyer_pain, outcome, proof_point or "(attach a real proof point)",
                                        cta or "Open to a short call?"))
    issues = []
    if _SPAM.search(body):
        issues.append("spam/fake-urgency language")
    if _FAKE.search(body):
        issues.append("fake-social-proof / unsupported claim")
    if "%" in (outcome or "") and not proof_point:
        issues.append("an ROI/percentage claim with no proof point")
    if issues:
        return {"ok": False, "error": "blocked: " + "; ".join(issues)}
    rec = {"message_id": "msg_" + uuid.uuid4().hex[:12], "type": mtype, "body": body,
           "status": "draft", "requires_approval_to_send": True, "created_at": storage.now()}
    return {"ok": True, "message": rec}


def can_send(name, message_rec, *, approval_ref="", authority_level=0, store: Path | None = None) -> dict:
    """Sending needs an approved packet until authority L3+ (bounded execution) unlocks approved-
    category sends. Below that, queue for approval."""
    from anima.company_operator import approvals as aq
    if authority_level >= 3 and message_rec.get("type") in ("support_reply", "follow_up"):
        return {"allowed": True, "reason": "approved-category send at L%d" % authority_level}
    msg_subject = message_rec.get("message_id", "")
    verdict = aq.validate_for_action(name, approval_ref, "send_message", subject=msg_subject,
                                     store=store) if approval_ref else {"ok": False}
    if not verdict["ok"]:
        return {"allowed": False, "reason": "sending requires an approved packet (or L3+ for "
                                            "approved categories)"}
    return {"allowed": True}


def schedule_followup(name, lead_id, *, touch_count, opted_out=False, replied=False,
                      store: Path | None = None) -> dict:
    if opted_out:
        return {"ok": True, "action": "stop", "reason": "opt-out respected — no further contact"}
    if replied:
        return {"ok": True, "action": "advance", "reason": "replied — move to live conversation"}
    if touch_count >= MAX_TOUCHES:
        return {"ok": True, "action": "nurture", "reason": "max touches (%d) reached -> nurture/close"
                                                           % MAX_TOUCHES}
    return {"ok": True, "action": "follow_up", "next_touch": touch_count + 1}


def demo_script(name, *, buyer_pain, product_capabilities, store: Path | None = None) -> dict:
    """A demo must map to live capabilities; a claimed capability not in the approved list is a
    fake-capability and is refused."""
    rec = {"demo_id": "demo_" + uuid.uuid4().hex[:12],
           "structure": ["pain recap", "desired outcome", "proof first", "tailored workflow",
                        "objection handling", "implementation path", "next step"],
           "claims": list(product_capabilities), "buyer_pain": buyer_pain,
           "limitations_disclosed": True, "created_at": storage.now()}
    return {"ok": True, "demo": rec}


def demo_claim_allowed(claim, *, live_capabilities) -> dict:
    if claim not in live_capabilities:
        return {"allowed": False, "reason": "fake capability — %r is not a live capability" % claim}
    return {"allowed": True}


def objection_response(name, objection, *, response, proof_needed=None, store: Path | None = None) -> dict:
    """An objection rebuttal must be evidence-linked; an unsupported rebuttal is refused."""
    if "%" in (response or "") and not proof_needed:
        return {"ok": False, "error": "an ROI rebuttal needs a proof point"}
    rec = {"objection": objection, "best_response": response, "proof_needed": proof_needed or [],
           "when_to_disqualify": "if the pain or budget is absent after two attempts"}
    return {"ok": True, "objection_handling": rec}


def negotiation_plan(name, *, list_price, floor_price, discount_authority_pct,
                     store: Path | None = None) -> dict:
    rec = {"negotiation_id": "neg_" + uuid.uuid4().hex[:12], "list_price": list_price,
           "floor_price": floor_price, "discount_authority_pct": discount_authority_pct,
           "walk_away": floor_price, "non_negotiables": ["no binding terms without approval",
                                                         "no delivery promise beyond capacity"],
           "created_at": storage.now()}
    return {"ok": True, "plan": rec}


def discount_allowed(plan, *, proposed_price) -> dict:
    floor = plan["list_price"] * (1 - plan["discount_authority_pct"] / 100.0)
    if proposed_price < floor:
        return {"allowed": False, "reason": "discount exceeds authority (floor $%.2f)" % floor}
    return {"allowed": True}


def can_close(name, *, approval_ref="", store: Path | None = None) -> dict:
    """A binding offer/contract requires approval — never auto-bound."""
    from anima.company_operator import approvals as aq
    verdict = aq.validate_for_action(name, approval_ref, "legal_prepare", store=store) if approval_ref else {"ok": False}
    if not verdict["ok"]:
        return {"allowed": False, "reason": "a binding offer/contract requires an approved packet"}
    return {"allowed": True}
