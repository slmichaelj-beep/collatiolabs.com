"""teams.delegation — delegation packets + work orders + agent teams + vendors.

A delegation needs context, deliverables, and success criteria; external delegation needs approval;
paid delegation needs budget; regulated delegation needs professional review. Work orders carry a
mandatory review step. Agent teams cannot send external messages, spend, or file legal/tax actions;
their output is draft until reviewed. Vendor hiring needs approval + budget + (for paid) a contract.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

WO_STATUS = ("draft", "approved", "assigned", "in_progress", "review", "done", "rejected", "blocked")
AGENT_FORBIDDEN = ("send_external_message", "spend", "file_legal", "file_tax", "sign_contract")


def delegate(name: str, *, role_id: str, task: str, objective: str, deliverables: list,
             success_criteria: list, context_refs: list | None = None, deadline: str = "",
             budget_ref: str = "", is_external: bool = False, is_paid: bool = False,
             is_regulated: bool = False, approval_ref: str = "", professional_review_ref: str = "",
             store: Path | None = None) -> dict:
    if not deliverables:
        return {"ok": False, "error": "no delegation without deliverables"}
    if not success_criteria:
        return {"ok": False, "error": "no delegation without success criteria"}
    if not (context_refs or []):
        return {"ok": False, "error": "no delegation without context"}
    if is_external and not approval_ref:
        return {"ok": False, "error": "external delegation requires approval"}
    if is_paid and not budget_ref:
        return {"ok": False, "error": "paid delegation requires budget"}
    if is_regulated and not professional_review_ref:
        return {"ok": False, "error": "regulated delegation requires professional review"}
    rec = {"delegation_id": "del_" + uuid.uuid4().hex[:10], "role_id": role_id, "task": task,
           "objective": objective, "deliverables": list(deliverables),
           "success_criteria": list(success_criteria), "context_refs": list(context_refs or []),
           "deadline": deadline, "budget_ref": budget_ref, "approval_ref": approval_ref or None,
           "review_required": True, "status": "approved" if (not is_external or approval_ref) else "draft"}
    storage.save(name, "team_delegation_%s" % rec["delegation_id"], rec, store)
    storage.emit_truth(name, "team_delegation", rec["delegation_id"], "DELEGATE: " + task,
                       actor="user", store=store)
    return {"ok": True, "delegation": rec}


def create_work_order(name: str, *, org_id: str, role_id: str, title: str, description: str,
                      deliverables: list, priority: str = "medium", budget_ref: str = "",
                      store: Path | None = None) -> dict:
    if not deliverables:
        return {"ok": False, "error": "a work order needs deliverables"}
    rec = {"work_order_id": "wo_" + uuid.uuid4().hex[:10], "org_id": org_id, "role_id": role_id,
           "title": title, "description": description, "priority": priority, "status": "draft",
           "dependencies": [], "deliverables": list(deliverables), "budget_ref": budget_ref,
           "approval_ref": None, "review_required": True, "action_refs": [], "quality_refs": [],
           "truth_refs": [], "observation_refs": []}
    storage.save(name, "team_wo_%s" % rec["work_order_id"], rec, store)
    return {"ok": True, "work_order": rec}


def complete_work_order(name: str, work_order_id: str, *, qa_passed: bool = False,
                        deliverable_ref: str = "", store: Path | None = None) -> dict:
    """Mark a work order done. REFUSED without a QA pass and a deliverable/evidence ref."""
    rec = storage.load(name, "team_wo_%s" % work_order_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such work order"}
    if not qa_passed:
        return {"ok": False, "error": "work order cannot be done without a QA pass"}
    if not (deliverable_ref or "").strip():
        return {"ok": False, "error": "done requires a deliverable/evidence ref"}
    rec["status"] = "done"; rec["deliverable_ref"] = deliverable_ref
    storage.save(name, "team_wo_%s" % work_order_id, rec, store)
    return {"ok": True, "work_order": rec}


def create_agent_team(name: str, *, org_id: str, mission: str, agents: list, allowed_tools: list,
                      output_review_policy: str = "vera_review", store: Path | None = None) -> dict:
    rec = {"agent_team_id": "at_" + uuid.uuid4().hex[:10], "org_id": org_id, "mission": mission,
           "agents": list(agents), "allowed_tools": list(allowed_tools),
           "forbidden_tools": list(AGENT_FORBIDDEN), "context_refs": [],
           "output_review_policy": output_review_policy, "status": "active",
           "authority_note": "agents cannot bypass authority, send external, spend, or file legal/tax"}
    storage.save(name, "team_agentteam_%s" % rec["agent_team_id"], rec, store)
    return {"ok": True, "agent_team": rec}


def agent_can(name: str, action: str) -> dict:
    """An agent action gate — forbidden categories are hard-blocked regardless of context."""
    if action in AGENT_FORBIDDEN:
        return {"allowed": False, "reason": "agents cannot %s — escalate to a human" % action}
    return {"allowed": True, "note": "output is draft until reviewed"}


def hire_vendor(name: str, *, vendor_name: str, category: str, is_paid: bool = True,
                approval_ref: str = "", budget_ref: str = "", store: Path | None = None) -> dict:
    """Hire/engage a vendor. REFUSED without approval; paid work refused without budget."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "hiring/contacting a vendor requires approval"}
    if is_paid and not (budget_ref or "").strip():
        return {"ok": False, "error": "paid vendor work requires budget"}
    rec = {"vendor_id": "ven_" + uuid.uuid4().hex[:10], "name": vendor_name, "category": category,
           "status": "approved", "risk_level": "regulated" if category in ("attorney", "CPA", "bookkeeper") else "low",
           "contract_required": True, "budget_ref": budget_ref, "approval_ref": approval_ref}
    storage.save(name, "team_vendor_%s" % rec["vendor_id"], rec, store)
    storage.emit_truth(name, "team_vendor", rec["vendor_id"], "VENDOR engaged (approved): " + vendor_name,
                       actor="user", store=store)
    return {"ok": True, "vendor": rec}
