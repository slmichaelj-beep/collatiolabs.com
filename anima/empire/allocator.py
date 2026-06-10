"""empire.allocator — revenue-priority scheduler + capital allocator + workforce allocator.

The scheduler prioritizes work that makes money — but security/legal emergencies and self-healing
critical faults outrank revenue, and paid customer deadlines outrank speculative research. The
capital allocator spends nothing without approval, funds winners on evidence, kills losers, protects
a reserve, and ties hardware spend to a business case. The workforce allocator assigns agents/humans/
hosts by margin + deadline + capacity, flagging overloaded teams and blocked work.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

# higher number = higher priority
_PRIORITY = {
    "security_incident": 100, "legal_deadline": 95, "self_heal_critical": 90,
    "paid_customer_delivery": 80, "cash_collection": 70, "sales_followup": 60,
    "approved_revenue_experiment": 55, "high_margin_fulfillment": 50, "qa_for_deliverable": 45,
    "opportunity_research": 20, "low_value_maintenance": 5,
}
CAPITAL_TARGETS = ("hardware", "cloud_api", "sales_experiments", "automation", "productization",
                   "hiring", "professional_review", "support_qa", "distribution", "partnerships", "cash_reserve")


def schedule(name: str, *, tasks: list, under_load: bool = False, store: Path | None = None) -> dict:
    """Order tasks by priority. tasks: [{id, kind}]. Security/legal/self-heal override revenue;
    low-value work is deferred under load."""
    ranked = sorted(tasks, key=lambda t: -_PRIORITY.get(t.get("kind"), 10))
    deferred = []
    if under_load:
        deferred = [t for t in ranked if _PRIORITY.get(t.get("kind"), 10) <= 20]
        ranked = [t for t in ranked if _PRIORITY.get(t.get("kind"), 10) > 20]
    rec = {"schedule_id": "sch_" + uuid.uuid4().hex[:8], "ordered": [t.get("id") for t in ranked],
           "ordered_kinds": [t.get("kind") for t in ranked], "deferred": [t.get("id") for t in deferred],
           "top": ranked[0]["kind"] if ranked else None}
    storage.save(name, "emp_schedule", rec, store)
    return {"ok": True, "schedule": rec}


def allocate_capital(name: str, *, period: str, available_budget: float, target: str, amount: float,
                     evidence_present: bool = False, approval_ref: str = "", reserve_pct: float = 0.2,
                     business_case: str = "", store: Path | None = None) -> dict:
    """Allocate capital to a target. No spend without approval; winners need evidence; hardware needs
    a business case; the reserve is protected."""
    if target not in CAPITAL_TARGETS:
        return {"ok": False, "error": "unknown capital target %r" % target}
    if amount > 0 and not (approval_ref or "").strip():
        return {"ok": False, "error": "capital allocation requires approval"}
    if target in ("automation", "productization", "hiring", "sales_experiments") and not evidence_present:
        return {"ok": False, "error": "funding this target requires evidence (fund winners, not hope)"}
    if target == "hardware" and not (business_case or "").strip():
        return {"ok": False, "error": "hardware spend must tie to a business case"}
    if amount > available_budget * (1 - reserve_pct):
        return {"ok": False, "error": "allocation would breach the protected cash reserve"}
    rec = {"capital_decision_id": "cap_" + uuid.uuid4().hex[:10], "period": period, "target": target,
           "amount": amount, "available_budget": available_budget, "reserve_pct": reserve_pct,
           "approval_ref": approval_ref, "evidence_present": evidence_present}
    storage.save(name, "emp_capital_%s" % rec["capital_decision_id"], rec, store)
    _idx(name, "emp_capital_index", rec["capital_decision_id"], store)
    storage.emit_truth(name, "emp_capital", rec["capital_decision_id"], "CAPITAL %s $%s" % (target, amount),
                       actor="user", store=store)
    return {"ok": True, "capital_decision": rec}


def allocate_workforce(name: str, *, workstream_id: str, assignee: str, host_id: str,
                       team_capacity_ok: bool, store: Path | None = None) -> dict:
    """Assign a workstream to an assignee + host. An overloaded team is flagged + the work blocked."""
    if not team_capacity_ok:
        return {"ok": False, "error": "team over capacity — work blocked until capacity frees", "blocked": True}
    rec = {"assignment_id": "wfa_" + uuid.uuid4().hex[:8], "workstream_id": workstream_id,
           "assignee": assignee, "host_id": host_id, "status": "assigned"}
    storage.save(name, "emp_assign_%s" % workstream_id, rec, store)
    return {"ok": True, "assignment": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)
