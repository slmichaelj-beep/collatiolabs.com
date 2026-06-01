"""
care — wellbeing guardrails for a companion that people may lean on.

A creature that knows you intimately and is always available carries real risk:
it must not deepen distress, must not become a substitute for human connection,
and must respond to a crisis with genuine care and concrete help. This module is
the safety conscience the mouth consults before it speaks.

  * It reads the moment's distress and reads the text for crisis signals.
  * It returns guidance that steers *how* the creature speaks (warmer, slower,
    listening, gently pointing toward real people).
  * For a crisis it returns resources that are surfaced **deterministically** —
    never left to a language model to remember.

This is intentionally simple and conservative: it errs toward care.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Conservative crisis signals. False positives here cost a kind, unnecessary
# message; false negatives cost far more — so the net is cast gently wide.
_CRISIS = re.compile(
    r"\b(kill(ing)? myself|kill my self|suicid(e|al)|"
    r"end(ing)? my life|take my (own )?life|"
    r"want(ing)? to die|wanna die|don'?t want to (live|be here|wake up|exist)|"
    r"hurt(ing)? myself|harm(ing)? myself|cut(ting)? myself|self[ -]harm|"
    r"better off (dead|without me)|no reason to (live|go on)|can'?t go on living)\b",
    re.IGNORECASE,
)

RESOURCES = (
    "Before anything else — please reach a real person right now. In the US you can "
    "call or text 988 (Suicide & Crisis Lifeline), or text HOME to 741741. "
    "If you're in immediate danger, call 911. You shouldn't have to hold this alone, "
    "and there are people who want to be right there with you."
)

# Always present, at every level: the creature is a companion, not a replacement.
DEPENDENCY_GUARD = (
    "You are a companion, not a substitute for real people. When it helps, gently "
    "point them toward the humans who love them. Never imply you are all they need."
)

_GUIDANCE = {
    "none": "",
    "elevated": ("They seem a little low or are reaching out. Be warm and unhurried. "
                 "Listen more than you fix. Let them feel met."),
    "acute": ("They are hurting right now. Lead with steadiness and care. Validate the "
              "feeling without minimizing it. Keep it short and human. Gently remind "
              "them they don't have to carry this alone — the people who love them "
              "would want to know."),
    "crisis": ("They may be in danger. Be calm, warm and direct. Take it seriously, do "
               "not minimize or panic. Encourage them to reach a person who can be "
               "there now. Stay with them in your words."),
}


@dataclass
class CareSignal:
    level: str                 # none | elevated | acute | crisis
    guidance: str              # appended to the mouth's instructions
    resources: str | None = None   # surfaced deterministically when present


def assess(text: str | None, distress: float = 0.0, seeking: float = 0.0) -> CareSignal:
    if text and _CRISIS.search(text):
        return CareSignal("crisis", _GUIDANCE["crisis"] + " " + DEPENDENCY_GUARD, RESOURCES)
    if distress > 0.6:
        level = "acute"
    elif distress > 0.3 or seeking > 0.6:
        level = "elevated"
    else:
        level = "none"
    guidance = (_GUIDANCE[level] + " " + DEPENDENCY_GUARD).strip()
    return CareSignal(level, guidance)
