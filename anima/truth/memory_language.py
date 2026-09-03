"""truth.memory_language — unsupported memory language is blocked or rewritten, never shipped.

The forbidden shapes (claims OF MEMORY) may only ship when the turn actually carries memory
provenance (bound LIRF rows / a deterministic memory seam). Without support, each phrase is
rewritten to its honest counterpart and the turn is flagged so the caller emits an
`unsupported` Truth Ledger event. ZERO unsupported memory claims is the bar.
"""
from __future__ import annotations

import re

# forbidden memory-claim shapes -> honest rewrites (applied ONLY when the turn has no support)
_REWRITES = [
    (re.compile(r"\bif memory serves\b", re.I), "I may be guessing"),
    (re.compile(r"\bmy recollection is\b", re.I), "my guess is"),
    (re.compile(r"\bas i recall\b", re.I), "I may be misremembering, but"),
    (re.compile(r"\bi remember\b", re.I), "I might have inferred"),
    (re.compile(r"\byou told me\b", re.I), "I had the impression"),
    (re.compile(r"\bi know your preference is\b", re.I),
     "I don't have your preference on record, but it might be"),
    (re.compile(r"\bi know you (?:prefer|like|love|hate)\b", re.I), "you might"),
]


def detect(text: str) -> list[str]:
    """Every forbidden memory-claim phrase present in `text` (the matched spans, lowercased)."""
    hits = []
    for rx, _ in _REWRITES:
        for m in rx.finditer(text or ""):
            hits.append(m.group(0).lower())
    return hits


def guard(text: str, has_memory_support: bool) -> tuple[str, list[str]]:
    """(possibly-rewritten text, flagged phrases). With support the text is untouched; without,
    each forbidden phrase is rewritten to its honest counterpart and returned as flagged."""
    if has_memory_support:
        return text, []
    hits = detect(text)
    if not hits:
        return text, []
    out = text
    for rx, repl in _REWRITES:
        out = rx.sub(repl, out)
    return out, hits
