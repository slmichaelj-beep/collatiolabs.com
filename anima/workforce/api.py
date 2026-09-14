"""workforce.api — assemble the /workforce dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import discovery as _disc, fulfillment as _ff, operations as _ops


def dashboard(name: str, store: Path | None = None) -> dict:
    gaps = _disc.list_gaps(name, store)
    services = _ff.list_services(name, store)
    return {
        "ok": True,
        "work_gaps": [{"title": g["title"], "band": g.get("ticket_size_estimate", "unknown"),
                       "model": g.get("recommended_model", "?"), "confidence": g["confidence"]}
                      for g in gaps],
        "service_catalog": [{"name": s["name"], "price": s["price"], "status": s["status"],
                             "buyer": s["buyer"]} for s in services],
        "portfolio": _ops.portfolio(name, store),
        "briefing": _ops.chairman_briefing(name, store),
        "honesty": "no service sold without a fulfillment workflow + team; no delivery without QA; "
                   "revenue only on payment+acceptance; no spam/fake work.",
    }
