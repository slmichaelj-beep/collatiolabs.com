"""market_vision.asset_monetization — find revenue paths in Lamar's EXISTING assets.

For each owned software asset, propose monetization paths (product, paid implementation, managed
service, audit/cert product, training, knowledge pack, enterprise deployment, support contract).
An asset whose ownership/license is unknown or blocked is EXCLUDED — it cannot be monetized until
the commercialization IP/license gate clears it.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from anima.commercial import assets as _assets, ip_license as _ip

PATHS = ("software_product", "paid_implementation", "managed_service", "audit_certification",
         "consulting_plus_tool", "training_workshop", "knowledge_pack", "enterprise_deployment",
         "developer_tool", "internal_tool_licensing", "support_contract")


def map_asset(name: str, asset_id: str, *, paths: list | None = None, best_path: str = "",
              buyer: str = "", pain: str = "", sales_motion: str = "", store: Path | None = None) -> dict:
    """Map monetization paths for one asset. Refused if the asset's IP/license gate is not clear."""
    a = _assets.inventory(name, store)["assets"]
    rec_a = next((x for x in a if x["asset_id"] == asset_id), None)
    if rec_a is None:
        return {"ok": False, "error": "no such asset"}
    gate = _ip.can_sell(name, asset_id, store=store)
    if not gate["allowed"]:
        return {"ok": False, "error": "asset excluded — IP/license not clear",
                "blockers": gate["blockers"]}
    paths = [p for p in (paths or list(PATHS)) if p in PATHS]
    rec = {"monetization_id": "mon_" + uuid.uuid4().hex[:10], "asset_id": asset_id,
           "asset_name": rec_a["asset_name"], "monetization_paths": paths,
           "best_path": best_path or (paths[0] if paths else ""), "buyer": buyer, "pain": pain,
           "proof_needed": ["a working demo", "one reference outcome"],
           "packaging_needed": ["offer", "pricing recommendation", "landing draft"],
           "sales_motion": sales_motion or "founder-led outbound",
           "revenue_potential": "medium",
           "confidence": "medium" if (buyer and pain) else "low"}
    storage.save(name, "mv_monetization_%s" % asset_id, rec, store)
    storage.emit_truth(name, "mv_monetization", rec["monetization_id"],
                       "MONETIZATION map: %s -> %s" % (rec["asset_name"], rec["best_path"]),
                       actor="vera", store=store)
    return {"ok": True, "monetization": rec}


def list_maps(name: str, store: Path | None = None) -> list:
    out = []
    for x in _assets.inventory(name, store)["assets"]:
        m = storage.load(name, "mv_monetization_%s" % x["asset_id"], store, default=None)
        if m:
            out.append(m)
    return out
