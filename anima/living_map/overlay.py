"""living_map.overlay — Milestone 5: PATTERN OVERLAY. Surface the REAL recurring patterns on the map.

Reads the Pattern Observatory's real patterns (reports/patterns.json) and maps each to the map node(s)
it concerns, so a node that has an open recurring issue carries a badge (count + worst severity) right on
the operational twin. No invented hotspots: a pattern that maps to no known node is surfaced honestly as
'unmapped', never forced onto a node. Read-only; honest empty when there are no patterns.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schema

REPORTS = Path("reports")

# pattern_id / title keyword -> the node it concerns (most specific wins)
_KEYWORD_NODE = [
    ("source", "sources"), ("retriev", "sources"), ("reference", "sources"),
    ("memory", "memory"), ("recall", "memory"), ("fact", "known_facts"),
    ("route", "route_classifier"), ("prompt", "prompt_compiler"),
    ("latency", "model_runtime"), ("model", "model_runtime"), ("token", "model_runtime"),
    ("lerf", "lerf"), ("skill", "lerf"),
    ("intake", "intake"), ("ocr", "ocr"), ("uki", "intake"), ("knowledge", "intake"), ("commit", "intake"),
    ("gate", "final_gate"), ("verify", "final_gate"), ("safety", "final_gate"),
    ("complet", "final_gate"), ("stripped", "final_gate"), ("truncat", "final_gate"),
    ("inject", "context_immune"), ("quarantine", "context_immune"), ("immune", "context_immune"),
    ("identity", "capability_truth"), ("narrative", "capability_truth"),
    ("history", "history"), ("improve", "improvements"),
]
# evidence route -> node (fallback when no keyword matches)
_ROUTE_NODE = {"llm": "model_runtime", "lerf": "lerf", "memory": "memory",
               "reference": "sources", "known_fact": "known_facts"}

_NODE_IDS = {n["node_id"] for n in schema.NODES}
_SEV_RANK = {"P0": 3, "P1": 2, "P2": 1, "P3": 0}


def _read_patterns() -> list:
    try:
        d = json.loads((REPORTS / "patterns.json").read_text())
        return [p for p in (d.get("patterns") or []) if isinstance(p, dict)]
    except Exception:
        return []


def _node_for(p: dict):
    blob = ("%s %s" % (p.get("pattern_id", ""), p.get("title", ""))).lower()
    for kw, node in _KEYWORD_NODE:
        if kw in blob and node in _NODE_IDS:
            return node
    # fallback: dominant evidence route
    routes = {}
    for e in (p.get("evidence") or []):
        r = str((e or {}).get("route") or "")
        if r:
            routes[r] = routes.get(r, 0) + 1
    if routes:
        top = max(routes, key=routes.get)
        node = _ROUTE_NODE.get(top)
        if node in _NODE_IDS:
            return node
    return None


def overlay(name: str = "Vera") -> dict:
    """Map the real recurring patterns onto map nodes. Returns per-node badges (count + worst severity +
    titles) + an honest 'unmapped' bucket. Read-only."""
    patterns = _read_patterns()
    by_node = {}
    unmapped = []
    for p in patterns:
        node = _node_for(p)
        item = {"pattern_id": p.get("pattern_id"), "title": p.get("title"),
                "severity": p.get("severity"), "frequency": p.get("frequency"),
                "recommended_fix": p.get("recommended_fix")}
        if node is None:
            unmapped.append(item)
            continue
        b = by_node.setdefault(node, {"node_id": node, "count": 0, "worst_severity": None, "patterns": []})
        b["count"] += 1
        b["patterns"].append(item)
        if _SEV_RANK.get(p.get("severity"), -1) > _SEV_RANK.get(b["worst_severity"], -1):
            b["worst_severity"] = p.get("severity")

    return {
        "name": name,
        "by_node": by_node,
        "nodes_with_patterns": sorted(by_node.keys()),
        "patterns_total": len(patterns),
        "mapped": sum(b["count"] for b in by_node.values()),
        "unmapped": unmapped,
        "doctrine": "Every badge is a REAL recurring pattern from the Pattern Observatory, mapped to the "
                    "node it concerns. A pattern that maps to no known node is shown as 'unmapped', never "
                    "forced onto a node. Read-only; no invented hotspots.",
        "empty": not patterns,
    }
