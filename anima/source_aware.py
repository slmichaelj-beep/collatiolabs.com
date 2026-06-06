"""
source_aware — reference attribution for the live turn (Intake Wave 3, Q, safe layer).

When Vera answers, surface WHICH uploaded/reference sources are relevant to the question,
labeled as external REFERENCE — never blurred with personal memory (LIRF) or with Vera's
self. This is the *attribution* half of source-aware answering:

  * It reads ONLY the Reference Library (intake_queue references) — the cite-only store of
    user-provided / public documents. It never reads LIRF facts, the persona, the heart, or
    any identity store, so personal memory and external reference can never be confused.
  * It is PURE + OFFLINE + GUARDED: deterministic keyword overlap, no model call, and every
    public entry returns [] rather than raising — so it can never change or break a reply.
  * It does NOT touch mouth.respond or the generated text. The reply is byte-for-byte what it
    would have been; this only adds a `sources` attribution channel the UI can show as
    "based on: <your uploaded doc>". (Reference-GROUNDED generation — the model answering
    *from* the source — is a separate, deeper step that must be re-certified against the
    #1-rule with the full experience battery before it ships.)

Returned shape (each item):
  {"source_id", "title", "type"("reference"|"uploaded_pdf"|"web_page"), "snippet", "score"}
"""

from __future__ import annotations

import re
from typing import List, Dict

_STOP = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for", "with", "is",
    "are", "was", "were", "be", "been", "it", "this", "that", "these", "those", "i", "you",
    "me", "my", "your", "we", "they", "he", "she", "do", "does", "did", "how", "what", "why",
    "when", "where", "who", "can", "could", "would", "should", "about", "tell", "show", "from",
}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if w not in _STOP}


def _infer_type(item: dict) -> str:
    """Label by rights/url WITHOUT ever calling it personal memory — reference is reference."""
    prov = item.get("provenance") or {}
    rights = str(prov.get("rights_category") or item.get("rights") or "").lower()
    url = str(prov.get("url_or_file") or prov.get("url") or item.get("title") or "").lower()
    if rights == "public-web" or url.startswith("http"):
        return "web_page"
    if url.endswith(".pdf") or "pdf" in str(item.get("kind") or "").lower():
        return "uploaded_pdf"
    return "reference"


def _best_snippet(chunks: list, q: set) -> tuple:
    """Return (score, snippet) for the best-overlapping chunk of a reference item."""
    best_score, best_text = 0.0, ""
    for ch in chunks or []:
        text = ch.get("text") if isinstance(ch, dict) else str(ch)
        if not text:
            continue
        ov = q & _tokens(text)
        if not ov:
            continue
        score = len(ov) / (len(q) or 1)
        if score > best_score:
            best_score, best_text = score, text
    snippet = best_text.strip().replace("\n", " ")
    if len(snippet) > 240:
        snippet = snippet[:237].rstrip() + "…"
    return best_score, snippet


def relevant_sources(name: str, text: str, *, limit: int = 3,
                     min_score: float = 0.15) -> List[Dict]:
    """The relevant Reference-Library sources for THIS question — labeled, scored, snippet-ed.

    Reference Library ONLY (cite-only user/public documents). Never LIRF, never identity.
    Pure keyword overlap; fully guarded (returns [] on anything unexpected). Empty when the
    question doesn't meaningfully match any uploaded source — silence over a forced citation.
    """
    q = _tokens(text)
    if not q:
        return []
    try:
        from . import intake_queue as _iq
    except Exception:
        return []
    try:
        items = _iq.references(name) or []
    except Exception:
        return []
    scored: List[Dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("deleted"):                      # a forgotten source is not cited
            continue
        chunks = item.get("chunks") or []
        score, snippet = _best_snippet(chunks, q)
        # also let the title carry a little weight (a doc titled for the topic is relevant)
        title = str(item.get("title") or "")
        title_ov = q & _tokens(title)
        score += 0.1 * len(title_ov)
        if score < min_score:
            continue
        scored.append({
            "source_id": item.get("id") or item.get("source_id") or "",
            "title": title or "(untitled source)",
            "type": _infer_type(item),
            "snippet": snippet,
            "score": round(float(score), 3),
        })
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:max(1, int(limit))]


# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    """Hermetic selftest — redirect the store, seed a reference, assert attribution + isolation."""
    import tempfile, pathlib, sys
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    from . import intake_queue as iq
    from . import intake as _int
    td = pathlib.Path(tempfile.mkdtemp(prefix="srcaware-"))
    old_intake, old_iq = _int.STORE, getattr(iq, "STORE", None)
    _int.STORE = td
    if hasattr(iq, "STORE"):
        iq.STORE = td
    try:
        name = "SrcAwareTest"
        iq.add_reference(
            name, source_id="src_test1", title="Acme SLA Handbook",
            provenance={"rights_category": "user-provided", "url_or_file": "sla.md"},
            chunks=[{"text": "A service level agreement is a documented commitment between a "
                             "provider and a client, defining uptime and response targets."}])
        hits = relevant_sources(name, "what is a service level agreement?")
        ok("relevant query returns the reference source", len(hits) >= 1)
        ok("source is labeled reference (not memory)", hits and hits[0]["type"] in
           ("reference", "uploaded_pdf", "web_page"))
        ok("source carries a snippet + title", hits and hits[0]["snippet"] and hits[0]["title"])
        off = relevant_sources(name, "what did I have for breakfast today?")
        ok("unrelated personal question -> no forced citation", off == [])
        empty = relevant_sources(name, "")
        ok("empty query -> []", empty == [])
        # isolation: a corrupt/missing store must never raise
        bad = relevant_sources("NoSuchCreature", "anything at all")
        ok("missing creature -> [] (guarded, never raises)", bad == [])
    finally:
        _int.STORE = old_intake
        if hasattr(iq, "STORE") and old_iq is not None:
            iq.STORE = old_iq
    print("\nSOURCE-AWARE SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("usage: python3 -m anima.source_aware --selftest")
