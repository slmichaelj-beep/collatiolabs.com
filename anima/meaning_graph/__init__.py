"""meaning_graph — Layer 4 of the Human Operating Layer: the Meaning & Relationship Graph.

A read-only view over the World State relational/causal edges, formalised with two guarantees: every
fact names its PROVENANCE (source + confidence + when), and SENSITIVE facts are flagged consent-relevant
(tying the graph to the Consent & Boundaries layer). It creates no new truth; it makes meaning auditable.
"""
from . import graph  # noqa: F401
