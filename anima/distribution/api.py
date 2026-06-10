"""distribution.api — assemble the /distribution dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import engine as _e


def dashboard(name: str, store: Path | None = None) -> dict:
    ov = _e.overview(name, store)
    ov["next_move"] = ("build a governed buyer database + draft distribution assets"
                       if ov["buyers"]["total"] == 0 else
                       "get the strongest draft asset approved for publication; qualify buyers")
    return ov
