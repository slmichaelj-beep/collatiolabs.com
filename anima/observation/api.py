"""observation.api — server-facing surface for the observation layer."""
from __future__ import annotations

from . import query, emit


def serve_recent(name: str, limit: int = 100) -> dict:
    return {"ok": True, "events": query.recent(name, limit), "summary": query.summary(name)}


def serve_trace(name: str, trace_id: str) -> dict:
    chain = query.by_trace(name, trace_id)
    return {"ok": True, "trace_id": trace_id, "events": chain,
            "evidence_linked": any(query.has_evidence(e) for e in chain)}
