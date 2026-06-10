"""revenue.api — assemble the /revenue dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import strike as _s, truth as _t


def dashboard(name: str, store: Path | None = None) -> dict:
    wedges = _s.rank_wedges(name, store)
    return {
        "ok": True,
        "cash_wedges": [{"name": w["name"], "buyer": w["buyer"], "price_range": w["price_range"],
                         "action": w["recommended_action"], "time_to_package": w["time_to_package"]}
                        for w in wedges],
        "top_wedge": (wedges[0]["name"] if wedges else None),
        "revenue_truth": _t.board(name, store),
        "next_move": ("find immediate cash wedges" if not wedges else
                      "package the top wedge into an offer + buyer shortlist + sprint (approval-gated)"),
        "honesty": "nothing is sent or sold without approval + a ready fulfillment packet; only "
                   "collected cash counts as revenue.",
    }
