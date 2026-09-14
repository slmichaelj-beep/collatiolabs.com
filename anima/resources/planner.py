"""resources.planner — resource monitor + bottleneck detector + request packets + multi-host plans.

The monitor records resource status with a business-impact link. The bottleneck detector flags
red/amber resources and ties them to blocked revenue. A resource request is procurement-ready: it
must carry a business case, bottleneck evidence, and minimum/recommended/premium options — and is
always approval-gated (Vera never buys/provisions/spends). Multi-host plans are security-scoped:
default data access is restricted, and a host needs trust setup + certs before it joins.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

RESOURCE_TYPES = ("cpu", "gpu", "ram", "disk", "network", "api", "storage", "human", "professional",
                  "browser", "model")
STATUS = ("green", "amber", "red", "unknown")
REQUEST_TYPES = ("hardware", "host", "cloud", "storage", "api_budget", "software_subscription",
                 "human", "professional")
HOST_PURPOSES = ("primary", "worker", "model", "browser", "storage", "backup", "monitoring", "cloud_burst")


def record_status(name: str, *, host_id: str, resource_type: str, current_usage: str, capacity: str,
                  status: str, bottleneck_for: list | None = None, business_impact: str = "",
                  store: Path | None = None) -> dict:
    if resource_type not in RESOURCE_TYPES:
        return {"ok": False, "error": "unknown resource type %r" % resource_type}
    rec = {"resource_status_id": "rs_" + uuid.uuid4().hex[:10], "host_id": host_id,
           "resource_type": resource_type, "current_usage": current_usage, "capacity": capacity,
           "status": status if status in STATUS else "unknown", "bottleneck_for": list(bottleneck_for or []),
           "business_impact": business_impact,
           "recommended_action": _action_for(status, resource_type)}
    storage.save(name, "res_status_%s_%s" % (host_id, resource_type), rec, store)
    _idx(name, "res_status_index", "%s_%s" % (host_id, resource_type), store)
    return {"ok": True, "status": rec}


def _action_for(status, rtype):
    if status not in ("amber", "red"):
        return "none"
    return {"disk": "buy_storage", "storage": "buy_storage", "api": "approve_api_budget",
            "human": "hire", "professional": "hire", "gpu": "buy_hardware", "ram": "buy_hardware",
            "cpu": "add_host", "model": "add_host", "browser": "add_host"}.get(rtype, "optimize")


def detect_bottlenecks(name: str, store: Path | None = None) -> dict:
    idx = storage.load(name, "res_status_index", store, default={"ids": []})["ids"]
    statuses = [s for s in (storage.load(name, "res_status_%s" % i, store, default=None) for i in idx) if s]
    bottlenecks = [s for s in statuses if s["status"] in ("amber", "red")]
    return {"ok": True, "total_monitored": len(statuses),
            "bottlenecks": [{"host": b["host_id"], "resource": b["resource_type"], "status": b["status"],
                             "blocks": b["bottleneck_for"], "action": b["recommended_action"]}
                            for b in bottlenecks],
            "blocked_revenue": sorted({x for b in bottlenecks for x in b["bottleneck_for"]})}


def resource_request(name: str, *, request_type: str, title: str, problem: str, business_case: str,
                     options: list, recommended_option: str, bottleneck_evidence_refs: list | None = None,
                     store: Path | None = None) -> dict:
    """Build a procurement-ready resource request. Refused without a business case and >=2 options
    (so a minimum vs recommended choice exists). ALWAYS approval-gated — Vera never purchases."""
    if request_type not in REQUEST_TYPES:
        return {"ok": False, "error": "unknown request type %r" % request_type}
    if not (business_case or "").strip():
        return {"ok": False, "error": "a resource request needs a business case (no vague requests)"}
    if len(options) < 2:
        return {"ok": False, "error": "a request needs >=2 options (minimum vs recommended)"}
    for o in options:
        if "estimated_cost" not in o or "option_name" not in o:
            return {"ok": False, "error": "each option needs an option_name + estimated_cost"}
    rec = {"resource_request_id": "rr_" + uuid.uuid4().hex[:10], "request_type": request_type, "title": title,
           "problem": problem, "business_case": business_case,
           "bottleneck_evidence_refs": list(bottleneck_evidence_refs or []), "options": list(options),
           "recommended_option": recommended_option, "approval_required": True, "budget_ref": None,
           "status": "ready_for_lamar", "vera_can_purchase": False}
    storage.save(name, "res_request_%s" % rec["resource_request_id"], rec, store)
    _idx(name, "res_request_index", rec["resource_request_id"], store)
    storage.emit_truth(name, "res_request", rec["resource_request_id"], "RESOURCE REQUEST: " + title,
                       actor="vera", store=store)
    return {"ok": True, "request": rec}


def purchase(name: str, resource_request_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    """Mark a request purchased. REFUSED without approval — Vera never spends on its own."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "purchase requires human approval — Vera does not buy"}
    rec = storage.load(name, "res_request_%s" % resource_request_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such request"}
    rec["status"] = "approved"; rec["budget_ref"] = approval_ref
    storage.save(name, "res_request_%s" % resource_request_id, rec, store)
    return {"ok": True, "request": rec, "note": "approved by human; provisioning is a human action"}


def host_plan(name: str, *, plan_name: str, purpose: str, connection_method: str = "local_network",
              data_access_scope: str = "restricted", security_policy: str = "", store: Path | None = None) -> dict:
    """Plan a new host. Refused if it claims full data access by default or lacks a security policy.
    No host joins without trust setup + certs."""
    if purpose not in HOST_PURPOSES:
        return {"ok": False, "error": "unknown host purpose %r" % purpose}
    if data_access_scope == "full":
        return {"ok": False, "error": "no host gets full data access by default — scope it"}
    if not (security_policy or "").strip():
        return {"ok": False, "error": "a host plan needs a security policy"}
    rec = {"host_plan_id": "hp_" + uuid.uuid4().hex[:10], "name": plan_name, "purpose": purpose,
           "connection_method": connection_method, "data_access_scope": data_access_scope,
           "security_policy": security_policy, "approval_required": True,
           "setup_steps": ["trust setup", "security review", "observe", "certify"],
           "certs_required": ["certify_host_registry"]}
    storage.save(name, "res_hostplan_%s" % rec["host_plan_id"], rec, store)
    return {"ok": True, "host_plan": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []})
    if item_id not in idx["ids"]:
        idx["ids"].append(item_id); storage.save(name, idxkey, idx, store)


def requests(name, store=None) -> list:
    idx = storage.load(name, "res_request_index", store, default={"ids": []})["ids"]
    return [r for r in (storage.load(name, "res_request_%s" % i, store, default=None) for i in idx) if r]
