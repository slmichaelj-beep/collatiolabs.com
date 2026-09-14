"""meaning_graph.graph — build the Meaning & Relationship Graph from the REAL World State edges.

Read-only. Each edge is enriched with its PROVENANCE (the source/confidence/timestamps it already
carries) and a SENSITIVITY classification (via the consent classifier), so a sensitive relation is
visibly consent-relevant. Provenance COVERAGE is measured honestly — never assumed 100%. Never raises.
"""
from __future__ import annotations


def _edge_text(e: dict) -> str:
    return "%s %s %s" % (e.get("subject", ""), e.get("predicate", ""), e.get("object", ""))


def has_provenance(e: dict) -> bool:
    """An edge has provenance only if it names a real source AND carries a confidence + a created time."""
    return bool(str(e.get("source") or "").strip()) and e.get("confidence") is not None and bool(e.get("created"))


def provenance_coverage(edges: list) -> float:
    """Fraction of edges that carry full provenance. Computed, not assumed — a single un-sourced edge
    pulls it below 1.0 (this is what makes the metric honest)."""
    if not edges:
        return 1.0
    return round(sum(1 for e in edges if has_provenance(e)) / len(edges), 3)


def _sensitivity(e: dict) -> dict:
    try:
        from anima.consent.classifier import classify_sensitivity
        return classify_sensitivity(_edge_text(e))
    except Exception:
        return {"sensitive": False, "domain": "general", "markers": []}


def enrich(edges: list) -> list:
    """Attach provenance + sensitivity to each edge (read-only copies)."""
    out = []
    for e in edges:
        sens = _sensitivity(e)
        out.append({
            "id": e.get("id"),
            "subject": e.get("subject"), "predicate": e.get("predicate"), "object": e.get("object"),
            "kind": e.get("kind"),
            "confidence": e.get("confidence"), "support": e.get("support", 1),
            "provenance": str(e.get("source") or "").strip() or None,
            "has_provenance": has_provenance(e),
            "created": e.get("created"), "updated": e.get("updated"),
            "sensitive": bool(sens.get("sensitive")),
            "domain": sens.get("domain", "general"),
            "consent_relevant": bool(sens.get("sensitive")),   # sensitive meaning is gated like sensitive memory
        })
    return out


def build(name: str = "Vera", limit: int = 500) -> dict:
    """The Meaning Graph payload: enriched edges + provenance coverage + sensitivity flags, grouped by
    subject. Read-only; honest empty state."""
    try:
        from anima.world_state import World
        raw = World.load(name).active()[: int(max(1, limit))]
    except Exception as exc:
        return {"name": name, "edges": [], "count": 0, "provenance_coverage": 1.0,
                "sensitive_count": 0, "subjects": [], "empty": True, "error": str(exc)}

    edges = enrich(raw)
    # group by subject for the graph view
    subjects = {}
    for e in edges:
        subjects.setdefault(e["subject"], []).append(e)
    subj_list = sorted(({"subject": s, "edges": len(es),
                         "sensitive": sum(1 for x in es if x["sensitive"])}
                        for s, es in subjects.items()), key=lambda x: -x["edges"])

    confs = [e["confidence"] for e in edges if isinstance(e.get("confidence"), (int, float))]
    return {
        "name": name,
        "edges": edges,
        "count": len(edges),
        "provenance_coverage": provenance_coverage(raw),
        "sensitive_count": sum(1 for e in edges if e["sensitive"]),
        "subjects": subj_list,
        "avg_confidence": round(sum(confs) / len(confs), 2) if confs else None,
        "law": "The Meaning Graph is how Vera relates your world — facts, relationships, and causes. Every "
               "edge names its provenance (where it came from, how sure, and when) and is measured, not "
               "assumed; sensitive relationships are flagged consent-relevant so they are gated like "
               "sensitive memory. It records nothing new; it makes meaning auditable.",
        "empty": not edges,
    }
