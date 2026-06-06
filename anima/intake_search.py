"""intake_search — Labeled cross-store search over Vera's knowledge stores.

Offline, deterministic keyword/overlap scoring over every store the intake pipeline
can write to. The CRITICAL invariant: ``source_type`` is ALWAYS correct and NEVER
blurs personal memory with external reference. The labels are the contract:

    memory           — LIRF personal facts (about the user — NEVER external content)
    reference        — Reference Library documents (citable external source)
    uploaded_pdf     — a reference item whose rights indicate a user-uploaded PDF
    web_page         — a reference item fetched from the web
    lerf_skill       — an active LERF skill
    lerf_concept     — an active LERF concept
    lerf_procedure   — an extracted procedure stored as a LERF skill (kind=procedure)
    personal_preference — personal intelligence objects: preferences / values / decisions
    world            — World Model entities / world_state edges

Pure function: ``search(query, name, scopes)`` returns a list of result dicts and
NEVER writes anything. All heavy imports are done lazily inside functions, so the module
can be imported without loading the full cognitive stack.
"""

from __future__ import annotations

import re
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Source-type labels — these are the contract the API surface exports
# ---------------------------------------------------------------------------
ST_MEMORY = "memory"
ST_REFERENCE = "reference"
ST_UPLOADED_PDF = "uploaded_pdf"
ST_WEB_PAGE = "web_page"
ST_LERF_SKILL = "lerf_skill"
ST_LERF_CONCEPT = "lerf_concept"
ST_LERF_PROCEDURE = "lerf_procedure"
ST_PERSONAL = "personal_preference"
ST_WORLD = "world"

ALL_SOURCE_TYPES = (
    ST_MEMORY, ST_REFERENCE, ST_UPLOADED_PDF, ST_WEB_PAGE,
    ST_LERF_SKILL, ST_LERF_CONCEPT, ST_LERF_PROCEDURE,
    ST_PERSONAL, ST_WORLD,
)

# Scope names the caller may pass (maps to source_type groups)
SCOPE_MEMORY = "memory"
SCOPE_REFERENCE = "reference"
SCOPE_LERF = "lerf"
SCOPE_PERSONAL = "personal"
SCOPE_WORLD = "world"
ALL_SCOPES = (SCOPE_MEMORY, SCOPE_REFERENCE, SCOPE_LERF, SCOPE_PERSONAL, SCOPE_WORLD)


# ---------------------------------------------------------------------------
# Tokeniser + scorer
# ---------------------------------------------------------------------------
def _words(text: str) -> set:
    """Lowercase word-tokens from text; single-char tokens dropped."""
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", text or "") if len(w) > 1}


def _score(query_words: set, *text_fields: str) -> float:
    """Overlap score: fraction of query words found in the combined text fields."""
    if not query_words:
        return 0.0
    combined = set()
    for t in text_fields:
        combined |= _words(t)
    overlap = query_words & combined
    return len(overlap) / len(query_words)


def _result(*, id: str, source_type: str, title: str, snippet: str,
            score: float, destination: str) -> dict:
    return {
        "id": str(id or ""),
        "source_type": str(source_type),
        "title": str(title or "")[:200],
        "snippet": str(snippet or "")[:300],
        "score": round(float(score), 3),
        "destination": str(destination or ""),
    }


# ---------------------------------------------------------------------------
# Per-store search functions
# ---------------------------------------------------------------------------

def _search_lirf(query_words: set, name: str) -> list:
    """Search LIRF personal facts. source_type='memory'. NEVER blurred with external."""
    results = []
    try:
        from . import memory_lirf as mlirf
        facts = mlirf.Facts.load(name)
        rows = facts.about() or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            trait = str(row.get("trait") or "")
            value = str(row.get("value") or "")
            evidence = str(row.get("evidence") or "")
            sc = _score(query_words, trait, value, evidence)
            if sc > 0:
                results.append(_result(
                    id=str(row.get("id") or trait),
                    source_type=ST_MEMORY,
                    title=f"personal fact: {trait}",
                    snippet=f"{trait} = {value[:200]}",
                    score=sc,
                    destination="LIRF",
                ))
    except Exception:
        pass
    return results


def _search_reference(query_words: set, name: str) -> list:
    """Search the Reference Library. source_type='reference'/'uploaded_pdf'/'web_page'."""
    results = []
    try:
        from . import intake_queue as iq
        for item in iq.references(name):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            prov = item.get("provenance") or {}
            rights = str(prov.get("rights_category") or "")
            url_or_file = str(prov.get("url_or_file") or "")
            # classify the source_type from provenance signals
            if rights in ("public-web",) or url_or_file.startswith(("http://", "https://")):
                stype = ST_WEB_PAGE
            elif "pdf" in url_or_file.lower() or "pdf" in title.lower():
                stype = ST_UPLOADED_PDF
            else:
                stype = ST_REFERENCE
            # search across title + chunk text
            chunk_texts = " ".join(
                (ch.get("text") or "") for ch in (item.get("chunks") or [])
                if isinstance(ch, dict)
            )
            sc = _score(query_words, title, chunk_texts, str(prov.get("source") or ""))
            if sc > 0:
                # best matching chunk snippet
                best_chunk = ""
                best_chunk_sc = 0.0
                for ch in (item.get("chunks") or []):
                    if not isinstance(ch, dict):
                        continue
                    ctext = ch.get("text") or ""
                    csc = _score(query_words, ctext)
                    if csc > best_chunk_sc:
                        best_chunk_sc = csc
                        best_chunk = ctext
                snippet = (best_chunk or chunk_texts)[:300]
                results.append(_result(
                    id=str(item.get("id") or ""),
                    source_type=stype,
                    title=title,
                    snippet=snippet,
                    score=sc,
                    destination="Reference Library",
                ))
    except Exception:
        pass
    return results


def _search_lerf(query_words: set, name: str) -> list:
    """Search LERF: skills, concepts, procedures. source_type varies by kind."""
    results = []
    try:
        from . import lerf
        # skills (includes procedure-shaped skills)
        for obj in lerf.all_skills(name=name, include_nonactive=False):
            if not isinstance(obj, dict):
                continue
            obj_name = str(obj.get("name") or "")
            domain = str(obj.get("domain") or "")
            steps_text = " ".join(str(s) for s in (obj.get("steps") or []))
            support = " ".join(str(s) for s in (obj.get("support") or []))
            sc = _score(query_words, obj_name, domain, steps_text, support)
            if sc > 0:
                # detect if this is a procedure (stored as a skill with extracted_kind:procedure in support)
                is_procedure = any("extracted_kind:procedure" in str(s) for s in (obj.get("support") or []))
                stype = ST_LERF_PROCEDURE if is_procedure else ST_LERF_SKILL
                results.append(_result(
                    id=str(obj.get("id") or obj_name),
                    source_type=stype,
                    title=f"{stype}: {obj_name}",
                    snippet=(steps_text[:300] or domain),
                    score=sc,
                    destination="LERF",
                ))
        # concepts
        try:
            concepts = lerf.retrieve_concepts("", name=name) if hasattr(lerf, "retrieve_concepts") else []
        except Exception:
            concepts = []
        for obj in (concepts or []):
            if not isinstance(obj, dict):
                continue
            obj_name = str(obj.get("name") or "")
            defn = str(obj.get("definition") or "")
            sc = _score(query_words, obj_name, defn)
            if sc > 0:
                results.append(_result(
                    id=str(obj.get("id") or obj_name),
                    source_type=ST_LERF_CONCEPT,
                    title=f"concept: {obj_name}",
                    snippet=defn[:300],
                    score=sc,
                    destination="LERF",
                ))
        # heuristics
        try:
            heuristics = lerf.retrieve_heuristics(query_words and " ".join(query_words) or "",
                                                   name=name)
        except Exception:
            heuristics = []
        for obj in (heuristics or []):
            if not isinstance(obj, dict):
                continue
            obj_name = str(obj.get("name") or "")
            cond = str(obj.get("condition") or "")
            action = str(obj.get("action") or "")
            sc = _score(query_words, obj_name, cond, action)
            if sc > 0:
                results.append(_result(
                    id=str(obj.get("id") or obj_name),
                    source_type=ST_LERF_SKILL,
                    title=f"heuristic: {obj_name}",
                    snippet=f"if {cond[:100]}, then {action[:100]}",
                    score=sc,
                    destination="LERF",
                ))
        # failure modes
        try:
            failures = lerf.retrieve_failure_modes(
                query_words and " ".join(query_words) or "", name=name)
        except Exception:
            failures = []
        for obj in (failures or []):
            if not isinstance(obj, dict):
                continue
            obj_name = str(obj.get("name") or "")
            trigger = str(obj.get("trigger") or "")
            sc = _score(query_words, obj_name, trigger)
            if sc > 0:
                results.append(_result(
                    id=str(obj.get("id") or obj_name),
                    source_type=ST_LERF_SKILL,
                    title=f"failure_mode: {obj_name}",
                    snippet=trigger[:300],
                    score=sc,
                    destination="LERF",
                ))
    except Exception:
        pass
    return results


def _search_personal(query_words: set, name: str) -> list:
    """Search Personal Intelligence objects. source_type='personal_preference'."""
    results = []
    try:
        from . import personal
        profile = personal.personal_profile(name) or {}
        for section_key in ("preferences", "values", "decisions", "lessons",
                            "writing_preferences", "decision_patterns"):
            items = profile.get(section_key) or []
            if isinstance(items, dict):
                items = list(items.values())
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                obj_name = str(obj.get("name") or obj.get("key") or "")
                content = str(obj.get("value") or obj.get("definition") or obj.get("description") or "")
                sc = _score(query_words, obj_name, content, section_key)
                if sc > 0:
                    results.append(_result(
                        id=str(obj.get("id") or obj_name),
                        source_type=ST_PERSONAL,
                        title=f"{section_key}: {obj_name}",
                        snippet=content[:300],
                        score=sc,
                        destination="Personal Intelligence",
                    ))
    except Exception:
        pass
    return results


def _search_world(query_words: set, name: str) -> list:
    """Search World Model entities. source_type='world'."""
    results = []
    try:
        from . import world_model as wm
        # most recent world model
        models_list = wm.world_models(name) or []
        if not models_list:
            return results
        model = models_list[-1] if isinstance(models_list[-1], dict) else None
        if not model:
            return results
        for ent in (model.get("entities") or []):
            if not isinstance(ent, dict):
                continue
            key = str(ent.get("key") or "")
            etype = str(ent.get("type") or "")
            desc = str(ent.get("description") or "")
            sc = _score(query_words, key, etype, desc)
            if sc > 0:
                results.append(_result(
                    id=str(ent.get("id") or key),
                    source_type=ST_WORLD,
                    title=f"entity: {key}",
                    snippet=f"[{etype}] {desc[:200]}",
                    score=sc,
                    destination="World Model",
                ))
    except Exception:
        pass
    # also check world_state edges as a fallback
    try:
        from . import world_state as ws
        edges = ws.get_edges(name) if hasattr(ws, "get_edges") else []
        for edge in (edges or []):
            if not isinstance(edge, dict):
                continue
            subj = str(edge.get("subject") or "")
            pred = str(edge.get("predicate") or "")
            obj = str(edge.get("object") or "")
            sc = _score(query_words, subj, pred, obj)
            if sc > 0:
                results.append(_result(
                    id=str(edge.get("id") or f"{subj}-{pred}"),
                    source_type=ST_WORLD,
                    title=f"relation: {subj} {pred} {obj}",
                    snippet=f"{subj} {pred} {obj}",
                    score=sc,
                    destination="World Model",
                ))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------
def search(query: str, name: str = "Vera", scopes: Optional[list] = None) -> list:
    """Cross-store offline keyword search. Returns a list of result dicts:
    ``[{id, source_type, title, snippet, score, destination}]`` sorted by score desc.

    ``source_type`` is ALWAYS correct and NEVER blurs personal memory with external
    reference — this is the hard contract. Each store is searched independently and
    its results carry the correct label before merging.

    ``scopes`` is an optional list of scope names from ``ALL_SCOPES``; defaults to all.
    Imports are lazy (heavy modules not loaded until called).
    """
    if not query or not query.strip():
        return []
    q_words = _words(query)
    if not q_words:
        return []
    active_scopes = set(scopes or ALL_SCOPES)
    results: list = []

    # Each store is searched independently — source_type is set by the store, never cross-blurred.
    if SCOPE_MEMORY in active_scopes:
        results.extend(_search_lirf(q_words, name))

    if SCOPE_REFERENCE in active_scopes:
        results.extend(_search_reference(q_words, name))

    if SCOPE_LERF in active_scopes:
        results.extend(_search_lerf(q_words, name))

    if SCOPE_PERSONAL in active_scopes:
        results.extend(_search_personal(q_words, name))

    if SCOPE_WORLD in active_scopes:
        results.extend(_search_world(q_words, name))

    # Sort by score descending; deduplicate on (id, source_type) keeping highest score.
    seen: dict = {}
    for r in sorted(results, key=lambda x: -x["score"]):
        key = (r["id"], r["source_type"])
        if key not in seen:
            seen[key] = r
    return list(seen.values())
