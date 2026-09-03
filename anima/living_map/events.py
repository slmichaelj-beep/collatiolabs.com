"""living_map.events — Milestone 2: REAL recent events for the Live-Flow animation.

The map animates ONLY what actually happened. Every event is derived from a real trace — a turn in the
MRI (Vera.mri.jsonl) or a security event in the SOC trail — mapped to a real edge/node with a timestamp
and an EVIDENCE reference back to its source. No synthetic pulses; if nothing has happened, the event
list is empty (the UI shows an honest "no recent activity", never a fake heartbeat).

recent_events(name, limit) -> a time-ordered (newest-first) list of edge-pulse events. Read-only.
"""
from __future__ import annotations

import json

from . import schema

# Which MRI stage means the turn reached which node (only emit a pulse for a stage that actually ran).
_STAGE_NODE = {
    "perception": "chat_ui", "heart": "chat_ui", "route": "route_classifier",
    "bind": "known_facts", "situation": "memory", "meaning": "memory",
    "prompt": "prompt_compiler", "generate": "model_runtime", "verify": "final_gate",
    "capture": "memory", "curiosity": "memory",
}
# The canonical turn PATH as (edge_id, from, to) — emitted as pulses for the stages a turn ran.
_TURN_PATH = [
    ("user_to_chat", "user", "chat_ui", "perception"),
    ("chat_to_route", "chat_ui", "route_classifier", "route"),
    ("route_to_immune", "route_classifier", "context_immune", "route"),
    ("memory_to_prompt", "memory", "prompt_compiler", "prompt"),
    ("prompt_to_model", "prompt_compiler", "model_runtime", "generate"),
    ("model_to_gate", "model_runtime", "final_gate", "verify"),
    ("gate_to_chat", "final_gate", "chat_ui", "verify"),
]
# security event route -> the node that caught it
_SEC_NODE = {"output": "final_gate", "source": "sources", "context": "context_immune",
             "conversation": "context_immune", "attribution": "context_immune"}

_EDGE_IDS = {e["edge_id"] for e in schema.EDGES}


def _recent_mri(name: str, n: int) -> list:
    try:
        from anima.server import STORE as _S
        lines = [ln for ln in (_S / f"{name}.mri.jsonl").read_text().splitlines() if ln.strip()]
        out = []
        for ln in lines[-int(n):]:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
        return out
    except Exception:
        return []


def recent_events(name: str = "Vera", limit: int = 60) -> list:
    """Time-ordered (newest-first) REAL events for the Live-Flow animation. Each event maps to a real
    edge + carries an evidence ref (mri_ref turn_id, or security_event_ref). Honest [] when idle."""
    events = []

    # ---- 1. TURN events from the MRI (each recent turn pulses along the path stages it ran) -------
    for t in _recent_mri(name, 12):
        ts = t.get("at")
        tid = t.get("turn_id") or ""
        stages = {s.get("stage") for s in (t.get("stages") or [])}
        total_ms = t.get("total_ms")
        for i, (eid, frm, to, need_stage) in enumerate(_TURN_PATH):
            if need_stage not in stages and need_stage not in ("perception",):
                continue
            if eid not in _EDGE_IDS:
                continue
            events.append({
                "event_id": "turn:%s:%s" % (tid[:12], eid),
                "trace_id": tid, "turn_id": tid,
                # fractional offset so a single turn's pulses are ordered within the turn
                "timestamp": ts, "seq": i,
                "node_id": to, "edge_id": eid, "from": frm, "to": to,
                "event_type": "exited" if eid == "gate_to_chat" else "entered",
                "summary": "turn flowed %s -> %s" % (frm, to),
                "metrics": ({"latency_ms": round(total_ms)} if (eid == "model_to_gate" and total_ms) else {}),
                "evidence": {"mri_ref": tid},
            })

    # ---- 2. SECURITY events from the SOC trail (catches pulse on the node that caught them) -------
    try:
        from anima import incident
        import datetime as _dt
        for e in incident.recent_events(40):
            if e.get("kind") not in ("quarantine", "lockdown", "restore"):
                continue
            node = _SEC_NODE.get(e.get("route"), "security")
            # parse the iso 'at' to an epoch for ordering with turn timestamps (guarded)
            ts = None
            try:
                ts = _dt.datetime.fromisoformat(e.get("at")).timestamp()
            except Exception:
                ts = None
            events.append({
                "event_id": "sec:%s:%s" % (e.get("at", ""), node),
                "trace_id": None, "turn_id": None,
                "timestamp": ts, "seq": 0,
                "node_id": node, "edge_id": "gate_to_security" if node == "final_gate" else "immune_to_security",
                "from": node, "to": "security",
                "event_type": "quarantined" if e.get("kind") == "quarantine" else e.get("kind"),
                "summary": e.get("detail") or e.get("kind"),
                "metrics": {"markers": len(e.get("markers") or [])} if e.get("markers") else {},
                "evidence": {"security_event_ref": e.get("at"), "route": e.get("route")},
            })
    except Exception:
        pass

    # newest first; events with no timestamp sink to the end (honest — undated)
    events.sort(key=lambda x: (x.get("timestamp") or 0, x.get("seq", 0)), reverse=True)
    return events[:int(max(1, limit))]


def events_payload(name: str = "Vera", limit: int = 60) -> dict:
    """The /founder/living-map/events response: the real event list + an honest empty flag."""
    evs = recent_events(name, limit)
    return {
        "name": name,
        "events": evs,
        "count": len(evs),
        "empty": not evs,
        "doctrine": "Every pulse is a real turn (MRI) or security catch (SOC trail), mapped to a real "
                    "edge with an evidence reference. No synthetic animation; idle == no pulses.",
    }
