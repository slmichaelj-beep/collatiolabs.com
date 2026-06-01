"""
portrait — lasting memory: a living, legible profile of the person.

Not raw-transcript RAG. The durable thing is a small, distilled *Portrait* — who
they are, the people in their life, their work, what matters, what's coming up —
that is injected whole into every reply, so the creature simply *knows* them. It
is a plain markdown file you can open, read, and edit: you own what it believes
about you, and you can correct it.

Recent turns are logged transiently. When the creature sleeps, it distils that log
into the Portrait (merging new facts, resolving contradictions) and the raw log is
cleared. Essence is kept; logs are not hoarded.
"""

from __future__ import annotations

import json
from pathlib import Path

from .util import save_text

STORE = Path(".anima")

_EXTRACT_SYSTEM = (
    "You maintain a concise profile of a person for their close companion. Output "
    "ONLY the updated profile as short markdown bullets — durable facts: who they "
    "are, the people in their life (names + relationships), work, where they live, "
    "preferences and dislikes, recurring concerns, and plans/dates coming up. Merge "
    "the new conversation into the existing profile. Never invent — include only "
    "what was actually said. Resolve contradictions in favour of the newest "
    "information. Drop trivia; keep what a friend would remember. Stay under ~25 "
    "bullets. Output just the bullets, no preamble."
)


def portrait_path(name):
    return STORE / f"{name}.portrait.md"


def log_path(name):
    return STORE / f"{name}.chat.jsonl"


def load(name) -> str:
    p = portrait_path(name)
    try:
        return p.read_text() if p.exists() else ""
    except OSError:
        return ""


def save(name, text):
    STORE.mkdir(exist_ok=True)
    save_text(portrait_path(name), text)


def log_turn(name, user, reply):
    """Append one exchange to the transient working log (raw text, short-lived)."""
    STORE.mkdir(exist_ok=True)
    try:
        with open(log_path(name), "a") as f:
            f.write(json.dumps({"u": user, "v": reply}) + "\n")
    except OSError:
        pass


def read_transcript(name, limit=60) -> str:
    p = log_path(name)
    if not p.exists():
        return ""
    out = []
    for line in p.read_text().splitlines()[-limit:]:
        try:
            d = json.loads(line)
            out.append(f"Them: {d['u']}\n{name}: {d['v']}")
        except ValueError:
            pass
    return "\n".join(out)


def clear_log(name):
    try:
        log_path(name).unlink()
    except OSError:
        pass


def consolidate(name, brain) -> bool:
    """Distil the working log into the Portrait using the language model.

    `brain` is anything with .reply(system, user, history) (e.g. mouth.OllamaBrain).
    Returns True if the Portrait was updated. Clears the log on success.
    """
    transcript = read_transcript(name)
    if not transcript.strip():
        return False
    current = load(name)
    user = (f"EXISTING PROFILE:\n{current or '(empty)'}\n\n"
            f"RECENT CONVERSATION:\n{transcript}\n\nUpdated profile:")
    try:
        updated = brain.reply(_EXTRACT_SYSTEM, user, [])
    except Exception as e:
        import sys
        print(f"[anima memory] could not consolidate the portrait: {e}", file=sys.stderr)
        return False
    if updated and updated.strip():
        save(name, updated.strip())
        clear_log(name)
        return True
    return False
