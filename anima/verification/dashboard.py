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

    decision = release_decision.decide(gates, floor, bi)

    # open blockers: every non-green required gate + the red feature list
    blockers = []
    for gate in gates:
        if gate["status"] in ("red", "blocked", "unknown") and "diamond" in (gate.get("required_for") or []):
            blockers.append({"blocker_id": "gate:" + gate["gate_id"], "severity": "P0" if gate["status"] == "red" else "UNKNOWN",
                             "source_gate": gate["gate_id"], "status": gate["status"],
                             "required_fix": gate.get("next_action", ""), "evidence": gate.get("evidence", "")})
    for f in floor.get("red_features", []):
        blockers.append({"blocker_id": "feature:" + f, "severity": "P0", "source_gate": "program_reality",
                         "status": "red", "required_fix": "triage + re-cert feature %s" % f, "evidence": ""})

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
    }
    return {
        "top": top,
        "gates": gates,
        "floor": floor,
        "blockers": blockers,
        "decision": decision,
        "doctrine": "No Verification Green without Live User Reality Green. No Diamond Green without "
                    "running==committed==served==certified, 0 P0, 0 P1, 0 UNKNOWN.",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(data(), indent=2))
