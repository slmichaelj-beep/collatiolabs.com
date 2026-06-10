"""resources.api — assemble the /resources dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import planner as _p


def dashboard(name: str, store: Path | None = None) -> dict:
    bn = _p.detect_bottlenecks(name, store)
    reqs = _p.requests(name, store)
    return {
        "ok": True,
        "bottlenecks": bn["bottlenecks"], "monitored": bn["total_monitored"],
        "blocked_revenue": bn["blocked_revenue"],
        "requests": [{"title": r["title"], "type": r["request_type"], "recommended": r["recommended_option"],
                      "status": r["status"]} for r in reqs],
        "next_move": ("monitor capacity to detect bottlenecks" if bn["total_monitored"] == 0 else
                      "submit the top resource request for approval (Vera never buys)"),
        "honesty": "Vera never purchases/provisions/spends; every request is approval-gated with a "
                   "business case + options; new hosts are security-scoped.",
    }
