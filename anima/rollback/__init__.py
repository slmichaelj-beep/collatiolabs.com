"""anima.rollback — global rollback semantics across every reversible surface.

One record shape + one apply path for: memory correction, forget/retraction, teaching record,
auto-learn draft conversion, knowledge-pack install/rebuild, runtime profile override, and
release-tier classification change. Every rollback records (rollback_id, target_event,
previous_state, new_state, actor, timestamp, reason, truth_ledger_event) and emits a Truth
Ledger event.
"""
from . import apply, schema  # noqa: F401
