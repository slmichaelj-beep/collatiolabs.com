"""market_vision.portfolio — track every opportunity from signal to venture.

Manages the opportunity lifecycle. A killed opportunity can never be advanced again; status
transitions are constrained so nothing silently jumps past validation. The portfolio view ranks
live opportunities by score and surfaces the watchlist and kill list (dead opportunities are shown,
not hidden).
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import thesis as _thesis

LIFECYCLE = ("raw_signal", "clustered", "thesis", "scored", "watch", "research", "validate",
             "validated", "commercialize_asset", "build_mvp", "launch_venture", "killed", "paused",
             "scaled")
_TERMINAL = ("killed",)


def set_status(name: str, opportunity_id: str, status: str, *, reason: str = "",
               store: Path | None = None) -> dict:
    if status not in LIFECYCLE:
        return {"ok": False, "error": "bad status %r" % status}
    opp = _thesis.get(name, opportunity_id, store)
    if opp is None:
        return {"ok": False, "error": "no such opportunity"}
    if opp.get("status") in _TERMINAL:
        return {"ok": False, "error": "opportunity is killed — cannot advance"}
    opp["status"] = status
    opp["status_reason"] = reason
    _thesis.save(name, opp, store)
    storage.emit_truth(name, "mv_opportunity", opportunity_id, "STATUS -> %s" % status,
                       actor="user", store=store)
    return {"ok": True, "opportunity": opp}


def portfolio(name: str, store: Path | None = None) -> dict:
    opps = _thesis.list_opportunities(name, store)
    def sc(o): return (o.get("score") or {}).get("total_score", 0)
    live = [o for o in opps if o.get("status") not in _TERMINAL]
    live.sort(key=sc, reverse=True)
    return {
        "ok": True, "total": len(opps),
        "by_status": {s: sum(1 for o in opps if o.get("status") == s) for s in LIFECYCLE
                      if any(o.get("status") == s for o in opps)},
        "top": [{"opportunity_id": o["opportunity_id"], "title": o["title"],
                 "score": sc(o), "recommendation": o.get("recommendation"),
                 "status": o.get("status")} for o in live[:10]],
        "watchlist": [o["title"] for o in opps if o.get("status") == "watch"],
        "validate_candidates": [o["title"] for o in opps if o.get("recommendation") == "validate"],
        "kill_list": [o["title"] for o in opps if o.get("status") == "killed"],
    }
