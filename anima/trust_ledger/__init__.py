"""trust_ledger — the unified Trust Ledger (Human Operating Layer, Layer 8).

A read-only, categorised, provenance-linked spine over the REAL trust events Vera already records
(incident.security_events.jsonl + the ROI ledger), plus the trust INVARIANTS that must hold. It
creates no new source of truth; it makes the existing one accountable in one place.
"""
from . import schema, ledger  # noqa: F401
