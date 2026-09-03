"""revenue_swarm.api — assemble the /revenue/swarm dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import factory as _f, portfolio as _p


def dashboard(name: str, store: Path | None = None) -> dict:
    exps = _f.list_experiments(name, store)
    return {
        "ok": True,
        "experiments": [{"hypothesis": e["hypothesis"], "method": e["method"], "status": e.get("status"),
                         "budget": e["budget"], "recommendation": (e.get("recommendation") or {}).get("action")}
                        for e in exps],
        "portfolio": _p.portfolio(name, store),
        "next_move": ("create revenue experiments from opportunities/offers" if not exps else
                      "approve the worth-running experiments; kill no-signal; scale only with proof"),
        "honesty": "every experiment has kill criteria + budget + approval; scale needs demand+margin+"
                   "capacity proof; pipeline is not cash.",
    }
