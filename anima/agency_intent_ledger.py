"""agency_intent_ledger — an append-only, local, timestamped log of every agency intent Vera proposes.

Every suggestion that enters the approval queue is first written here, so there is a permanent record
of what Vera *wanted* to do — independent of whether it was approved, rejected, or expired. Local-only
(never leaves the Mac), per-creature, never raises (a logging failure must not break the spine).
"""
from __future__ import annotations

import json
from pathlib import Path

STORE = Path(".anima")


def _path(name: str) -> Path:
    return STORE / f"{name}.agency_intents.jsonl"


def log_intent(name: str, suggestion: dict) -> dict:
    """Append a proposed intent to the per-creature ledger. Returns the suggestion unchanged."""
    try:
        STORE.mkdir(exist_ok=True)
        with _path(name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(suggestion, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return suggestion


def entries(name: str, n: int = 50) -> list:
    """The most recent proposed intents (newest last). Never raises."""
    try:
        lines = _path(name).read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-int(max(1, n)):]:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out
