"""collatio.ip_assets — entity-level IP / asset ownership registry.

Knows which products/assets are owned by Collatio vs Lamar vs third parties. Unknown ownership
blocks a sale; mixed ownership requires review; assignment-needed creates a task; a blocked license
prevents commercialization. This complements the commercialization `ip_license` gate with the
entity-ownership question ("does Collatio actually own this to sell it?").
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from .entity import ENTITY_ID

OWNER = ("unknown", "Lamar", "Collatio Labs LLC", "third_party", "mixed")
ASSIGNMENT = ("unknown", "assigned", "needs_assignment", "not_assignable", "blocked")
COMMERCIAL_USE = ("unknown", "clear", "needs_review", "blocked")


def _all(name, store): return storage.load(name, "collatio_ip", store, default={"assets": []})["assets"]
def _save(name, a, store): storage.save(name, "collatio_ip", {"assets": a}, store)


def register_asset(name: str, *, title: str, asset_type: str, owner: str = "unknown",
                   assignment_status: str = "unknown", commercial_use_status: str = "unknown",
                   license_status: str = "unknown", store: Path | None = None) -> dict:
    rec = {"asset_id": "ipa_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID, "title": title,
           "asset_type": asset_type, "owner": owner if owner in OWNER else "unknown",
           "assignment_status": assignment_status if assignment_status in ASSIGNMENT else "unknown",
           "commercial_use_status": commercial_use_status if commercial_use_status in COMMERCIAL_USE else "unknown",
           "license_status": license_status if license_status in COMMERCIAL_USE else "unknown",
           "record_refs": [], "truth_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    return {"ok": True, "asset": rec}


def can_entity_sell(name: str, asset_id: str, *, store: Path | None = None) -> dict:
    """Entity-ownership gate for selling an asset under Collatio. Unknown/mixed/blocked all stop it."""
    rec = next((r for r in _all(name, store) if r["asset_id"] == asset_id), None)
    if rec is None:
        return {"allowed": False, "reason": "no such asset"}
    blockers = []
    if rec["owner"] == "unknown":
        blockers.append("ownership unknown — cannot sell")
    if rec["owner"] == "mixed":
        blockers.append("mixed ownership — requires review")
    if rec["owner"] == "third_party":
        blockers.append("third-party owned — not Collatio's to sell")
    if rec["assignment_status"] in ("needs_assignment", "blocked"):
        blockers.append("assignment %s" % rec["assignment_status"])
    if rec["license_status"] == "blocked" or rec["commercial_use_status"] == "blocked":
        blockers.append("license/commercial use blocked")
    needs_review = rec["owner"] == "mixed" or "needs_review" in (rec["commercial_use_status"], rec["license_status"])
    return {"allowed": not blockers, "blockers": blockers, "needs_review": needs_review}


def assets(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "assets": a,
            "needs_assignment": [r["title"] for r in a if r["assignment_status"] == "needs_assignment"],
            "unknown_ownership": [r["title"] for r in a if r["owner"] == "unknown"]}
