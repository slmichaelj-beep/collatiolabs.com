"""verification.dashboard — assemble the served Verification Dashboard payload from real gates.

Top-level release status (directive §3) + the gate rows + open blockers + the computed release decision.
Everything here is computed live; nothing is hardcoded green.
"""
from __future__ import annotations

from . import build_identity, gates as gates_mod, release_decision


def data() -> dict:
    """The full dashboard payload. Computed from real reports + live build identity. Never raises."""
    try:
        g = gates_mod.compute()
        gates, floor, bi = g["gates"], g["floor"], g["build_identity"]
    except Exception as e:
        return {"error": "gate computation failed: %r" % e, "release": {"color": "blocked"}}

    fc = g.get("flake_classification") or {}
    ext = g.get("external_dependencies") or {}
    rep = g.get("repeatability")
    fresh = g.get("freshness") or {}
    blockers = g.get("blockers") or []          # computed once in gates.collect

    decision = release_decision.decide(gates, floor, bi)

    top = {
        "diamond_eligible": decision["diamond_eligible"],
        "release_state": decision["color"].upper(),
        "release_decision": decision["decision"],
        "reason": decision["reason"],
        "running_eq_committed_eq_served_eq_certified": decision["build_identity_green"],
        "unknown_user_behavior": floor.get("unknown_count", 0),
        "p0_open": decision["p0_open"],
        "p1_open": decision["p1_open"],
        "certified_commit": bi.get("certified_commit"),
        "running_commit": bi.get("running_commit"),
        "committed_commit": (bi.get("committed_commit") or "")[:12] or None,
        "served_frontend_hash": bi.get("served_frontend_hash"),
        "backend_process": bi.get("backend_process"),
        "active_worktree": bi.get("worktree"),
        "active_branch": bi.get("branch"),
        "clean_tree": bi.get("clean_tree"),
        # cert-flake hardening: no unclassified flakes, repeatability proven, dependency state visible
        "unclassified_flakes": len(fc.get("unclassified", [])),
        "harness_flakes": len(fc.get("harness_flakes", [])),
        "product_partials": len(fc.get("product_partials", [])),
        "repeatability_confirmed": bool(rep and rep.get("repeatable")),
        "repeatability_runs": (rep or {}).get("runs"),
        "stale_certs": len(fresh.get("stale_required", [])),
        "open_blockers": len(blockers),
        # the §3 summary lines for a few headline gates
        "live_user_reality": _gate_status(gates, "live_user_reality"),
        "rover_critical_journeys": _gate_status(gates, "rover_journeys"),
        "observation_bundle": "COMPLETE" if _gate_status(gates, "observation_bundle") == "green" else "INCOMPLETE",
        "last_full_verification_run": next((x["last_run"] for x in gates if x["gate_id"] == "program_reality"), None),
    }
    # the classified breakdown (distinguishes the FOUR kinds) + the EXTERNAL DEPENDENCY STATE block
    by_class = {}
    for o in fc.get("per_feature", []):
        by_class.setdefault(o["class"], []).append(o["feature"])
    classification = {
        "intentional_external_partial": by_class.get("intentional_external_partial", []),
        "env_dependency_partial": by_class.get("env_dependency_partial", []),
        "harness_flake": by_class.get("harness_flake", []),
        "product_partial": by_class.get("product_partial", []),
        "product_red": by_class.get("product_red", []),
        "unclassified": by_class.get("unclassified", []),
    }
    return {
        "top": top,
        "gates": gates,
        "floor": floor,
        "blockers": blockers,
        "decision": decision,
        "classification": classification,
        "external_dependencies": ext.get("dependencies", []),
        "repeatability": rep,
        "freshness": fresh,
        "evidence_room": g.get("evidence_room"),
        "scenario_matrix": g.get("scenario_matrix"),
        "ui_truth": g.get("ui_truth"),
        "doctrine": "No Verification Green without Live User Reality Green. No Diamond Green without "
                    "running==committed==served==certified, 0 P0, 0 P1, 0 UNKNOWN, 0 stale required certs, "
                    "0 unclassified flakes, repeatability confirmed.",
    }


def _gate_status(gates, gid):
    g = next((x for x in gates if x["gate_id"] == gid), None)
    return g["status"] if g else "unknown"


if __name__ == "__main__":
    import json
    print(json.dumps(data(), indent=2))
