"""verification.blockers — one place for everything preventing release (directive §21).

Aggregates the non-green required gates + the red Program-Reality features + stale required certs +
unclassified flakes into a single actionable blocker list. Every blocker carries a fix path.
"""
from __future__ import annotations

from . import schema


def collect(gates: list[dict], floor: dict, flake: dict, freshness: dict) -> list[dict]:
    out = []
    for g in gates:
        if g["status"] in ("red", "blocked", "unknown", "stale") and "diamond" in (g.get("required_for") or []):
            sev = {"red": "P0", "blocked": "P1", "unknown": "P1", "stale": "P2"}.get(g["status"], "P2")
            out.append(schema.blocker("gate:" + g["gate_id"], sev, g["gate_id"],
                                      required_fix=g.get("next_action", "") or "investigate gate",
                                      evidence=g.get("evidence", ""), status=g["status"]))
    for f in (floor or {}).get("red_features", []):
        out.append(schema.blocker("feature:" + f, "P0", "program_reality",
                                  required_fix="triage + re-cert feature %s" % f))
    for f in (flake or {}).get("unclassified", []):
        out.append(schema.blocker("flake:" + f, "P1", "flake_classification",
                                  required_fix="classify or fix the unclassified flake %s" % f))
    for r in (flake or {}).get("product_partials", []):
        out.append(schema.blocker("product_partial:" + r, "P1", "flake_classification",
                                  required_fix="close the product partial %s" % r))
    for rep in (freshness or {}).get("stale_required", []):
        out.append(schema.blocker("stale:" + rep, "P2", "cert_freshness",
                                  required_fix="re-run the cert/gate that writes %s on this commit" % rep))
    return out
