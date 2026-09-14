"""trust.api — assemble the /trust dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import moat as _m


def dashboard(name: str, store: Path | None = None) -> dict:
    ov = _m.overview(name, store)
    ov["next_move"] = ("build the proof library: link each offer claim to evidence + QA/delivery receipts"
                       if not ov["proofs"] else
                       "refresh stale proof; collect permissioned outcomes for case studies")
    return ov
