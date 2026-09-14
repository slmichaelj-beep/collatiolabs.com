"""company.release_tracker — release-tier truth, as an operator reads it.

Derived from the live verification gates / release_tiers (the same source the dashboard uses), so
the company tracker and the dashboard can never disagree. Deferred / not-claimed / enterprise-only
are separated and never counted as blockers of a lower tier.
"""
from __future__ import annotations

import json
import urllib.request


def _verification_json() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/verification.json", timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def state() -> dict:
    vj = _verification_json()
    tiers = vj.get("release_tiers", [])
    cls = vj.get("classification", {})
    out = []
    for t in tiers:
        out.append({
            "tier": t.get("label") or t.get("name") or t.get("tier"),
            "status": t.get("color") or t.get("status"),
            "diamond_eligible": t.get("diamond_eligible"),
            "passed_gates": t.get("passed_gates", []),
            "failed_gates": t.get("failed_gates", []),
            "missing_evidence": t.get("missing_evidence", []),
            "blocking": t.get("blocked_by") or t.get("blocking_items") or [],
            "not_claimed": t.get("not_claimed", []),
        })
    return {
        "ok": bool(vj),
        "tiers": out,
        "deferred_not_claimed": cls.get("deferred_not_claimed", []),
        "enterprise_only": cls.get("enterprise_only_partial", []),
        "product_red": cls.get("product_red", []),
        "product_partial": cls.get("product_partial", []),
        "unclassified": cls.get("unclassified", []),
        "highest_green": next((t["tier"] for t in out if (t["status"] == "green")), "none yet"),
    }
