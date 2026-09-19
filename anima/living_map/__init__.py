"""living_map — Vera's operational digital twin (the "Living Map").

An animated, interactive, EVIDENCE-BACKED model of how data, memory, sources, models, safety gates,
tools, host resources, patterns, and decisions move through Vera. Read-only / observational by default;
simulation is sandboxed and never mutates live state.

Core principle (enforced by certify_living_map_no_wallpaper.py): every node, edge, status, and pulse is
backed by REAL telemetry / trace / dependency metadata, or is honestly marked `unknown` / `stale`. No
fake animation, no hardcoded green, no decorative flow pretending to be truth.

Milestones: STATIC (real node/edge graph) -> LIVE (real event pulses) -> REPLAY (one turn) ->
SIMULATION (pull a lever, see predicted impact with assumptions+confidence) -> PATTERNS overlay.
"""
from . import schema, graph  # noqa: F401
