"""observation.schema — the universal observation event contract."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

ACTORS = ("user", "vera", "system", "cert", "rover")
RESULTS = ("success", "blocked", "failed", "partial", "deferred")
CLASSIFICATIONS = ("real", "deferred", "not_claimed", "future_tier", "blocked", "unknown_invalid")
SYSTEMS = ("foundry", "sales", "company", "learning", "truth", "host", "commercial",
           "company_operator", "observation", "verification")

REQUIRED = ("trace_id", "event_id", "timestamp", "surface", "system", "action", "actor",
            "authority_level", "governance_state", "truth_refs", "decision_refs", "approval_refs",
            "budget_refs", "action_refs", "report_refs", "cert_refs", "result", "classification")


def new_trace() -> str:
    return "tr_" + uuid.uuid4().hex[:12]


def new_event() -> str:
    return "ob_" + uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(surface: str, system: str, action: str, *, actor: str = "user",
         authority_level: str = "L0", governance_state: dict | None = None,
         truth_refs=None, decision_refs=None, approval_refs=None, budget_refs=None,
         action_refs=None, report_refs=None, cert_refs=None, result: str = "success",
         classification: str = "real", trace_id: str | None = None) -> dict:
    ev = {
        "trace_id": trace_id or new_trace(),
        "event_id": new_event(),
        "timestamp": now(),
        "surface": surface,
        "system": system if system in SYSTEMS else "observation",
        "action": action,
        "actor": actor if actor in ACTORS else "system",
        "authority_level": authority_level,
        "governance_state": governance_state or {},
        "truth_refs": list(truth_refs or []),
        "decision_refs": list(decision_refs or []),
        "approval_refs": list(approval_refs or []),
        "budget_refs": list(budget_refs or []),
        "action_refs": list(action_refs or []),
        "report_refs": list(report_refs or []),
        "cert_refs": list(cert_refs or []),
        "result": result if result in RESULTS else "success",
        "classification": classification if classification in CLASSIFICATIONS else "real",
    }
    problems = validate(ev)
    if problems:
        raise ValueError("invalid observation event: " + "; ".join(problems))
    return ev


def validate(ev: dict) -> list[str]:
    p = []
    if not isinstance(ev, dict):
        return ["not a dict"]
    for k in REQUIRED:
        if k not in ev:
            p.append("missing %r" % k)
    if p:
        return p
    if ev["actor"] not in ACTORS:
        p.append("bad actor")
    if ev["result"] not in RESULTS:
        p.append("bad result")
    if ev["classification"] not in CLASSIFICATIONS:
        p.append("bad classification")
    if not isinstance(ev["governance_state"], dict):
        p.append("governance_state must be a dict")
    return p
