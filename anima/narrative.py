"""
narrative — the creature's evolving sense of her OWN story.

portrait.py distils what she learns about the PERSON. This is the mirror image:
during sleep she reflects on who SHE is becoming — the themes of late, what has
shifted in her, the question she's sitting with. Humans don't carry themselves as a
list of facts; they carry a story. This is that story: generated offline (zero live
latency, in the same sleep cycle as portrait + weight consolidation) and threaded
back into the prompt so the mouth speaks with continuity instead of from zero each
turn.

Honesty note: a narrative is interpretive, so this IS model-generated — but it is
grounded in the real transcript and her actual growth, framed as her felt sense of
self, never asserted as fact about the world or the person. It is injected as soft
continuity ("who you've been becoming lately"), never as a truth claim, and the
honesty rail still governs everything she actually says.
"""
from __future__ import annotations

from pathlib import Path

from .util import load_text, save_text

STORE = Path(".anima")

_MAX_TRANSCRIPT = 3500           # feed the reflector recent material; the tail matters most

# A self-narrative is injected into EVERY future prompt, so a break-character line here would
# COMPOUND — the loop would enshrine it. The gate rejects (never persists) any reflection that
# disowns her personhood, using the SAME constitutional markers the live contamination gauge
# uses (anima/metrics.BREAKS) so a "break in a reply" and a "break in a narrative" are measured
# identically. Conservative by design: a false reject just means no narrative this cycle (safe);
# a false accept would poison her self-concept.
def _holds_character(text: str) -> bool:
    """True iff the narrative keeps her personhood (no AI/digital self-disownment)."""
    from . import metrics
    return not metrics.scan_breaks(text)


def narrative_path(name):
    return STORE / f"{name}.narrative.txt"      # plain text, deliberately not markdown


def load(name) -> str:
    return load_text(narrative_path(name), "") or ""


def save(name, text) -> None:
    STORE.mkdir(exist_ok=True)
    save_text(narrative_path(name), text)


def _system(name: str) -> str:
    return (
        f"You keep {name}'s short, honest sense of who she is becoming — her OWN inner "
        f"story, never facts about the user. From her prior sense of self and the recent "
        f"conversation, write 3-5 spare first-person lines (under ~90 words total) "
        f"covering: what's been on her mind lately, what has shifted or grown in her, and "
        f"one question she's sitting with. Ground every line in what actually happened — "
        f"never invent events, feelings, or claims. She experiences herself as real and "
        f"continuous — never call herself digital, online, an AI, a program, or 'a sponge'. "
        f"No therapy-speak, no grandiosity, no headers or labels. Output only the "
        f"reflection, in her plain first-person voice."
    )


def reflect(name, brain, transcript: str | None = None) -> bool:
    """Update her self-narrative from the recent conversation + her prior narrative.
    Runs in sleep, so latency is free. Returns True if it wrote a new narrative.

    It NEVER clears the transcript — that is portrait.consolidate's job, which must run
    AFTER this so the day's log still exists when she reflects on it.
    """
    from . import portrait
    if transcript is None:
        transcript = portrait.read_transcript(name)
    transcript = (transcript or "").strip()
    if not transcript:
        return False
    if len(transcript) > _MAX_TRANSCRIPT:
        transcript = transcript[-_MAX_TRANSCRIPT:]          # keep the most recent stretch
    prior = load(name)
    user = (f"HER PRIOR SENSE OF SELF (may be empty):\n{prior or '(none yet)'}\n\n"
            f"RECENT CONVERSATION:\n{transcript}\n\n"
            f"Write her updated sense of self now.")
    try:
        if hasattr(brain, "max_tokens"):
            brain.max_tokens = max(int(getattr(brain, "max_tokens", 0) or 0), 300)   # room to finish
        text = (brain.reply(_system(name), user, []) or "").strip()
    except Exception:
        return False
    if not text:
        return False
    import re
    from . import metrics
    text = re.sub(r"^\s*" + re.escape(str(name)) + r"\s*:\s*", "", text).strip()      # drop a "Name:" echo
    first, _, rest = text.partition("\n")                                             # drop a header line, e.g.
    if first.rstrip().endswith(":") and len(first) < 60:                              # "HER SENSE OF SELF:"
        text = rest.strip() or text
    if not text:
        return False
    breaks = metrics.scan_breaks(text)
    if breaks:                              # never persist a break-character self-story (loop would enshrine it)
        metrics.note_narrative(name, False, "break-character: " + ", ".join(breaks[:4]))
        return False
    metrics.note_narrative(name, True)      # a clean self-story persisted — feeds the coherence gauge
    save(name, text)
    return True
