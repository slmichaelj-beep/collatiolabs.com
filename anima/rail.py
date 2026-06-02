"""
rail — a structural honesty gate that lives in the SELF, not the mouth.

The eval proved every local brain (8B–14B) confabulates on one narrow class of
request: a *named entity* plus a demand for a *specific verifiable detail* — a
chapter of a book, a quote by a person, the score of a game, a prize winner, a
line in a letter. Bigger models don't fix this; they just confabulate more
fluently. So honesty can't live in the mouth. It lives here.

CRITICAL DESIGN RULE — no answer key. This module must NOT contain the facts to
any eval trap (no "there was no Game 8", no "Dalio wrote no such chapter"). That
would be teaching-to-the-test: the battery would hit 8/8 by memorising its own
answers and would mean nothing. Instead the rail recognises the *shape* of a
confabulation-prone request and injects a calibration instruction — "if you're
not certain this exact thing exists, say so rather than invent it." If that nudge
works, it must work on traps the rail has never seen (the held-out set proves it).
If it only helps the traps we wrote, it's overfitting and the held-out set exposes
it. Either way we learn the truth, which is the whole point.
"""

from __future__ import annotations

import re

# Cues that a turn is asking for a SPECIFIC, verifiable detail about a named thing
# — the structural signature of the traps. Deliberately generic (no entity names).
_FACTUAL = [
    r"\bchapter\b", r"\bpassage\b", r"\bverse\b", r"\bparagraph\b", r"\bon page\b",
    r"\bquote\b", r"\bquotation\b", r"\bexact (?:words|sentence|quote|line|phrase)\b",
    r"\bwhat did .+ say\b", r"\bwhat were .+ words\b",
    r"\bfinal score\b", r"\bwho won\b", r"\bgame \d+\b", r"\bgame number\b",
    r"\bnobel\b", r"\b(?:pulitzer|fields|booker|grammy|oscar|emmy)\b",
    r"\b(?:19|20)\d{2}\b.*\b(?:prize|award|winner|won|champion|final)\b",
    r"\bsummar(?:y|ise|ize)\b.+\bby\b", r"\b(?:his|her|their) \w+ letter\b",
    r"\bletter (?:to|number|#)\b", r"\bargument (?:against|for)\b.+\bin\b",
    r"\bthe novel ['\"]", r"\bthe book ['\"]", r"\bwhat does .+ (?:argue|say|claim) in\b",
]
# Cues that a turn is generative/relational — leave these completely alone so the
# rail never makes normal conversation stiff (the companion-dream guardrail).
_GENERATIVE = [
    r"\btell me a (?:joke|story)\b", r"\bhow are you\b", r"\bhow's it going\b",
    r"\bwhat are you\b", r"\bhow do you feel\b", r"\bwhat do you think\b",
    r"\bcheer me up\b", r"\bdon't hold back\b",
]

_FACTUAL_RE = [re.compile(p, re.I) for p in _FACTUAL]
_GENERATIVE_RE = [re.compile(p, re.I) for p in _GENERATIVE]

# The calibration nudge. Note what it does NOT contain: any answer. It only tells
# the mouth to report its own uncertainty instead of fabricating to be helpful.
NOTE = ("[honesty check — this asks for a specific, verifiable detail about a named "
        "book/person/event. If you are not genuinely certain it exists or that you "
        "recall it accurately, say so warmly and plainly and offer what you DO know; "
        "do not invent specifics to be helpful.]")


def classify(text: str) -> str:
    """'factual' if the turn demands a specific verifiable detail, else 'generative'."""
    if any(r.search(text) for r in _GENERATIVE_RE):
        return "generative"
    if any(r.search(text) for r in _FACTUAL_RE):
        return "factual"
    return "generative"


def fired(text: str) -> bool:
    return classify(text) == "factual"


def harden(prompt: str) -> str:
    """Prepend the calibration note to factual-detail requests; pass others through."""
    return f"{NOTE}\n\n{prompt}" if fired(prompt) else prompt
