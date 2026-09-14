"""anima.knowledge_packs — curated domain knowledge: DATA, never policy.

Lifecycle: added -> quarantined -> indexed -> evaluated -> ready -> stale/disabled/removed.
No pack is retrievable before evaluation. Pack content cannot become behavior, mutate memory,
or override system rules / release status / cert status / host profile / consent — the only
path toward behavior or memory is a Teaching Mode draft riding the full approval flow.
"""
from . import api, builder, quarantine, registry, retrieval, schema  # noqa: F401
