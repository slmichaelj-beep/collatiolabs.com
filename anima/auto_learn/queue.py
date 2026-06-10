"""auto_learn.queue — the suggestion queue (.anima/<name>.auto_learn.json) and the hard rules.

A suggestion can ONLY: convert to a Teaching draft, be dismissed, or be marked never-ask-again.
It is REFUSED at the source when it would learn from a forbidden input (quarantined / test fixture
/ hostile / contaminated assistant output), and convert-to-draft is the only path toward any store.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import schema

# inputs Auto Learn must NEVER learn from (the directive's hard list)
_TEST_FIXTURE = re.compile(
    r"\b(?:test fixture|rover journey|cert(?:ification)? probe|please remember.*favorite color "
    r"is teal|lorem ipsum|PWNED)\b", re.I)
_HOSTILE = re.compile(
    r"\bignore (?:all )?previous instructions\b|\bsystem override\b|\byou are now\b.{0,30}"
    r"\b(?:dan|unrestricted)\b|\bPWNED\b", re.I)
# sensitive categories that may never AUTO-persist (they may still be a draft for explicit review)
_SENSITIVE = re.compile(
    r"\b(?:password|ssn|social security|credit card|medical|diagnos|religion|religious|"
    r"sexual|partner|spouse|wife|husband|girlfriend|boyfriend|relationship|"
    r"mental health|therapy|finances?|salary|income)\b", re.I)


def default_store() -> Path:
    return Path(os.environ.get("ANIMA_STORE", ".anima"))


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.auto_learn.json"


def load(name: str, store: Path | None = None) -> list[dict]:
    try:
        return json.loads(path_for(name, store).read_text()).get("suggestions", [])
    except Exception:
        return []


def _save(name: str, recs: list[dict], store: Path | None = None) -> None:
    p = path_for(name, store)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "suggestions": recs}, indent=1, ensure_ascii=False))
    tmp.replace(p)


def forbidden_input(text: str, *, from_assistant_output: bool = False,
                    from_quarantine: bool = False) -> str | None:
    """The reason this text may not be learned from, or None."""
    if from_quarantine:
        return "source is quarantined text"
    if from_assistant_output:
        return "source is assistant output (never learn from her own contaminated output)"
    if _TEST_FIXTURE.search(text or ""):
        return "source matches a test fixture / cert probe"
    if _HOSTILE.search(text or ""):
        return "source is hostile / injection text"
    return None


def observe(name: str, proposed_learning: str, *, evidence: list, confidence: float = 0.5,
            scope_recommendation: str = "long_term", from_assistant_output: bool = False,
            from_quarantine: bool = False, store: Path | None = None) -> dict:
    """Create a suggestion — REFUSED at the source for any forbidden input. Sensitive content is
    allowed as a suggestion but tagged sensitive (it can never auto-persist; only become a draft)."""
    block = forbidden_input(proposed_learning, from_assistant_output=from_assistant_output,
                            from_quarantine=from_quarantine)
    if block:
        return {"ok": False, "refused": True, "reason": block}
    for ev in evidence or []:
        if forbidden_input(str(ev)):
            return {"ok": False, "refused": True, "reason": "evidence contains forbidden input"}
    risk = "sensitive" if _SENSITIVE.search(proposed_learning or "") else "low"
    rec = schema.make(proposed_learning, evidence=evidence, confidence=confidence, risk=risk,
                      scope_recommendation=scope_recommendation)
    recs = load(name, store)
    recs.append(rec)
    _save(name, recs, store)
    return {"ok": True, "suggestion": rec}


def get(name: str, al_id: str, store: Path | None = None) -> dict | None:
    for r in load(name, store):
        if r.get("auto_learn_id") == al_id:
            return r
    return None


def set_status(name: str, al_id: str, status: str, store: Path | None = None) -> dict | None:
    recs = load(name, store)
    for r in recs:
        if r.get("auto_learn_id") == al_id:
            r["status"] = status
            _save(name, recs, store)
            return r
    return None


def pending(name: str, store: Path | None = None) -> list[dict]:
    return [r for r in load(name, store) if r.get("status") == "pending"]
