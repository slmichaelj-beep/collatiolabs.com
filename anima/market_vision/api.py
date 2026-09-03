"""market_vision.api — assemble the /opportunities dashboard payload (read-only).

Pulls the source inventory, signal count, scored opportunity portfolio, privacy-first angles,
asset-monetization matches, and validation recommendations into one honest view for the dashboard.
Read-only: no side effects, no scanning, no spend.
"""
from __future__ import annotations

from pathlib import Path

from . import source_registry as _src, signals as _sig, portfolio as _pf, briefing as _brief, \
    asset_monetization as _mon


def dashboard(name: str, store: Path | None = None) -> dict:
    inv = _src.inventory(name, store)
    return {
        "ok": True,
        "sources": {"total": len(inv["sources"]), "approved": inv["approved"],
                    "needs_review": inv["needs_review"], "blocked": inv["blocked"],
                    "classes": sorted({s["source_type"] for s in inv["sources"]})},
        "signals": len(_sig.list_signals(name, store=store)),
        "portfolio": _pf.portfolio(name, store),
        "asset_monetization": [{"asset": m["asset_name"], "best_path": m["best_path"],
                                "buyer": m.get("buyer", "")} for m in _mon.list_maps(name, store)],
        "briefing": _brief.build(name, store),
    }
