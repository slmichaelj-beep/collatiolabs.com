"""empire.registry — host registry + workload router.

Every host is registered with a security status + data-access scope. An uncertified host can never
receive sensitive data; a cloud host can't get private data without approval. The workload router
places tasks by privacy sensitivity, urgency, and requirement: private/sensitive tasks stay on a
certified approved host; a cloud route for private data is blocked without approval; professional-
review work routes to the human/professional queue. Every routing decision is logged.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

HOST_ROLES = ("primary", "worker", "model", "browser", "storage", "backup", "cloud", "human_queue")
SECURITY = ("unknown", "certified", "needs_review", "blocked")
DATA_SCOPE = ("none", "limited", "restricted", "full")


def register_host(name: str, *, host_name: str, role: str, capabilities: list | None = None,
                  data_access_scope: str = "restricted", security_status: str = "unknown",
                  store: Path | None = None) -> dict:
    if role not in HOST_ROLES:
        return {"ok": False, "error": "unknown host role %r" % role}
    rec = {"host_id": "host_" + uuid.uuid4().hex[:10], "name": host_name, "role": role,
           "status": "approved" if security_status == "certified" else "planned",
           "capabilities": list(capabilities or []), "resource_profile": {},
           "data_access_scope": data_access_scope if data_access_scope in DATA_SCOPE else "restricted",
           "security_status": security_status if security_status in SECURITY else "unknown",
           "last_health_check": storage.now(), "cert_refs": [], "observation_refs": []}
    storage.save(name, "emp_host_%s" % rec["host_id"], rec, store)
    _idx(name, "emp_host_index", rec["host_id"], store)
    storage.emit_truth(name, "emp_host", rec["host_id"], "HOST registered: %s (%s)" % (host_name, role),
                       actor="user", store=store)
    return {"ok": True, "host": rec}


def certify_host(name: str, host_id: str, *, cert_ref: str, store: Path | None = None) -> dict:
    rec = storage.load(name, "emp_host_%s" % host_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such host"}
    rec["security_status"] = "certified"; rec["status"] = "active"; rec["cert_refs"].append(cert_ref)
    storage.save(name, "emp_host_%s" % host_id, rec, store)
    return {"ok": True, "host": rec}


def route_task(name: str, *, task_kind: str, sensitivity: str, host_id: str, urgent: bool = False,
               cloud_approval_ref: str = "", store: Path | None = None) -> dict:
    """Route a task to a host. Sensitive tasks need a certified host; private data on a cloud host
    needs approval; professional-review work routes to the human queue regardless of host."""
    host = storage.load(name, "emp_host_%s" % host_id, store, default=None)
    if not host:
        return {"allowed": False, "reason": "no such host"}
    if task_kind == "professional_review" and host["role"] != "human_queue":
        return {"allowed": False, "reason": "professional review must route to the human/professional queue",
                "reroute_to": "human_queue"}
    if sensitivity in ("private", "sensitive", "restricted"):
        if host["security_status"] != "certified":
            return {"allowed": False, "reason": "sensitive task requires a certified host"}
        if host["role"] == "cloud" and not (cloud_approval_ref or "").strip():
            return {"allowed": False, "reason": "private data on a cloud host requires approval"}
    rec = {"routing_id": "rt_" + uuid.uuid4().hex[:8], "task_kind": task_kind, "sensitivity": sensitivity,
           "host_id": host_id, "urgent": urgent, "decision": "routed", "at": storage.now()}
    storage.save(name, "emp_routing_%s" % rec["routing_id"], rec, store)
    storage.emit_truth(name, "emp_routing", rec["routing_id"], "ROUTE %s -> %s" % (task_kind, host["name"]),
                       actor="vera", store=store)
    return {"allowed": True, "routing": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def hosts(name, store=None) -> list:
    idx = storage.load(name, "emp_host_index", store, default={"ids": []})["ids"]
    return [h for h in (storage.load(name, "emp_host_%s" % i, store, default=None) for i in idx) if h]
