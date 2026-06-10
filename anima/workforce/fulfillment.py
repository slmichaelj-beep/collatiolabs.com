"""workforce.fulfillment — workflow designer + digital workforce builder + service catalog.

Vera designs HOW the work gets done before selling it: a fulfillment workflow (inputs, steps, QA
checks, delivery format, failure modes) is required before any offer. The workforce builder assembles
the team (no team without a workflow; paid roles need budget; agents can't bypass authority). The
service catalog turns a gap into a sellable product — but a service cannot be sold without a
fulfillment workflow + a team, and selling is approval-gated.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage


def design_workflow(name: str, work_gap_id: str, *, inputs_required: list, steps: list,
                    qa_checks: list, delivery_format: str, turnaround_time: str,
                    failure_modes: list, agents_required: list | None = None,
                    professional_review_required: bool = False, store: Path | None = None) -> dict:
    """Design a fulfillment workflow. Refused without inputs, steps, QA checks, delivery format,
    and failure modes."""
    for field, val in (("inputs_required", inputs_required), ("steps", steps), ("qa_checks", qa_checks),
                       ("failure_modes", failure_modes)):
        if not val:
            return {"ok": False, "error": "workflow needs %s" % field}
    if not (delivery_format and turnaround_time):
        return {"ok": False, "error": "workflow needs a delivery format + turnaround time"}
    rec = {"workflow_id": "wkf_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id,
           "inputs_required": list(inputs_required), "steps": list(steps), "qa_checks": list(qa_checks),
           "delivery_format": delivery_format, "turnaround_time": turnaround_time,
           "failure_modes": list(failure_modes), "agents_required": list(agents_required or []),
           "human_review_required": bool(agents_required is None),
           "professional_review_required": professional_review_required,
           "revision_policy": "one revision included", "refund_policy": "refund if QA-confirmed defect"}
    storage.save(name, "wf_workflow_%s" % work_gap_id, rec, store)
    return {"ok": True, "workflow": rec}


def build_workforce(name: str, work_gap_id: str, *, team_name: str, roles: list,
                    budget_ref: str = "", is_paid: bool = False, qa_policy_ref: str = "",
                    store: Path | None = None) -> dict:
    """Assemble the workforce team. Refused without a workflow; paid teams need a budget; a team
    can't be active without a QA policy."""
    wf = storage.load(name, "wf_workflow_%s" % work_gap_id, store, default=None)
    if not wf:
        return {"ok": False, "error": "no fulfillment workflow — cannot build a team yet"}
    if is_paid and not budget_ref:
        return {"ok": False, "error": "a paid team requires a budget"}
    if not qa_policy_ref:
        return {"ok": False, "error": "a team cannot be active without a QA policy"}
    rec = {"workforce_team_id": "wft_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id,
           "team_name": team_name, "roles": list(roles), "workflow_id": wf["workflow_id"],
           "authority_policy_ref": "collatio.authority", "budget_ref": budget_ref,
           "quality_policy_ref": qa_policy_ref, "capacity_estimate": "TBD", "status": "approved"}
    storage.save(name, "wf_team_%s" % work_gap_id, rec, store)
    return {"ok": True, "team": rec}


def add_service(name: str, work_gap_id: str, *, service_name: str, buyer: str, promise: str,
                deliverable: str, price: float, turnaround_time: str, limitations: list,
                store: Path | None = None) -> dict:
    """Add a sellable service. Refused without a fulfillment workflow + a team. Starts as draft;
    selling requires approval."""
    wf = storage.load(name, "wf_workflow_%s" % work_gap_id, store, default=None)
    team = storage.load(name, "wf_team_%s" % work_gap_id, store, default=None)
    if not wf or not team:
        return {"ok": False, "error": "a service needs a fulfillment workflow + a team first"}
    if not limitations:
        return {"ok": False, "error": "a service must state its limitations (no overpromising)"}
    rec = {"service_id": "svc_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id,
           "name": service_name, "buyer": buyer, "promise": promise, "deliverable": deliverable,
           "price": price, "turnaround_time": turnaround_time, "limitations": list(limitations),
           "revision_policy": wf["revision_policy"], "refund_policy": wf["refund_policy"],
           "fulfillment_workflow_id": wf["workflow_id"], "team_id": team["workforce_team_id"],
           "approval_required_before_sale": True, "status": "draft"}
    storage.save(name, "wf_service_%s" % rec["service_id"], rec, store)
    storage.save(name, "wf_service_for_%s" % work_gap_id, {"service_id": rec["service_id"]}, store)
    _idx(name, rec["service_id"], store)
    storage.emit_truth(name, "wf_service", rec["service_id"], "SERVICE drafted: " + service_name,
                       actor="vera", store=store)
    return {"ok": True, "service": rec}


def approve_service(name: str, service_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "selling a service requires approval"}
    rec = storage.load(name, "wf_service_%s" % service_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such service"}
    rec["status"] = "selling"; rec["approval_ref"] = approval_ref
    storage.save(name, "wf_service_%s" % service_id, rec, store)
    return {"ok": True, "service": rec}


def _idx(name, sid, store):
    idx = storage.load(name, "wf_service_index", store, default={"ids": []}); idx["ids"].append(sid)
    storage.save(name, "wf_service_index", idx, store)


def list_services(name, store=None) -> list:
    idx = storage.load(name, "wf_service_index", store, default={"ids": []})["ids"]
    return [s for s in (storage.load(name, "wf_service_%s" % i, store, default=None) for i in idx) if s]
