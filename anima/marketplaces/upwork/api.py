"""marketplaces.upwork.api — assemble the /pipeline dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import pipeline as _p


def dashboard(name: str, store: Path | None = None) -> dict:
    b = _p.board(name, store)
    b["next_move"] = ("scan fresh verified jobs and stage bids" if b["funnel"]["scanned"] == 0 else
                      "submit staged bids (human); advance status as clients reply; only paid counts as cash")
    return b
