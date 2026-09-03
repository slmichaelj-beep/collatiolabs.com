"""anima.truth — the Truth Ledger: every claim Vera makes is traceable to provenance.

Append-only per-creature ledger (.anima/<name>.truth.jsonl). See schema (the bounded event),
ledger (append/load), query (fold -> current truth, trace -> provenance chain), supersession
(corrections/retractions as chain links), api (the organ hooks), memory_language (unsupported
memory claims are blocked or rewritten — never shipped).
"""
from . import api, ledger, memory_language, query, schema, supersession  # noqa: F401
