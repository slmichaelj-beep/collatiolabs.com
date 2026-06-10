"""compounding.api — assemble the /compounding dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import allocator as _a, growth as _g


def dashboard(name: str, store: Path | None = None) -> dict:
    allocs = _a.allocations(name, store)
    watch = _g.acquisition_watchlist(name, store)
    return {
        "ok": True,
        "allocations": [{"workstream": a["workstream_id"], "action": a["action"], "reason": a["reason"]}
                        for a in allocs],
        "scale_recommendations": [a["workstream_id"] for a in allocs if a["action"] == "scale"],
        "kill_recommendations": [a["workstream_id"] for a in allocs if a["action"] == "kill"],
        "acquisition_watch": [{"candidate": w["candidate"], "rationale": w["strategic_rationale"],
                               "outreach": w["outreach_status"]} for w in watch],
        "next_move": ("allocate effort/capital across the revenue portfolio once workstreams have "
                      "collected-cash evidence" if not allocs else
                      "fund winners, kill losers, automate/productize repeatable streams (approval-gated)"),
        "honesty": "nothing scales without margin + quality + capacity; no investment without "
                   "approval; acquisition is research-only; legal/financial action is human-only.",
    }
