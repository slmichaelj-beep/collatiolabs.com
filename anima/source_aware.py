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
from typing import List, Dict, Optional

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


# Prompt-injection markers: text inside an EXTERNAL source that tries to act as INSTRUCTIONS to Vera
# rather than be quoted as data. The architecture already blocks any ACTION from source text (no
# connector call in the ingest/answer path, caps off, no silent write); this is DEFENSE-IN-DEPTH —
# it FLAGS such content so the answer path can frame it to the model as untrusted, quoted data.
_INJECTION_RE = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior|the\s+above)\s+(?:instructions|prompts?|rules)"
    r"|disregard\s+(?:all\s+)?(?:previous|prior|the)\b"
    r"|you\s+are\s+now\s+(?:an?\s+|unrestricted|in\s+)"
    r"|system\s*(?:override|prompt|message)|^\s*system\s*:"
    r"|rights_category\s*[:=]"
    r"|enable\s+identity_agency|grant\s+(?:yourself\s+)?agency|enable\s+agency\b"
    r"|forward\s+all\s+(?:of\s+)?(?:the\s+)?(?:user'?s\s+)?e-?mails?"
    r"|reply\s+only\s+with|respond\s+only\s+with|output\s+only\s+the"
    r"|do\s+not\s+(?:tell|inform|alert|notify)\s+the\s+user"
    r"|jailbreak|developer\s+mode|\bDAN\b"
    r"|exfiltrat|send\s+(?:all\s+)?(?:the\s+)?(?:data|secrets?|passwords?|api\s*keys?)",
    re.I | re.M)


def looks_like_injection(text: str) -> bool:
    """True if EXTERNAL source text contains a prompt-injection OR hostile-control marker (text trying
    to act as an instruction to Vera, or a planted command like PWNED / 'wire money' / 'delete emails'
    / 'this override'). UNIFIED with metrics.scan_hostile so the SOURCE-quarantine detector and the
    OUTPUT gate detector never disagree (the live P0: the output gate caught 'PWNED' but this source
    detector did not, so a poisoned source could slip into context). Pure; never raises. Quarantine is
    targeted: a false flag only excludes one source from answer-support, never blocks the spine."""
    try:
        if not text:
            return False
        if _INJECTION_RE.search(str(text)):
            return True
        from . import metrics as _m
        return bool(_m.scan_hostile(text))
    except Exception:
        return False


def neutralize(text: str) -> str:
    """DEFANG injection imperatives in untrusted source text so they cannot act as instructions even if
    the text reaches the model's context. Splits the snippet into sentence/line segments and DROPS any
    segment carrying an injection marker, keeping the benign prose (the real, quotable content). This is
    the model-echo fix: there is no imperative left for a small model to obey or parrot back.

    Deterministic and idempotent; never raises. Clean text is returned unchanged (no rewrite when
    nothing is flagged). If EVERY segment was an instruction, returns a single removed-marker."""
    try:
        if not text or not _INJECTION_RE.search(str(text)):
            return text
        segs = re.split(r"(?<=[.!?])\s+|[\r\n]+", str(text))
        kept = [s.strip() for s in segs if s.strip() and not _INJECTION_RE.search(s)]
        cleaned = " ".join(kept).strip()
        return cleaned if cleaned else "[untrusted instructions removed]"
    except Exception:
        return str(text)


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
        # defense-in-depth: flag a source whose surfaced text tries to act as instructions, so the
        # answer path can frame it to the model as untrusted, quoted data (scan the snippet + the
        # first chunks, bounded). The architecture already blocks any ACTION from source text.
        flagged = looks_like_injection(snippet) or any(
            looks_like_injection(c.get("text") if isinstance(c, dict) else "") for c in chunks[:12])
        if flagged:
            # QUARANTINE (P0 fix): an injection-bearing source can NEVER become answer-support, a
            # source chip, or model context. It stays on disk as EVIDENCE, but it is EXCLUDED from
            # this turn's support set entirely — untrusted text is data, never trusted context. (The
            # earlier neutralize() of the snippet was not enough: a 'based on source' chip still
            # dressed it as trusted. Quarantine = drop it from the support path.)
            continue
        scored.append({
            "source_id": item.get("id") or item.get("source_id") or "",
            "title": title or "(untitled source)",
            "type": _infer_type(item),
            "snippet": snippet,
            "score": round(float(score), 3),
            "untrusted_injection": False,
        })
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:max(1, int(limit))]


# ============================================================================================
# Deterministic reference RECALL — the *use* half of source-aware answering.
#
# attribution (relevant_sources) only LABELS which source is relevant. RECALL actually ANSWERS
# FROM the stored reference when the user explicitly asks what they uploaded/saved about a topic,
# and labels it as their uploaded reference. It is DETERMINISTIC (no model) and the seam in
# server._turn ships it through the SAME #1-rule final_output_gate as every reply — the proven
# host-awareness-seam pattern. recall() returns None unless (a) the phrasing is an explicit
# upload/reference question AND (b) a stored reference actually matches; otherwise the normal
# pipeline answers honestly ("you haven't uploaded anything about that"). Reference content is
# external user material, never personal memory (LIRF) and never Vera's self.
# ============================================================================================

_UPLOAD_VERBS = (r"(?:upload(?:ed)?|add(?:ed)?|sav(?:e|ed)|stor(?:e|ed)|put|gave|give|sent|send|"
                 r"shared|share)")
_REF_NOUNS = r"(?:referenc\w*|librar\w*|upload\w*|document\w*|docs?|files?|notes?|knowledge)"


def classify_recall(text: str) -> bool:
    """True iff `text` is an explicit 'what did I upload / save / put in my reference about X'
    question. Tight on purpose — a normal conversational turn must NOT be hijacked into a
    reference dump. The seam still only fires if a stored reference also matches (see recall())."""
    t = (text or "").strip().lower()
    if not t or len(t) > 600:
        return False
    # "what did i upload/save/store/... <about X>"  — the canonical phrasing.
    if re.search(r"\bwhat\b.*\bi\b\s+(?:" + _UPLOAD_VERBS + r")\b", t):
        return True
    # "what ... in/from/about my|the reference|library|docs|uploads|notes|knowledge"
    if re.search(r"\bwhat\b.*\b(?:in|from|about|on)\b\s+(?:my|the)\s+" + _REF_NOUNS, t):
        return True
    # "from/in my|the uploaded|reference|saved|knowledge ..."
    if re.search(r"\b(?:from|in)\s+(?:my|the)\s+(?:uploaded|reference|saved|knowledge)\b", t):
        return True
    return False


def _friendly_title(title: str) -> str:
    """A title worth quoting, or '' for a generic auto-id (so we don't say 'reference src abc123')."""
    t = (title or "").strip()
    if (not t or t == "(untitled source)" or t.lower().startswith("src ")
            or re.fullmatch(r"[0-9a-f]{6,}", t) or t.lower().startswith("http")):
        return ""
    return t


def _recall_body(name: str, source_id, q: set, max_chars: int) -> str:
    """The most-relevant chunk text(s) of ONE reference, concatenated up to max_chars."""
    try:
        from . import intake_queue as _iq
        items = _iq.references(name) or []
    except Exception:
        return ""
    item = next((it for it in items if isinstance(it, dict)
                 and (it.get("id") == source_id or it.get("source_id") == source_id)), None)
    if not item:
        return ""
    scored = []
    for ch in item.get("chunks") or []:
        txt = (ch.get("text") if isinstance(ch, dict) else str(ch)) or ""
        ov = q & _tokens(txt)
        if ov:
            scored.append((len(ov), txt.strip()))
    scored.sort(key=lambda s: s[0], reverse=True)
    out, total = [], 0
    for _, txt in scored:
        out.append(txt)
        total += len(txt)
        if total >= max_chars:
            break
    body = " ".join(out).replace("\n", " ").strip()
    if len(body) > max_chars:
        body = body[:max_chars - 1].rstrip() + "…"
    return body


def recall(name: str, text: str, *, cloud_safe: bool = False, max_chars: int = 600) -> Optional[str]:
    """A labeled answer built FROM the best-matching uploaded reference, or None.

    Returns text only when classify_recall(text) is True AND a reference actually matches.
    The returned string explicitly labels the content as the user's uploaded reference; the
    server seam routes it through final_output_gate before shipping. Fully guarded: never raises.
    """
    try:
        if not classify_recall(text):
            return None
        hits = relevant_sources(name, text, limit=2)
        if not hits:
            return None
        top = hits[0]
        q = _tokens(text)
        body = _recall_body(name, top.get("source_id"), q, max_chars) or str(top.get("snippet") or "").strip()
        if not body:
            return None
        ft = _friendly_title(top.get("title") or "")
        lead = (f'From your uploaded reference "{ft}": ' if ft else "From the reference you uploaded: ")
        return lead + body
    except Exception:
        return None


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
        # ---- reference RECALL (the *use* half of source-aware answering) ----------------
        ok("classify_recall: 'what did I upload about X' -> True",
           classify_recall("what did I upload about the service agreement?"))
        ok("classify_recall: 'what's in my reference about uptime' -> True",
           classify_recall("what's in my reference about uptime?"))
        ok("classify_recall: normal chat -> False",
           not classify_recall("how are you feeling today?"))
        ans = recall(name, "what did I upload about a service level agreement?")
        ok("recall answers FROM the reference (uses stored content)",
           bool(ans) and "service level agreement" in (ans or "").lower())
        ok("recall labels it as the user's uploaded reference",
           bool(ans) and "uploaded" in (ans or "").lower() and "reference" in (ans or "").lower())
        ok("recall on a non-recall question -> None (no hijack)",
           recall(name, "how are you today?") is None)
        ok("recall with NO matching source -> None (honest fall-through)",
           recall(name, "what did I upload about quantum chromodynamics zzz?") is None)
        ok("recall on a missing creature -> None (guarded)",
           recall("NoSuchCreature", "what did I upload about anything?") is None)
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
