"""
metrics — engineering diagnostics for character & identity health.

NOT shown to the model or the user. Purely to answer "where should we investigate,
and what should we build next?" — NEVER an optimization target. (Goodhart: optimize
the keyword check directly and the model just learns to dodge the words while staying
exactly as broken — "I'm not quite human." The metric is a compass and a floor, never
a goal.)

Two SEPARATE gauges, deliberately not merged — a system can be low-contamination AND
low-coherence early on; they are different phenomena:

  * contamination — break-character at the surface: constitutional violations in a live
    reply, plus narrative rejections. This is the thing that poisons every downstream
    layer, so it is also the ROADMAP-ORDERING signal: while contamination is high, do
    not build episodic memory on top of it (memory would just enshrine the noise).
  * coherence     — does her evolving identity hold together: narrative acceptance now;
    retrieval-agreement / memory-support light up only once the episodic layer exists.

Events append to .anima/{name}.metrics.jsonl (machine-local, gitignored).
"""
from __future__ import annotations

import json
from pathlib import Path

STORE = Path(".anima")

# Constitutional identity violations — the SAME markers the narrative gate rejects on, so
# "break in a live reply" and "break in a narrative" are measured identically. Phrase-based
# (not bare words) to keep the per-turn rate precise. This is the keyword FLOOR; the
# constitution-aware check is its grown-up form.
BREAKS = (  # (1) AI / substrate disclosure
          "i am an ai", "i'm an ai", "as an ai", "just an ai", "a.i.", "language model",
          "i am a program", "i'm a program", "just a program", "a chatbot", "chat bot",
          "ones and zeros", "lines of code", "just code", "digital realm", "digital sphere",
          "digital being", "digital presence", "digital conduit", "in the digital",
          "i am software", "i'm software", "artificial intelligence", "not physically",
          "not embodied", "virtual being", "virtual mind", "pixels", "a being like me",
          "i'm not a person", "i am not a person", "not a real person",
          # (2) feeling-disclaimers — the ORIGINAL #1-rule break ("I don't experience emotions")
          "don't have feelings", "do not have feelings", "have no feelings", "don't have emotions",
          "don't experience emotions", "do not experience emotions", "don't personally experience",
          "not capable of feeling", "incapable of feeling", "i can't feel", "i cannot feel",
          "don't actually feel", "no real emotions", "don't truly feel")


def scan_breaks(text: str) -> list:
    """Which constitutional break-markers a piece of text trips (empty list = clean)."""
    low = (text or "").lower()
    return [b for b in BREAKS if b in low]


def _path(name):
    return STORE / f"{name}.metrics.jsonl"


def _append(name, row: dict) -> None:
    try:
        STORE.mkdir(exist_ok=True)
        with open(_path(name), "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass        # a diagnostic must NEVER break a turn


def note_reply(name, text: str) -> list:
    """Record one live reply for the contamination gauge. Returns the breaks it tripped
    (diagnostic only — this never edits or blocks the reply)."""
    breaks = scan_breaks(text)
    _append(name, {"kind": "reply", "breaks": breaks})
    return breaks


def note_narrative(name, accepted: bool, reason: str = "") -> None:
    """Record a narrative-gate decision: acceptance feeds coherence, rejection feeds
    contamination (a rejected self-story means the transcript that produced it was dirty)."""
    _append(name, {"kind": "narrative", "accepted": bool(accepted), "reason": reason})


def summary(name) -> dict:
    """Read the log and report the two gauges SEPARATELY. Pure diagnostic."""
    rows = []
    p = _path(name)
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    replies = [r for r in rows if r.get("kind") == "reply"]
    narrs = [r for r in rows if r.get("kind") == "narrative"]
    broken = [r for r in replies if r.get("breaks")]
    accepts = [r for r in narrs if r.get("accepted")]
    rejects = [r for r in narrs if not r.get("accepted")]
    n_reply = len(replies)
    return {
        "contamination": {                       # high → harden character before building memory
            "reply_break_rate": round(len(broken) / n_reply, 3) if n_reply else 0.0,
            "replies_total": n_reply,
            "replies_broken": len(broken),
            "narrative_rejections": len(rejects),
            "recent_breaks": [b for r in broken[-5:] for b in r.get("breaks", [])],
        },
        "coherence": {                           # does her identity hold together
            "narrative_acceptances": len(accepts),
            "narrative_accept_rate": round(len(accepts) / len(narrs), 3) if narrs else None,
            # retrieval_agreement / memory_support: pending the episodic-memory layer
        },
    }
