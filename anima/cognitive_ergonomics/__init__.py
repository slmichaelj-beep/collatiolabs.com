"""cognitive_ergonomics — Layer 5 of the Human Operating Layer.

Deterministic clarity metrics over Vera\047s OWN replies: jargon, readability, hedging, unexplained
acronyms, and cognitive load. Measures real text against real, reproducible scorers — no model in the
loop — and explains every issue human-level (what it means -> what to do).
"""
from . import lexicon, metrics, analyzer  # noqa: F401
