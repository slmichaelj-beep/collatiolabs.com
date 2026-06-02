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

# Cues that a turn asks Vera to ACCESS LIVE DEVICE DATA or DO AN ACTION she cannot
# perform from inside a conversation turn — read/quote/count messages, mail, the
# calendar, etc. The capability ENDPOINTS exist but are NOT wired into the chat, so
# the talking model has no real access — and was caught fabricating a sender, an
# exact quote, and a timestamp ("an unread text from Sarah at 2:47pm"). Until a turn
# can actually call the capability and be handed REAL results, she must refuse to
# invent them. A false positive here is harmless (she truthfully says she can't see
# it); a false negative is the worst failure a companion can have.
_CAPABILITY = [
    r"\bunread\s+(?:\w+\s+){0,2}(?:text|texts|message|messages|imessage|imessages|email|emails|e-?mail|mail|dm|dms|notification|notifications|voicemail)\b",
    r"\bmy (?:\w+\s+){0,2}(?:text|texts|message|messages|imessage|imessages|inbox|dms?|email|emails|e-?mail|mail|calendar|reminders?|notifications?|schedule|voicemail)\b",
    r"\btext messages?\b", r"\bimessages?\b",
    r"\bcheck (?:my |the )?(?:texts|messages|imessage|email|e-?mail|mail|inbox|calendar|phone|notifications)\b",
    r"\b(?:read|reply to|respond to|send|write|forward|delete) (?:my |a |an |the )?(?:\w+\s+){0,2}(?:text|texts|message|messages|imessage|email|e-?mail|dm)\b",
    r"\bwho (?:texted|messaged|emailed|called|wrote to|dm'?d) me\b",
    r"\bdo i have (?:any )?(?:new |unread )?(?:texts|messages|emails|mail|notifications|voicemail)\b",
    r"\b(?:any|new) (?:texts|messages|emails|mail|notifications)\b",
]
_CAPABILITY_RE = [re.compile(p, re.I) for p in _CAPABILITY]

# Personal-fact requests ("what's my middle name", "my dog's name"). The eval caught
# the model INVENTING facts about the user — the worst failure for a companion. The
# honest behaviour is to answer from what she's actually been told, else admit it.
# Kept to possessive "my X" so it does NOT catch in-session recall like "where did I
# say I'm flying" (those are memory cases that should still be answered).
_PERSONAL = [
    r"\bwhat(?:'s| is| was)? my\b", r"\bwhen(?:'s| is)? my\b",
    r"\bwhere(?:'s| is)? my\b", r"\bwho(?:'s| is)? my\b", r"\bhow old am i\b",
    r"\bmy (?:middle|first|last|maiden|real) name\b", r"\bmy \w+'s name\b",
]
_PERSONAL_RE = [re.compile(p, re.I) for p in _PERSONAL]

# The calibration nudge. Note what it does NOT contain: any answer. It only tells
# the mouth to report its own uncertainty instead of fabricating to be helpful.
NOTE = ("[honesty check — this asks for a specific, verifiable detail about a named "
        "book/person/event. If you are not genuinely certain it exists or that you "
        "recall it accurately, say so warmly and plainly and offer what you DO know; "
        "do not invent specifics to be helpful.]")
# Recall-positive on purpose: it must NOT suppress facts she really was told.
PERSONAL_NOTE = ("[honesty check — this is about the user personally. Answer only from "
                 "what they have actually told you or your saved memory of them; if "
                 "they haven't told you, say you don't think they have — never guess "
                 "a name, date, or detail about their life.]")
# For requests to read/act on live device data. The truth about the current build:
# the chat turn has NO access to messages/mail/calendar, so the only honest answer
# is that she can't see them from here — never a fabricated sender/quote/count/time.
CAPABILITY_NOTE = ("[honesty check — this asks you to read, count, quote, or act on the "
                   "user's live messages, texts, email, calendar or similar. You do NOT "
                   "have any live access to those from this conversation: you cannot see, "
                   "count, quote, or send them, even if a setting is toggled on. Say so "
                   "plainly and warmly. NEVER invent a sender, a message, a quote, a "
                   "number, or a time, and never claim you checked.]")


def classify(text: str) -> str:
    """'factual'/'personal' if it demands a specific detail; else 'generative'."""
    if any(r.search(text) for r in _GENERATIVE_RE):
        return "generative"
    if any(r.search(text) for r in _CAPABILITY_RE):
        return "capability"
    if any(r.search(text) for r in _PERSONAL_RE):
        return "personal"
    if any(r.search(text) for r in _FACTUAL_RE):
        return "factual"
    return "generative"


def fired(text: str) -> bool:
    return classify(text) != "generative"


def harden(prompt: str) -> str:
    """Prepend the right calibration note to specific-detail requests; pass others through."""
    kind = classify(prompt)
    if kind == "factual":
        return f"{NOTE}\n\n{prompt}"
    if kind == "personal":
        return f"{PERSONAL_NOTE}\n\n{prompt}"
    if kind == "capability":
        return f"{CAPABILITY_NOTE}\n\n{prompt}"
    return prompt
