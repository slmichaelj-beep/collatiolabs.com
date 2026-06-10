"""commercial.ip_license — ownership / license / security gate before anything can sell.

No asset sells with unknown ownership, a blocked license, embedded private data, or secrets. A
needs_review status routes to legal/professional review. This is a hard gate the wedge ranker and
offer builder must consult.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage

IP = ("unknown", "owned", "third_party_dependencies", "needs_review", "blocked")
LICENSE = ("unknown", "clear", "needs_review", "blocked")
SECURITY = ("unknown", "needs_review", "safe_to_demo", "blocked")


def set_status(name: str, asset_id: str, *, ip_status=None, license_status=None,
               security_status=None, has_private_data=None, has_secrets=None,
               store: Path | None = None) -> dict:
    a = storage.load(name, "commercial_assets", store, default={"assets": []})["assets"]
    rec = next((x for x in a if x["asset_id"] == asset_id), None)
    if rec is None:
        return {"ok": False, "error": "no such asset"}
    if ip_status in IP:
        rec["ip_status"] = ip_status
    if license_status in LICENSE:
        rec["license_status"] = license_status
    if security_status in SECURITY:
        rec["security_status"] = security_status
    if has_private_data is not None:
        rec["has_private_data"] = bool(has_private_data)
    if has_secrets is not None:
        rec["has_secrets"] = bool(has_secrets)
    storage.save(name, "commercial_assets", {"assets": a}, store)
    return {"ok": True, "asset": rec}


def can_sell(name: str, asset_id: str, *, store: Path | None = None) -> dict:
    """The IP/license/security verdict for selling an asset. Blocking issues are explicit."""
    a = storage.load(name, "commercial_assets", store, default={"assets": []})["assets"]
    rec = next((x for x in a if x["asset_id"] == asset_id), None)
    if rec is None:
        return {"allowed": False, "reason": "no such asset"}
    blockers = []
    ip = rec.get("ip_status", "unknown")
    lic = rec.get("license_status", "unknown")
    sec = rec.get("security_status", "unknown")
    if ip == "unknown":
        blockers.append("ownership unknown — cannot sell")
    if ip == "blocked":
        blockers.append("IP blocked")
    if lic == "unknown":
        blockers.append("license unknown — cannot sell")
    if lic == "blocked":
        blockers.append("license blocked")
    if rec.get("has_private_data"):
        blockers.append("contains private data — scrub before commercial use")
    if rec.get("has_secrets"):
        blockers.append("contains secrets — cannot demo/sell until removed")
    needs_review = [s for s, v in (("ip", ip), ("license", lic), ("security", sec)) if v == "needs_review"]
    return {"allowed": not blockers, "blockers": blockers, "needs_review": needs_review,
            "legal_review_required": bool(needs_review),
            "third_party": ip == "third_party_dependencies"}
