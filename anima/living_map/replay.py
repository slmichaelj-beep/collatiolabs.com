"""living_map.replay — Milestone 3: REPLAY. Scrub back through what actually happened.

Where M2 streams the newest pulses live, M3 reconstructs the map's history as a seekable, CHRONOLOGICAL
timeline built from the same real trace (MRI turns + SOC catches). Every frame is a real event with its
evidence reference; seeking to a position deterministically reconstructs which nodes were lit at that
moment from the recorded trace. No synthetic frames; idle == an honest empty timeline.
"""
from __future__ import annotations

from collections import Counter

from . import events, schema

_NODE_IDS = {n["node_id"] for n in schema.NODES}
_TRAIL = 3   # how many trailing events count as "still lit" at a playhead (deterministic window)


def timeline(name: str = "Vera", limit: int = 300) -> list:
    """The REAL events in CHRONOLOGICAL (oldest-first) playback order. Read-only."""
    evs = events.recent_events(name, limit)
    return sorted(evs, key=lambda x: (x.get("timestamp") or 0, x.get("seq", 0)))


def active_at(frames: list, index: int) -> list:
    """Deterministically reconstruct which nodes were lit at playhead `index`: the node of the event at
    that index plus the trailing window. Pure function of the recorded trace — same input, same output."""
    if not frames:
        return []
    i = max(0, min(int(index), len(frames) - 1))
    lo = max(0, i - _TRAIL + 1)
    seen = []
    for e in frames[lo:i + 1]:
        n = e.get("node_id")
        if n in _NODE_IDS and n not in seen:
            seen.append(n)
    return seen


def replay(name: str = "Vera", limit: int = 300) -> dict:
    """The /founder/living-map/replay payload: a chronological, seekable timeline of real events with
    per-node activity over the window. Honest empty when nothing has happened."""
    frames = timeline(name, limit)
    ts = [e.get("timestamp") for e in frames if e.get("timestamp")]
    activity = Counter(e.get("node_id") for e in frames if e.get("node_id") in _NODE_IDS)
    # group frames into turns (a turn = one trace_id) so the scrubber can show turn boundaries
    turns = []
    for e in frames:
        tid = e.get("trace_id")
        if tid and (not turns or turns[-1]["trace_id"] != tid):
            turns.append({"trace_id": tid, "at": e.get("timestamp"), "start_index": frames.index(e)})
    return {
        "name": name,
        "frames": frames,
        "count": len(frames),
        "span_from": min(ts) if ts else None,
        "span_to": max(ts) if ts else None,
        "node_activity": dict(activity),
        "busiest_node": (activity.most_common(1)[0][0] if activity else None),
        "turns": turns,
        "empty": not frames,
        "doctrine": "Replay reconstructs the map's history from the SAME real trace the live view streams "
                    "(MRI turns + SOC catches), in chronological order. Seeking is a deterministic function "
                    "of the recorded events — no synthetic frames, no invented motion.",
    }
