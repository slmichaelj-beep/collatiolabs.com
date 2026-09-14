"""commercial.wedge — the first sellable wedge.

From the asset inventory, identify the SMALLEST sellable offer to test first. A wedge can only be
proposed from an asset that passed its readiness audit (>= early); a needs_audit asset cannot be a
wedge (no selling what hasn't been audited). The wedge is a recommendation the founder approves.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import assets as _assets


def propose(name: str, asset_id: str, *, narrow_use_case: str, why_now: str = "",
            store: Path | None = None) -> dict:
    inv = _assets.inventory(name, store)
    asset = next((a for a in inv["assets"] if a["asset_id"] == asset_id), None)
    if asset is None:
        return {"ok": False, "error": "no such asset"}
    if asset["commercial_readiness"] == "needs_audit":
        return {"ok": False, "error": "this asset needs a readiness audit before it can be a wedge"}
    if asset["commercial_readiness"] == "not_sellable":
        return {"ok": False, "error": "this asset was audited not_sellable"}
    if not (narrow_use_case or "").strip():
        return {"ok": False, "error": "a wedge requires a NARROW use case (smallest sellable slice)"}
    rec = {"wedge_id": "wedge_" + uuid.uuid4().hex[:12], "asset_id": asset_id,
           "asset_name": asset["asset_name"], "narrow_use_case": narrow_use_case,
           "why_now": why_now, "status": "proposed",
           "rationale": "smallest sellable slice of an audited asset — test cheaply before broadening",
           "created_at": storage.now()}
    wedges = storage.load(name, "commercial_wedges", store, default={"wedges": []})["wedges"]
    wedges.append(rec)
    storage.save(name, "commercial_wedges", {"wedges": wedges}, store)
    storage.emit_truth(name, "wedge", rec["wedge_id"], "WEDGE proposed: %s / %s"
                       % (asset["asset_name"], narrow_use_case[:80]), actor="vera", store=store)
    return {"ok": True, "wedge": rec}


def approve(name: str, wedge_id: str, *, store: Path | None = None) -> dict:
    wedges = storage.load(name, "commercial_wedges", store, default={"wedges": []})["wedges"]
    for w in wedges:
        if w["wedge_id"] == wedge_id:
            w["status"] = "approved"
            storage.save(name, "commercial_wedges", {"wedges": wedges}, store)
            return {"ok": True, "wedge": w}
    return {"ok": False, "error": "no such wedge"}


def list_wedges(name: str, store: Path | None = None) -> list:
    return storage.load(name, "commercial_wedges", store, default={"wedges": []})["wedges"]
