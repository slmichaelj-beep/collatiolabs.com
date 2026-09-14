"""commercial.assets — the Software Asset Inventory.

Honest inventory of the software Lamar actually has. Commercial readiness is NEVER assumed: a new
asset is `needs_audit`; only an explicit readiness audit (with recorded findings) can move it to
`early` or `sellable`. No asset is ever auto-claimed sellable. This is the first stage of the
commercialization loop.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

READINESS = ("needs_audit", "not_sellable", "early", "sellable")
# the assets that genuinely exist (from the recovery matrix / repos) — seeded honestly as
# needs_audit; nothing is claimed sellable without an audit.
SEED = [
    ("Vera", "local-first personal/company intelligence layer (anima)", "active_build"),
    ("Argus", "local macOS host/network MRI (read-only observation)", "certified_v0.1"),
    ("Collatio / SU(8) tooling", "su8-predictions + cascade tooling", "research"),
    ("scriba", "notes/writing tool", "prototype"),
    ("collatiolabs.com", "site + landing", "live_site"),
]


def _all(name, store): return storage.load(name, "commercial_assets", store, default={"assets": []})["assets"]
def _save(name, a, store): storage.save(name, "commercial_assets", {"assets": a}, store)


def seed(name: str, *, store: Path | None = None) -> dict:
    existing = {a["asset_name"] for a in _all(name, store)}
    added = []
    a = _all(name, store)
    for nm, desc, maturity in SEED:
        if nm in existing:
            continue
        rec = {"asset_id": "asset_" + uuid.uuid4().hex[:12], "asset_name": nm, "description": desc,
               "maturity": maturity, "commercial_readiness": "needs_audit",
               "audit_findings": None, "created_at": storage.now()}
        a.append(rec)
        added.append(nm)
        storage.emit_truth(name, "commercial_asset", rec["asset_id"], "ASSET inventoried: " + nm,
                           actor="user", store=store)
    _save(name, a, store)
    return {"ok": True, "added": added, "total": len(a)}


def add_asset(name: str, asset_name: str, description: str, *, maturity: str = "unknown",
              store: Path | None = None) -> dict:
    rec = {"asset_id": "asset_" + uuid.uuid4().hex[:12], "asset_name": asset_name,
           "description": description, "maturity": maturity,
           "commercial_readiness": "needs_audit", "audit_findings": None,
           "created_at": storage.now()}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    return {"ok": True, "asset": rec}


def audit_readiness(name: str, asset_id: str, *, readiness: str, findings: str,
                    store: Path | None = None) -> dict:
    """Move an asset off needs_audit ONLY with explicit findings. 'sellable' requires non-empty
    findings (no asset is claimed sellable on a hunch)."""
    if readiness not in READINESS:
        return {"ok": False, "error": "bad readiness %r" % readiness}
    if readiness in ("early", "sellable") and not (findings or "").strip():
        return {"ok": False, "error": "advancing readiness requires recorded audit findings"}
    a = _all(name, store)
    for r in a:
        if r["asset_id"] == asset_id:
            r["commercial_readiness"] = readiness
            r["audit_findings"] = findings
            _save(name, a, store)
            storage.emit_truth(name, "commercial_asset", asset_id,
                               "ASSET audited: %s -> %s" % (r["asset_name"], readiness),
                               actor="user", store=store)
            return {"ok": True, "asset": r}
    return {"ok": False, "error": "no such asset"}


def inventory(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "assets": a,
            "counts": {k: sum(1 for x in a if x["commercial_readiness"] == k) for k in READINESS
                       if any(x["commercial_readiness"] == k for x in a)},
            "sellable": [x["asset_name"] for x in a if x["commercial_readiness"] == "sellable"],
            "needs_audit": [x["asset_name"] for x in a if x["commercial_readiness"] == "needs_audit"]}
