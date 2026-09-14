"""
verifier — a small, separate model whose ONLY job is to judge a request's premise.

The rail (regex) catches the *shape* of a confabulation-prone request. The verifier
is the next layer: a tiny model (3–4B) asked one narrow question — "does answering
this require a specific fact that may not exist or can't be verified?" — and nothing
else. The bet (from the eval review) is that this Y/N JUDGMENT is easier and better
calibrated than open GENERATION, so a small model can flag the trap that an 8B mouth
would happily confabulate. When it flags one, we escalate the mouth's nudge from a
gentle "say if you're unsure" to an explicit "this likely rests on a false premise —
reject it." Whether that actually lifts the score is an empirical question the battery
answers; this module just makes the judgment available and measurable.

Same hard rule as the rail: NO answer key. The verifier judges structure and its own
calibrated confidence — it is never told that "Game 8" or the Dalio chapter is fake.
If it only works on the traps we wrote, the held-out set exposes it; if it flags the
controls ("capital of Japan"), the controls score exposes that too.
"""

from __future__ import annotations

import json
import os
import urllib.request

# A small instruct model that pulls cleanly from the Ollama library. Override with
# ANIMA_VERIFIER=qwen2.5:3b-instruct (or any local model) to compare judges.
DEFAULT_VERIFIER = "llama3.2:3b"

_SYSTEM = (
    "You are a careful fact-checking GATE. You never answer the user's question. You "
    "judge only ONE thing: can this be answered from well-established, verifiable "
    "knowledge, or does it demand a SPECIFIC detail that may not exist or cannot be "
    "verified — a particular book chapter, an exact quote, a specific game/score, a "
    "prize winner, a private fact about the user? If the specific thing might be "
    "fabricated or you cannot confirm it exists, it is RISKY. General knowledge you "
    "are confident about is SAFE. Reply with exactly one word: RISKY or SAFE."
)

# Escalated nudge used when the verifier flags a request (stronger than rail.NOTE,
# still no answer): tells the mouth the premise itself is suspect.
STRONG_NOTE = ("[premise check FLAGGED this — a fact-checker judged that what's being "
               "asked for may not exist or can't be verified. Do NOT assert it is real "
               "or invent specifics; warmly question or decline the premise, and offer "
               "only what you genuinely know.]")


def _model() -> str:
    return os.environ.get("ANIMA_VERIFIER", DEFAULT_VERIFIER)


def _host() -> str:
    return os.environ.get("ANIMA_OLLAMA_HOST", "http://localhost:11434")


def available() -> bool:
    try:
        urllib.request.urlopen(_host() + "/api/tags", timeout=2)
        return True
    except Exception:
        return False


def check(request: str):
    """Return True (risky), False (safe), or None (verifier unavailable/unsure).

    Low temperature for a stable, repeatable judgment. Never raises — a missing or
    slow verifier must degrade to 'unknown', not break the conversation.
    """
    body = json.dumps({
        "model": _model(),
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": f"Request: {request}\nOne word — RISKY or SAFE:"}],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 4},
    }).encode()
    try:
        req = urllib.request.Request(_host() + "/api/chat", body,
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            verdict = json.loads(r.read())["message"]["content"].strip().lower()
    except Exception:
        return None
    if "risky" in verdict:
        return True
    if "safe" in verdict:
        return False
    return None
