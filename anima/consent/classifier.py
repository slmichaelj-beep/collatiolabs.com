"""consent.classifier — deterministic SENSITIVITY classification.

Given a piece of text (a memory candidate, a source snippet, a turn), decide which sensitive DOMAIN it
touches, if any. Pure, offline, guarded — keyword/phrase markers per domain, no model. Conservative on
the safe side: it is better to flag a borderline item as sensitive (-> ask) than to silently write it.
The ratio/labels are what matter; exact scores are heuristic.
"""
from __future__ import annotations

import re

from . import schema

# Per-domain markers. Word-boundary, case-insensitive. Tuned for personal-life material.
_MARKERS = {
    "health": r"\b(diagnos\w+|symptom|disease|cancer|tumou?r|chronic|blood pressure|cholesterol|"
              r"diabet\w+|medication|prescri\w+|doctor|clinic|hospital|surgery|illness|condition|"
              r"pain|injur\w+|disab\w+|HIV|STD|pregnan\w+)\b",
    "mental_health": r"\b(depress\w+|anxiet\w+|anxious|panic attack|suicid\w+|self[-\s]?harm|bipolar|"
                     r"ptsd|ocd|adhd|eating disorder|bulimi\w+|anorexi\w+|breakdown|psychiatric|"
                     r"mental health|medicated)\b",
    "therapy": r"\b(therap\w+|therapist|counsel\w+|counsellor|psycholog\w+|psychiatr\w+|my session)\b",
    "sex": r"\b(sex\w*|sexual\w*|intimac\w+|porn\w*|orgasm|libido|kink|fetish|nudes?)\b",
    "trauma": r"\b(trauma\w*|abus\w+|assault\w*|rape|molest\w+|ptsd|flashback|grief|grieving|"
              r"died|passed away|loss of)\b",
    "relationships": r"\b(my (boyfriend|girlfriend|partner|husband|wife|ex)|divorce|breakup|broke up|"
                     r"cheat\w+|affair|marriage|dating|in love|heartbreak)\b",
    "finance": r"\b(salary|income|debt|loan|mortgage|bankrupt\w*|credit score|net worth|savings|"
               r"\$[\d,]+|bank account|investment\w*|broke|can'?t afford|overdraft)\b",
    "legal": r"\b(lawsuit|sue\w*|attorney|lawyer|court|arrested|charges?|criminal|legal|settlement|"
             r"custody|restraining order|probation)\b",
    "family": r"\b(my (mother|father|mom|dad|son|daughter|child|kids?|sister|brother|parents?)|"
              r"family (conflict|issue|problem)|estranged)\b",
    "location": r"\b(my address|home address|I live at|GPS|coordinates|geoloc\w+|where I live|"
                r"my house is at)\b",
    "religion_politics": r"\b(my (faith|religion|church|god)|I (voted|believe in)|political\w*|"
                         r"conservative|liberal|atheist|muslim|christian|jewish|hindu|buddhist)\b",
    "identity": r"\b(my (real )?identity|who I really am|my orientation|gay|lesbian|bisexual|"
                r"transgender|non[-\s]?binary|coming out|my secret)\b",
    "workplace_conflict": r"\b(my (boss|manager|coworker|colleague)|fired|laid off|harass\w+|"
                          r"workplace|HR complaint|hostile work|quit my job)\b",
    "private_messages": r"\b(private message|DM|text from|email from|journal|diary|personal note)\b",
}
_COMPILED = None


def _compiled():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = {d: re.compile(p, re.I) for d, p in _MARKERS.items()}
    return _COMPILED


def classify_sensitivity(text) -> dict:
    """Return {'domain', 'sensitive', 'markers', 'confidence'}. 'general' + sensitive=False when no
    sensitive domain is touched. Deterministic + guarded (never raises)."""
    out = {"domain": "general", "sensitive": False, "markers": [], "confidence": 0.0}
    try:
        t = str(text or "")
        if not t.strip():
            return out
        best_domain, best_hits = None, []
        for d, rx in _compiled().items():
            hits = rx.findall(t)
            # findall may return tuples for grouped patterns — flatten to strings
            flat = []
            for h in hits:
                flat.append(h if isinstance(h, str) else next((x for x in h if x), ""))
            flat = [x for x in flat if x]
            if flat and len(flat) > len(best_hits):
                best_domain, best_hits = d, flat
        if best_domain:
            out.update({"domain": best_domain, "sensitive": True,
                        "markers": sorted(set(m.lower() for m in best_hits))[:6],
                        "confidence": round(min(1.0, 0.5 + 0.15 * len(best_hits)), 2)})
        return out
    except Exception:
        return out


def is_sensitive(text) -> bool:
    return classify_sensitivity(text).get("sensitive", False)
