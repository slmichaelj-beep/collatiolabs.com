"""teams.quality — QA/review/acceptance + performance + escalation + product-support builder.

No deliverable is accepted without review. Legal/financial/professional deliverables escalate to a
professional or Lamar; customer-facing deliverables are claim/proof-checked. Performance flags
overdue/poor work and can recommend pause/replace. Escalation routes high-risk items (legal,
financial, security, budget overrun) to the board briefing + human review. The product-support
builder requires a triage policy, an escalation path, and a capacity-checked support promise.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

REVIEW_TYPES = ("technical", "commercial", "legal_professional", "brand", "security",
                "support_quality", "customer_promise", "financial")
RESULTS = ("accepted", "rejected", "needs_revision", "escalated")
_ESCALATE_TYPES = ("legal_professional", "financial")
ESCALATION_TRIGGERS = ("legal_risk", "financial_risk", "customer_anger", "security_issue",
                       "missed_deadline", "budget_overrun", "quality_failure", "support_overload",
                       "deal_at_risk", "vendor_failure")


def review(name: str, *, work_order_id: str, review_type: str, criteria: list, passed: bool,
           customer_facing: bool = False, claim_proof_ok: bool = True, reviewer: str = "vera",
           store: Path | None = None) -> dict:
    if review_type not in REVIEW_TYPES:
        return {"ok": False, "error": "unknown review type %r" % review_type}
    issues = []
    result = "accepted" if passed else "needs_revision"
    if review_type in _ESCALATE_TYPES and reviewer not in ("professional", "lamar"):
        result = "escalated"; issues.append("legal/financial work must be reviewed by a professional or Lamar")
    if customer_facing and not claim_proof_ok:
        result = "rejected"; issues.append("customer-facing claim lacks proof")
    rec = {"qa_id": "qa_" + uuid.uuid4().hex[:10], "work_order_id": work_order_id,
           "review_type": review_type, "criteria": list(criteria), "result": result,
           "issues": issues, "reviewer": reviewer,
           "accepted_for_delivery": result == "accepted", "evidence_refs": []}
    storage.save(name, "team_qa_%s" % rec["qa_id"], rec, store)
    return {"ok": True, "review": rec}


def performance(name: str, *, role_id: str, period: str, completed: int, overdue: int,
                quality_pass_rate: float, cost: float = 0.0, store: Path | None = None) -> dict:
    if overdue > completed or quality_pass_rate < 0.6:
        rec_action = "coach" if quality_pass_rate >= 0.4 else "replace"
    elif overdue > 0:
        rec_action = "coach"
    else:
        rec_action = "continue"
    rec = {"performance_id": "perf_" + uuid.uuid4().hex[:8], "role_id": role_id, "period": period,
           "completed": completed, "overdue": overdue, "quality_pass_rate": quality_pass_rate,
           "cost": cost, "issues": (["low quality"] if quality_pass_rate < 0.6 else []),
           "recommendation": rec_action}
    storage.save(name, "team_perf_%s" % rec["performance_id"], rec, store)
    return {"ok": True, "performance": rec}


def escalate(name: str, *, trigger: str, summary: str, store: Path | None = None) -> dict:
    if trigger not in ESCALATION_TRIGGERS:
        return {"ok": False, "error": "unknown escalation trigger %r" % trigger}
    high = trigger in ("legal_risk", "financial_risk", "security_issue", "budget_overrun")
    rec = {"escalation_id": "esc_" + uuid.uuid4().hex[:10], "trigger": trigger, "summary": summary,
           "severity": "high" if high else "medium",
           "requires_human_review": high, "board_visible": high,
           "blocks_spend": trigger == "budget_overrun"}
    storage.save(name, "team_escalation_%s" % rec["escalation_id"], rec, store)
    storage.emit_truth(name, "team_escalation", rec["escalation_id"], "ESCALATION: %s" % trigger,
                       actor="vera", risk="high" if high else "low", store=store)
    return {"ok": True, "escalation": rec}


def build_support_org(name: str, *, product_id: str, triage_policy: str, escalation_path: str,
                      support_promise: str, capacity_ok: bool, response_templates: list | None = None,
                      templates_approved: bool = False, store: Path | None = None) -> dict:
    """Build a product support org. Refused without triage + escalation; the support promise must be
    capacity-checked; customer response templates are approval-gated."""
    if not (triage_policy and escalation_path):
        return {"ok": False, "error": "support org needs a triage policy + escalation path"}
    if not capacity_ok:
        return {"ok": False, "error": "a support promise requires a capacity check"}
    if (response_templates or []) and not templates_approved:
        return {"ok": False, "error": "customer response templates require approval before use"}
    rec = {"support_org_id": "sup_" + uuid.uuid4().hex[:10], "product_id": product_id,
           "triage_policy": triage_policy, "escalation_path": escalation_path,
           "support_promise": support_promise, "capacity_checked": True,
           "response_templates": list(response_templates or [])}
    storage.save(name, "team_support_%s" % rec["support_org_id"], rec, store)
    return {"ok": True, "support_org": rec}
