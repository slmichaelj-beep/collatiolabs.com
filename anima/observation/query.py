"""observation.query — read recent traces + follow a trace to its evidence."""
from __future__ import annotations

from pathlib import Path

from . import store


def recent(name: str, limit: int = 100, store_path: Path | None = None) -> list[dict]:
    return list(reversed(store.load(name, store_path, limit=limit)))


def by_trace(name: str, trace_id: str, store_path: Path | None = None) -> list[dict]:
    return [e for e in store.load(name, store_path) if e.get("trace_id") == trace_id]


def has_evidence(event: dict) -> bool:
    """Does this event link to ANY evidence (truth/decision/approval/budget/action/report/cert)?"""
    return any(event.get(k) for k in ("truth_refs", "decision_refs", "approval_refs",
                                      "budget_refs", "action_refs", "report_refs", "cert_refs"))


def summary(name: str, store_path: Path | None = None) -> dict:
    evs = store.load(name, store_path)
    by_system, by_result = {}, {}
    for e in evs:
        by_system[e.get("system", "?")] = by_system.get(e.get("system", "?"), 0) + 1
        by_result[e.get("result", "?")] = by_result.get(e.get("result", "?"), 0) + 1
    return {"total": len(evs), "by_system": by_system, "by_result": by_result,
            "with_evidence": sum(1 for e in evs if has_evidence(e))}
