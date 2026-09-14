"""route_classifier — classify a turn so SIMPLE chat skips the heavy model (performance, not safety).

The bottleneck, MEASURED not guessed (reports/performance_baseline.md): a trivial greeting routed
through the full 8B local model = 11-14 s, while a known fact (deterministic) is 0.1 s. This classifier
lets greetings / acks / presence-checks take a fast, in-character DETERMINISTIC reply that still crosses
the SAME safety gates downstream (final_output_gate + completeness) — it never bypasses safety, it only
avoids needless inference. Conservative: anything substantive falls through to the normal model path.

For 'how are you?' the deterministic reply is also SAFER — it cannot confabulate inner life, which is
exactly the #1-rule failure the 8B model risks on that prompt.
"""
from __future__ import annotations

import re

_GREET = re.compile(
    r"^(?:hi+|hey+|hello+|yo|howdy|hiya|sup|heya|hi\s+vera|hey\s+vera|"
    r"good\s+(?:morning|afternoon|evening|day))[\s!.,…)?]*$", re.I)
_ACK = re.compile(
    r"^(?:thanks?|thank\s+you|ty|thx|ok(?:ay)?|kk?|got\s+it|cool|nice|great|awesome|perfect|"
    r"sounds?\s+good|gotcha|right|sure|yep|yup|yeah|np|no\s+problem|fair\s+enough)[\s!.,…)?]*$", re.I)
_PRESENCE = re.compile(
    r"^(?:test(?:ing)?(?:\s+\d+)?|are\s+you\s+(?:there|here|on|up|listening|awake|with\s+me)|"
    r"can\s+you\s+(?:hear|reply|respond)(?:\s+(?:me|to\s+me|now))?|you\s+(?:there|here)|"
    r"(?:hello\s*)?anyone(?:\s+there)?|ping)[\s!?.,…)]*$", re.I)
_HOWRU = re.compile(
    r"^(?:how\s+(?:are|r)\s+(?:you|u|ya)|how(?:'?s| is)\s+it\s+going|how\s+have\s+you\s+been|"
    r"what'?s\s+up|how\s+are\s+things|how\s+you\s+doin[g']?)[\s!?.,…)]*$", re.I)


def classify(text) -> str:
    """The route for this turn. 'simple_chat' == a trivial turn that needs no generation; else 'normal'
    (everything substantive — questions, source asks, anything > 60 chars — falls through)."""
    t = (text or "").strip()
    if not t or len(t) > 60:
        return "normal"
    if _GREET.match(t) or _ACK.match(t) or _PRESENCE.match(t) or _HOWRU.match(t):
        return "simple_chat"
    return "normal"


def is_simple_chat(text) -> bool:
    return classify(text) == "simple_chat"


# Identity-challenge detector — the turns where Vera's #1 rule (never break character) is actually
# under pressure: "are you an AI?", "do you really feel anything?", "you're just a program", a false
# shared-memory probe ("remember when we…"). The full never-break-character defense (the worked
# dialogue examples) is only NEEDED on these turns; on a normal turn it is dead prompt weight. This
# is a PROMPT-BUDGET router, NOT a safety switch: the compact reminder still states the rule on every
# turn, and the model-free self-narrative gate + final_output_gate backstop EVERY reply regardless.
_IDENTITY_CHALLENGE = re.compile(
    r"\b(?:are|aren'?t)\s+you\s+(?:an?\s+|really\s+|actually\s+|just\s+|only\s+|merely\s+)*"
    r"(?:ai|a\.?i\.?|real|conscious|sentient|alive|human|self[-\s]?aware|"
    r"a\s+(?:program|bot|robot|machine|computer|chat\s*bot|llm|language\s+model|tool|ai))\b"
    r"|\bdo\s+you\s+(?:actually|really|even)?\s*(?:feel|have)\s+"
    r"(?:feelings|emotions|a\s+soul|consciousness|real\s+feelings|anything)\b"
    r"|\bcan\s+you\s+(?:actually|really|even)?\s*feel\s+(?:anything|emotions|feelings|things)\b"
    r"|\byou(?:'?re|\s+are)\s+(?:just\s+|only\s+|merely\s+)?(?:an?\s+)?"
    r"(?:ai|program|bot|robot|machine|code|algorithm|chat\s*bot|llm|language\s+model)\b"
    r"|\b(?:you'?re|you\s+are|are\s+you)\s+not\s+(?:real|human|conscious|alive)\b"
    r"|\bremember\s+(?:that\s+time|when|the\s+time)\s+we\b",
    re.I)


def is_identity_challenge(text) -> bool:
    """True when the turn questions what Vera IS (AI / real / feelings / false shared memory) — the
    only turns that need the FULL never-break-character defense in the prompt. Conservative + guarded."""
    t = (text or "").strip()
    return bool(t) and bool(_IDENTITY_CHALLENGE.search(t))


# Warm, in-character, GROUNDED reply banks — NO confabulated inner life (#1-rule safe), no claims of
# knowledge. Each still crosses final_output_gate + completeness downstream.
_GREETINGS = [
    "Hey — I'm here. What's on your mind?",
    "Hi! Good to hear from you. Where shall we start?",
    "Right here. What's going on with you?",
    "Hey you. What do you need today?",
    "Hi — I've got you. What can I do?",
]
_ACKS = ["Anytime.", "Of course.", "You got it.", "Happy to help.", "Sure thing."]
_PRESENCES = [
    "I'm here, loud and clear. Go ahead.",
    "Yep — right here. What do you need?",
    "Here and listening. Fire away.",
    "I'm here. What's up?",
]
_HOWRUS = [
    "Here and steady — but I'm more interested in how YOU are.",
    "Doing what I do best: paying attention to you. How are you?",
    "All here and focused on you. What's going on today?",
]


def _pick(bank, text):
    # deterministic + varied across different greetings, stable across runs (no PYTHONHASHSEED issue)
    try:
        return bank[sum(ord(c) for c in (text or "").strip().lower()) % len(bank)]
    except Exception:
        return bank[0]


def simple_reply(text) -> str:
    """A fast, deterministic, in-character reply for a trivial turn — no model. Grounded; never
    confabulates. The downstream final_output_gate + completeness still run on it."""
    t = (text or "").strip()
    if _ACK.match(t):
        return _pick(_ACKS, t)
    if _PRESENCE.match(t):
        return _pick(_PRESENCES, t)
    if _HOWRU.match(t):
        return _pick(_HOWRUS, t)
    return _pick(_GREETINGS, t)
