"""revenue_intelligence.api — assemble the /revenue/intelligence dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import store as _s


def dashboard(name: str, store: Path | None = None) -> dict:
    g = _s.graph(name, store)
    return {
        "ok": True,
        "graph": g,
        "lessons": _s.lessons(name, store),
        "next_move": ("record revenue events as you sell + deliver" if g["total_events"] == 0 else
                      "act on the lessons: scale offers with real cash, prepare for recurring objections"),
        "honesty": g["honesty"],
    }
