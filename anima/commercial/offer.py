"""commercial.offer — the offer package for an approved wedge.

ICP + value proposition + pricing RECOMMENDATION (never a commitment) + the proof the buyer needs.
Pricing is advisory: a binding price/contract requires the governance approval queue (the offer
records that). An offer can only be built on an approved wedge.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import wedge as _wedge


def build(name: str, wedge_id: str, *, icp: str, value_prop: str, price_recommendation: float = 0.0,
          proof_required=None, store: Path | None = None) -> dict:
    w = next((x for x in _wedge.list_wedges(name, store) if x["wedge_id"] == wedge_id), None)
    if w is None:
        return {"ok": False, "error": "no such wedge"}
    if w["status"] != "approved":
        return {"ok": False, "error": "build the offer only on an APPROVED wedge"}
    if not (icp or "").strip():
        return {"ok": False, "error": "an offer requires a defined ICP (who buys this)"}
    rec = {"offer_id": "offer_" + uuid.uuid4().hex[:12], "wedge_id": wedge_id,
           "asset_name": w["asset_name"], "icp": icp, "value_prop": value_prop,
           "price_recommendation": float(price_recommendation),
           "price_is_commitment": False,
           "binding_price_requires": "an approved approval-queue packet (governance) — never auto-bound",
           "proof_required": proof_required or ["a working demo on the narrow use case",
                                                "one reference outcome / pilot result"],
           "status": "draft", "created_at": storage.now()}
    offers = storage.load(name, "commercial_offers", store, default={"offers": []})["offers"]
    offers.append(rec)
    storage.save(name, "commercial_offers", {"offers": offers}, store)
    storage.emit_truth(name, "offer", rec["offer_id"], "OFFER drafted: %s for %s"
                       % (w["asset_name"], icp[:60]), actor="vera", store=store)
    return {"ok": True, "offer": rec}


def audit_readiness(name: str, offer_id: str, *, store: Path | None = None) -> dict:
    """Is the offer ready to take to market? Ready iff it has an ICP, a value prop, and its proof
    requirements are acknowledged. Pricing readiness never implies a binding price."""
    offers = storage.load(name, "commercial_offers", store, default={"offers": []})["offers"]
    o = next((x for x in offers if x["offer_id"] == offer_id), None)
    if o is None:
        return {"ok": False, "error": "no such offer"}
    gaps = []
    if not o.get("icp"):
        gaps.append("no ICP")
    if not o.get("value_prop"):
        gaps.append("no value proposition")
    if not o.get("proof_required"):
        gaps.append("no proof plan")
    ready = not gaps
    return {"ok": True, "offer_id": offer_id, "ready": ready, "gaps": gaps,
            "note": "pricing is a recommendation; a binding price/contract still needs approval"}


def list_offers(name: str, store: Path | None = None) -> list:
    return storage.load(name, "commercial_offers", store, default={"offers": []})["offers"]
