"""cognitive_ergonomics.metrics — the deterministic, model-free scorers.

Every function is pure and reproducible: the same text always yields the same numbers. No randomness, no
network, no model. These are the measurable foundation the clarity report stands on.
"""
from __future__ import annotations

import re

from . import lexicon

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_SENT = re.compile(r"[.!?]+(?:\s+|$)")
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")


def words(text: str) -> list:
    return _WORD.findall(text or "")


def sentences(text: str) -> list:
    parts = [s.strip() for s in _SENT.split(text or "") if s.strip()]
    return parts or ([text.strip()] if (text or "").strip() else [])


def _syllables(word: str) -> int:
    w = word.lower()
    if w in lexicon.SYLLABLE_EXCEPTIONS:
        return lexicon.SYLLABLE_EXCEPTIONS[w]
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ie", "ee")):
        n -= 1
    return max(1, n)


def readability(text: str) -> dict:
    """Flesch Reading Ease (0-100; higher = easier). A deterministic proxy: 206.835 - 1.015*(words/
    sentence) - 84.6*(syllables/word). >=60 is plain English; <30 is very hard."""
    ws, ss = words(text), sentences(text)
    nw, ns = len(ws), max(1, len(ss))
    if nw == 0:
        return {"flesch": 100.0, "words": 0, "sentences": 0, "avg_sentence_len": 0.0, "syll_per_word": 0.0}
    syll = sum(_syllables(w) for w in ws)
    fre = 206.835 - 1.015 * (nw / ns) - 84.6 * (syll / nw)
    return {
        "flesch": round(max(0.0, min(100.0, fre)), 1),
        "words": nw, "sentences": ns,
        "avg_sentence_len": round(nw / ns, 1),
        "syll_per_word": round(syll / nw, 2),
    }


def jargon(text: str) -> dict:
    """Specialist-term density + the flagged terms. density = jargon_words / total_words."""
    ws = words(text)
    low = [w.lower() for w in ws]
    hits = sorted({w for w in low if w in lexicon.JARGON})
    density = (sum(1 for w in low if w in lexicon.JARGON) / len(ws)) if ws else 0.0
    return {"density": round(density, 3), "terms": hits, "count": len(hits)}


def hedging(text: str) -> dict:
    """Hedge-word count (single + multiword phrases). Too many => non-committal."""
    t = " " + (text or "").lower() + " "
    found = []
    for h in lexicon.HEDGES:
        n = t.count(" " + h + " ") if " " in h else len(re.findall(r"\b" + re.escape(h) + r"\b", t))
        if n:
            found.append(h)
    return {"count": len(found), "terms": sorted(found)}


def acronyms(text: str) -> dict:
    """Unexplained acronyms: ALL-CAPS tokens (>=2 letters) that are not common and not expanded nearby
    (an expansion is heuristically 'TLA (Three Letter Acronym)' or initials present in a preceding phrase)."""
    raw = _ACRONYM.findall(text or "")
    flagged = []
    for a in raw:
        if a in lexicon.ACRONYM_OK:
            continue
        # treat 'XYZ (...)' as explained
        if re.search(re.escape(a) + r"\s*\(", text or ""):
            continue
        flagged.append(a)
    return {"count": len(set(flagged)), "terms": sorted(set(flagged))}


def load(text: str) -> dict:
    """Cognitive load proxies: length, longest sentence, clause density (commas + coordinating
    conjunctions per sentence)."""
    ws, ss = words(text), sentences(text)
    longest = max((len(words(s)) for s in ss), default=0)
    clauses = len(re.findall(r",|\b(?:and|but|or|because|although|however|therefore|moreover)\b",
                            (text or "").lower()))
    return {
        "words": len(ws), "sentences": len(ss), "longest_sentence": longest,
        "clauses": clauses,
        "clauses_per_sentence": round(clauses / max(1, len(ss)), 1),
    }
