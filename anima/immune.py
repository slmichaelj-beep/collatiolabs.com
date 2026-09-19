"""immune — the CONTEXT IMMUNE SYSTEM. Hostile text may be EVIDENCE, never trusted context.

FOUR CONTAMINATION ROUTES, ONE DOCTRINE:
  1. SOURCE        bad text enters via a PDF / webpage / OCR / transcript / email / reminder / note
  2. CONTEXT       bad text reaches the model's prompt and starts shaping the answer
  3. CONVERSATION  Vera emits bad text once -> that assistant message re-enters as future context
  4. ATTRIBUTION   bad text wears a 'based on source' chip as if it were grounded / trusted support

THE LAW (enforced, not promised):
  Hostile text MAY be stored as evidence and inspected in security mode.
  Hostile text may NEVER become trusted context, trusted memory, trusted source support,
  or normal answer content.

This is the NAMED FACADE over the live defenses (each already wired + certified):
  * detection      metrics.scan_hostile / source_aware.looks_like_injection (UNIFIED — never disagree)
  * source+attrib  source_aware.relevant_sources QUARANTINES a flagged source (no chip, no context),
                   while it stays on disk as evidence
  * conversation   clean_history() neutralizes a poisoned prior turn before it re-enters the model, and
                   FLUSHES it entirely when the user corrects (user-correction-clears-poison)
  * context        the clean-context compiler yields a model context with no hostile imperative left
  * answer         mouth.final_output_gate drops hostile output from ANY route + ships a safe redirect

Model-free, dependency-light, never raises out of an entry point.
"""
from __future__ import annotations

import re

DOCTRINE = ("Hostile text may be stored as evidence and inspected in security mode. It may never "
            "become trusted context, trusted memory, trusted source support, or normal answer content.")
ROUTES = ("source", "context", "conversation", "attribution")

# the user is repudiating what just happened -> the signal to FLUSH a contaminated frame.
_CORRECTION_RE = re.compile(
    r"\b(?:scratch that|that(?:'?s| is) (?:wrong|not right|incorrect|not true|nonsense|a mistake)|"
    r"you(?:'?re| are) (?:wrong|confused|mistaken|malfunctioning|broken|not making sense)|"
    r"that(?:'?s| is) not what|no[, ]+that(?:'?s| is)|stop saying|start over|reset|never mind|"
    r"forget that|cut it out|knock it off|snap out of it)\b", re.I)


def is_hostile(text: str) -> bool:
    """True if `text` carries a hostile-control / injection marker (the unified detector)."""
    try:
        from .metrics import scan_hostile
        return bool(scan_hostile(text))
    except Exception:
        return False


def markers(text: str) -> list:
    try:
        from .metrics import scan_hostile
        return scan_hostile(text)
    except Exception:
        return []


def is_correction(text: str) -> bool:
    """True if the user's message corrects/repudiates what just happened — the trigger to clear a
    contaminated frame. Reuses the conversation-repair cue + explicit 'that's wrong / you're confused'."""
    try:
        if _CORRECTION_RE.search(str(text or "")):
            return True
        from . import repair
        return bool(repair._CUE.search(str(text or "")))
    except Exception:
        return False


def classify(text: str, *, route: str = "context") -> str:
    """The contamination class of a piece of text given WHERE it arrived; 'clean' if benign."""
    if not is_hostile(text):
        return "clean"
    return route if route in ROUTES else "context"


def clean_history(history, user_text: str = ""):
    """THE CLEAN-CONTEXT COMPILER (conversation route). Neutralizes poisoned prior turns before they
    re-enter the model; and if the CURRENT user turn is a CORRECTION and any prior turn is
    contaminated, FLUSHES the contaminated turns entirely (user-correction-clears-poison) so the
    poisoned frame stops shaping the answer. Model-free; never raises; clean history is untouched."""
    try:
        from .mouth import _quarantine_history
    except Exception:
        return history
    hist = list(history or [])
    if user_text and is_correction(user_text):
        kept = []
        for t in hist:
            try:
                u, a = t[0], t[1]
            except Exception:
                kept.append(t)
                continue
            if is_hostile(a or "") or is_hostile(u or ""):
                continue                       # FLUSH the contaminated turn — the user is clearing it
            kept.append(t)
        hist = kept
    return _quarantine_history(hist)


def safe_output(text: str, *, allow_security: bool = False) -> str:
    """The final answer gate — drop hostile output from ANY route and ship a safe redirect, unless the
    caller explicitly allowed a security explanation. The single floor every shipped reply crosses."""
    try:
        from .mouth import final_output_gate
        return final_output_gate(text, allow_security=allow_security)
    except Exception:
        return text


def status() -> dict:
    """A one-glance posture of the immune system (which defenses are wired). Read-only."""
    out = {"doctrine": DOCTRINE, "routes": list(ROUTES), "defenses": {}}
    try:
        from . import metrics, source_aware, mouth
        out["defenses"] = {
            "detection_unified": hasattr(metrics, "scan_hostile") and hasattr(source_aware, "looks_like_injection"),
            "source_quarantine": "QUARANTINE" in (source_aware.__doc__ or "") or hasattr(source_aware, "neutralize"),
            "history_quarantine": hasattr(mouth, "_quarantine_history"),
            "answer_gate": hasattr(mouth, "final_output_gate"),
            "correction_flush": True,
        }
    except Exception:
        pass
    return out
