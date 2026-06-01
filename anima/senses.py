"""
The Senses — organs that turn raw life into a perception the heart can feel.

The heart never sees text, and never sees tokens. The senses' whole job is to
distil a moment of the world — the words someone said, the *tone* underneath
them, the hour, the shape of the day ahead — into a handful of continuous,
interpretable qualities: a `Perception`. Words are split only to *look up* their
felt weight in a small affect lexicon, and then discarded. What flows inward is
feeling, not language.

This encoder is deliberately tiny, transparent and on-device — a VADER-style
lexicon, not a model download. It can be upgraded later to a small embedding
encoder, but the *interface* (the Perception below) stays fixed, so the heart
never notices the organ behind it changed. Anti-swap, all the way down.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from .heart import PERCEPT_FIELDS

# A compact affect lexicon: word -> (valence in [-1, 1], arousal in [0, 1]).
# Small on purpose; it is the seed of a sense, not a dictionary.
LEXICON: dict[str, tuple[float, float]] = {
    # warmth / joy
    "love": (0.9, 0.7), "loved": (0.9, 0.6), "happy": (0.8, 0.6), "joy": (0.85, 0.7),
    "glad": (0.6, 0.4), "grateful": (0.8, 0.4), "thank": (0.6, 0.3), "thanks": (0.6, 0.3),
    "good": (0.6, 0.3), "great": (0.8, 0.6), "wonderful": (0.9, 0.6), "amazing": (0.9, 0.8),
    "calm": (0.5, 0.1), "peace": (0.6, 0.1), "peaceful": (0.6, 0.1), "rested": (0.5, 0.2),
    "hope": (0.6, 0.4), "hopeful": (0.6, 0.4), "proud": (0.7, 0.5), "safe": (0.6, 0.2),
    "excited": (0.7, 0.9), "fun": (0.7, 0.6), "smile": (0.7, 0.4), "warm": (0.6, 0.3),
    # ache / fear / anger
    "sad": (-0.7, 0.4), "down": (-0.5, 0.3), "lonely": (-0.7, 0.4), "alone": (-0.5, 0.4),
    "tired": (-0.4, 0.2), "exhausted": (-0.6, 0.3), "drained": (-0.6, 0.3),
    "afraid": (-0.6, 0.8), "scared": (-0.7, 0.8), "fear": (-0.7, 0.8), "anxious": (-0.6, 0.8),
    "worried": (-0.5, 0.7), "stress": (-0.6, 0.8), "stressed": (-0.6, 0.8),
    "overwhelmed": (-0.7, 0.8), "angry": (-0.7, 0.9), "mad": (-0.6, 0.8), "hate": (-0.85, 0.8),
    "hurt": (-0.7, 0.6), "pain": (-0.7, 0.6), "lost": (-0.6, 0.5), "broken": (-0.8, 0.5),
    "bad": (-0.6, 0.4), "terrible": (-0.8, 0.6), "awful": (-0.8, 0.6), "sick": (-0.6, 0.4),
    "sorry": (-0.3, 0.4), "miss": (-0.4, 0.5), "cry": (-0.7, 0.6), "crying": (-0.7, 0.6),
}

INTENSIFIERS = {"very", "so", "really", "extremely", "incredibly", "deeply", "totally", "absolutely"}
NEGATIONS = {"not", "no", "never", "cant", "cannot", "dont", "wont", "isnt", "arent", "nothing"}
SECOND_PERSON = {"you", "your", "youre", "u", "ur", "yourself"}
FIRST_PERSON = {"i", "im", "me", "my", "mine", "myself", "ive", "id"}
# explicit signals of acute distress, and of reaching out for connection/support
DISTRESS_WORDS = {"scared", "afraid", "terrified", "panic", "panicking", "overwhelmed",
                  "hopeless", "alone", "lonely", "breaking", "cant", "hurts", "hurting",
                  "crying", "drowning", "lost", "desperate", "anxious"}
SEEKING_WORDS = {"help", "need", "talk", "listen", "please", "tell", "stay", "here",
                 "miss", "alone", "scared", "worried", "support", "advice", "okay"}

_WORD = re.compile(r"[a-z']+")


@dataclass
class Perception:
    """One sensed moment, in the felt qualities the heart understands."""

    presence: float = 0.0      # is someone here, now, at all                  [0, 1]
    attention: float = 0.0     # is it turned toward the creature              [0, 1]
    mood: float = 0.0          # how the person seems to feel                  [-1, 1]
    intensity: float = 0.0     # how charged the moment is                     [0, 1]
    wellbeing: float = 0.5     # overall how-they-are (explicit or inferred)   [0, 1]
    load: float = 0.0          # pressure of the day ahead                     [0, 1]
    distress: float = 0.0      # acuteness of suffering in the moment          [0, 1]
    seeking: float = 0.0       # are they reaching out for connection/support  [0, 1]
    openness: float = 0.0      # how much they are disclosing / sharing        [0, 1]

    def vector(self) -> np.ndarray:
        d = self.__dict__
        return np.array([d[f] for f in PERCEPT_FIELDS], dtype=float)


def calendar_load(events, now: float) -> float:
    """Felt pressure from what's coming. events: [{'when': ts, 'weight': w}, ...]."""
    if not events:
        return 0.0
    horizon = 2 * 86400.0
    total = 0.0
    for e in events:
        delay = e["when"] - now
        if delay < 0 or delay > horizon:
            continue
        proximity = 1.0 - delay / horizon          # sooner weighs heavier
        total += e.get("weight", 1.0) * (0.4 + 0.6 * proximity)
    return float(1.0 - math.exp(-0.5 * total))     # saturating


def read(text: str | None = None, *, now: float | None = None,
         wellbeing: float | None = None, events=None, name: str | None = None) -> Perception:
    """Sense a moment into a Perception. Any of text / wellbeing / events may be given."""
    import time
    now = time.time() if now is None else now

    load = calendar_load(events, now)

    if not text or not text.strip():
        wb = 0.5 if wellbeing is None else float(np.clip(wellbeing, 0.0, 1.0))
        return Perception(presence=0.0, wellbeing=wb, load=load)

    words = _WORD.findall(text.lower())
    valences: list[float] = []
    arousals: list[float] = []
    negate = False
    for w in words:
        if w in NEGATIONS:
            negate = True
            continue
        if w in LEXICON:
            v, a = LEXICON[w]
            valences.append(-v if negate else v)
            arousals.append(a)
        if w not in INTENSIFIERS:
            negate = False  # negation only reaches the next sentiment-bearing word

    mood = float(np.clip(np.mean(valences), -1.0, 1.0)) if valences else 0.0

    # intensity: word-arousal, exclamation, and shouting
    word_arousal = float(np.mean(arousals)) if arousals else 0.0
    exclaim = min(text.count("!"), 3) / 3.0
    letters = [c for c in text if c.isalpha()]
    caps = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
    intensity = float(np.clip(0.55 * word_arousal + 0.3 * exclaim + 0.15 * caps, 0.0, 1.0))

    wordset = set(words)
    # attention: is this turned toward the creature?
    addressed = bool(wordset & SECOND_PERSON)
    named = bool(name) and name.lower() in wordset
    question = "?" in text
    attention = float(np.clip(0.35 + 0.3 * addressed + 0.4 * named + 0.2 * question, 0.0, 1.0))

    # distress: how acutely they are hurting right now
    distress = float(np.clip(0.65 * max(0.0, -mood) * (0.5 + 0.5 * intensity)
                             + 0.4 * (len(wordset & DISTRESS_WORDS) > 0), 0.0, 1.0))

    # seeking: a bid for connection or support
    first = wordset & FIRST_PERSON
    seeking = float(np.clip(0.3 * bool(first) + 0.35 * (len(wordset & SEEKING_WORDS) > 0)
                            + 0.2 * question + 0.15 * addressed, 0.0, 1.0))

    # openness: how much they are actually disclosing
    fp_density = len(first) / max(1, len(words))
    openness = float(np.clip(0.4 * min(len(words) / 25.0, 1.0) + 0.35 * min(fp_density * 4, 1.0)
                             + 0.25 * bool(valences), 0.0, 1.0))

    # wellbeing: explicit report, else read off tone and dampened by distress
    wb = (0.5 + 0.5 * mood - 0.3 * distress) if wellbeing is None else float(np.clip(wellbeing, 0.0, 1.0))

    return Perception(presence=1.0, attention=attention, mood=mood, intensity=intensity,
                      wellbeing=float(np.clip(wb, 0.0, 1.0)), load=load,
                      distress=distress, seeking=seeking, openness=openness)
