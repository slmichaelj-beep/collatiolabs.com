"""anima.observation — the universal observation layer for the operator/foundry/sales product.

Every meaningful operator action emits a trace-linked observation event (schema.make) into an
append-only per-creature store (.anima/<name>.observation.jsonl). Events carry the live governance
state (authority level, external/spending/legal/kill) and references to truth/decision/approval/
budget/action/report/cert evidence, so any UI claim can be followed to its proof. The /observation
surface renders recent traces. Read-only/observational — emitting never mutates governed state.
"""
from . import api, emit, query, schema, store  # noqa: F401
