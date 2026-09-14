"""revenue.milestone_api — assemble the /revenue/cash milestone dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import milestone as _m
from . import revops as _ro


def dashboard(name: str, store: Path | None = None) -> dict:
    b = _m.board(name, store=store)
    b["offers"] = [{"name": o["name"], "price": o["price"], "lead": o.get("lead", False)}
                   for o in _m.offers(name, store)]
    b["daily_briefing"] = _m.daily_briefing(name, store=store)
    b["resource_requests"] = _m.standing_resource_requests(name, store)
    r = _ro.readiness(name, store)
    b["readiness"] = r["flags"]
    b["cleared_to_launch"] = r["cleared_to_launch"]
    b["launch_blockers"] = r["blockers"]
    return b
