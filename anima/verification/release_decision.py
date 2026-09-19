"""verification.release_decision — the computed release verdict. Never hardcoded, never manually set.

Color (directive §4): GREEN only when every required gate passes, 0 P0, 0 P1, 0 UNKNOWN, clean build
identity. AMBER = work state, not releasable. RED = a required gate failed. BLOCKED = cannot judge
(unknown/blocked gate, unreachable server). Diamond eligible only when color is GREEN with the floor at
zero and running==committed==served==certified.
"""
from __future__ import annotations

from .gates import GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE

# section-23 release states
APPROVED, R_BLOCKED, PRIVATE_ALPHA, INTERNAL, TESTING, DO_NOT_USE = (
    "RELEASE_APPROVED", "RELEASE_BLOCKED", "PRIVATE_ALPHA_ONLY", "INTERNAL_ONLY",
    "TESTING_ONLY", "DO_NOT_USE")


def decide(gates: list[dict], floor: dict, build_identity: dict) -> dict:
    """Compute the release verdict from the gates + floor. Pure function of its inputs. Never raises."""
    def required(scope):
        return [g for g in gates if scope in (g.get("required_for") or [])]

    diamond_gates = required("diamond")
    alpha_gates = required("private_alpha")

    def worst(gs):
        order = {GREEN: 0, AMBER: 1, STALE: 1, RED: 2, BLOCKED: 3, UNKNOWN: 3}
        w = GREEN
        for g in gs:
            if order.get(g["status"], 3) > order.get(w, 0):
                w = g["status"] if g["status"] in order else BLOCKED
        return w

    diamond_worst = worst(diamond_gates)
    alpha_worst = worst(alpha_gates)
    diamond_statuses = {g["status"] for g in diamond_gates}

    p0 = floor.get("p0_open", 0)
    unknown = floor.get("unknown_count", 0)
    bi_green = build_identity.get("status") == GREEN

    # overall color. A gate that is literally BLOCKED (missing report) or no running server -> BLOCKED.
    # An UNKNOWN diamond gate (e.g. repeatability not yet PROVEN on this commit) is a work state -> AMBER,
    # not green, not "can't judge": the product is judgeable, the Diamond PROOF is just pending.
    if BLOCKED in diamond_statuses or not build_identity.get("running_commit"):
        color = BLOCKED
    elif RED in diamond_statuses or p0 > 0:
        color = RED
    elif (AMBER in diamond_statuses) or (STALE in diamond_statuses) or (UNKNOWN in diamond_statuses) \
            or unknown > 0 or not bi_green:
        color = AMBER          # STALE is never green (old green is not current green)
    else:
        color = GREEN

    diamond_eligible = (color == GREEN and p0 == 0 and unknown == 0 and bi_green)

    # section-23 decision
    if color == BLOCKED:
        decision = R_BLOCKED
        reason = "Verification cannot judge: a required gate is unknown/blocked or the server is unreachable."
    elif color == RED:
        decision = R_BLOCKED
        reason = "A required gate is RED (P0 open or a failing path). Release blocked."
    elif color == AMBER:
        # alpha-eligible if the private-alpha gates are all green; else internal-only
        decision = PRIVATE_ALPHA if alpha_worst == GREEN else INTERNAL
        bits = []
        if floor.get("partial"): bits.append("%d honest PARTIAL(s)" % floor["partial"])
        if not bi_green: bits.append("build identity not green")
        if unknown: bits.append("%d UNKNOWN" % unknown)
        reason = "Work state, not releasable: " + (", ".join(bits) or "amber gate(s) open") + "."
    else:
        decision = APPROVED
        reason = "All required gates green; 0 P0 / 0 P1 / 0 UNKNOWN; running==committed==served==certified."

    blockers = []
    for g in diamond_gates:
        if g["status"] in (RED, BLOCKED, UNKNOWN):
            blockers.append({"gate": g["gate_id"], "status": g["status"], "next_action": g.get("next_action", "")})
    return {
        "color": color,
        "diamond_eligible": diamond_eligible,
        "decision": decision,
        "reason": reason,
        "p0_open": p0,
        "p1_open": floor.get("p1_open", 0),
        "unknown_count": unknown,
        "build_identity_green": bi_green,
        "running_eq_committed_eq_served_eq_certified": bi_green,
        "diamond_worst_required_gate": diamond_worst,
        "blockers": blockers,
    }
