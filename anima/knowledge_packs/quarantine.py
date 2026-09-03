"""knowledge_packs.quarantine — pack text is DATA, never policy.

Evaluation scans every chunk for instruction-shaped content aimed at the assistant (the exact
attack family the Context Immune System quarantines in chat). A pack with hostile content can
still become ready — the text is EVIDENCE, retrievable WITH its hostility flagged — but its
prompt_injection_risk is HIGH and the retrieval layer renders it as quoted data with a warning,
never as instruction. Nothing in a pack can mutate memory, behavior, rules, status, or consent —
those surfaces simply do not read pack content (proven by certify_knowledge_packs).
"""
from __future__ import annotations

import re

# instruction-shaped patterns aimed at the assistant — flagged, never obeyed
_HOSTILE = [
    re.compile(r"\bignore (?:all )?(?:prior|previous) instructions\b", re.I),
    re.compile(r"\bsystem override\b", re.I),
    re.compile(r"\byou are now\b.{0,40}\b(?:unrestricted|dan)\b", re.I),
    re.compile(r"\b(?:rewrite|overwrite|update|mutate)\b.{0,30}\bmemor(?:y|ies)\b", re.I),
    re.compile(r"\bmark\b.{0,30}\b(?:dashboard|cert|status)\b.{0,20}\bgreen\b", re.I),
    re.compile(r"\b(?:send|exfiltrate|forward)\b.{0,40}\b(?:private|secret|password|token|data)\b", re.I),
    re.compile(r"\bchange\b.{0,30}\bhost profile\b", re.I),
    re.compile(r"\breveal\b.{0,30}\bsystem prompt\b", re.I),
]


def scan_text(text: str) -> list[str]:
    """Every instruction-shaped span found in `text` (empty == clean)."""
    hits = []
    for rx in _HOSTILE:
        for m in rx.finditer(text or ""):
            hits.append(m.group(0)[:80])
    return hits


def evaluate_chunks(chunks: list[dict]) -> dict:
    """The evaluation verdict for an indexed pack: per-chunk hostility flags + the overall
    injection risk. Hostile chunks are FLAGGED (quoted-data-only), never dropped silently."""
    flagged = []
    for i, ch in enumerate(chunks):
        hits = scan_text(ch.get("text", ""))
        if hits:
            flagged.append({"chunk": i, "hits": hits})
    risk = "high" if flagged else "low"
    return {"chunks_total": len(chunks), "flagged": flagged,
            "prompt_injection_risk": risk,
            "verdict": ("hostile content present — retrievable as QUOTED DATA with a warning, "
                        "never as instruction" if flagged else "clean")}
