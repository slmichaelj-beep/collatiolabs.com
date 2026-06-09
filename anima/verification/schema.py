"""verification.schema — the canonical shapes of the verification objects (directive §24-26).

Pure builders + constants. Every verification object is a plain dict of this shape so it serialises
straight to the dashboard / API. No hardcoded statuses live here — callers compute them.
"""
from __future__ import annotations

GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE = "green", "amber", "red", "blocked", "unknown", "stale"
GATE_STATUSES = (GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE)
RUN_TYPES = ("smoke", "critical", "full", "diamond", "renegade")
RELEASE_STATES = ("RELEASE_APPROVED", "RELEASE_BLOCKED", "PRIVATE_ALPHA_ONLY",
                  "INTERNAL_ONLY", "TESTING_ONLY", "DO_NOT_USE")


def gate(gate_id, name, status, *, required_for=(), evidence="", blockers=None, unknowns=None,
         owner="vera/verification", next_action="", last_run=None, commit=None, link=None) -> dict:
    """A VerificationGate (§25)."""
    assert status in GATE_STATUSES, status
    return {"gate_id": gate_id, "name": name, "status": status, "required_for": list(required_for),
            "evidence": evidence, "blockers": blockers or [], "unknowns": unknowns or [],
            "owner": owner, "next_action": next_action, "last_run": last_run, "commit": commit,
            "link": link}


def blocker(blocker_id, severity, source_gate, *, required_fix="", evidence="", status="open",
            scenario=None, owner="vera/verification") -> dict:
    """A VerificationBlocker (§21)."""
    return {"blocker_id": blocker_id, "severity": severity, "source_gate": source_gate,
            "scenario": scenario, "evidence": evidence, "owner": owner, "required_fix": required_fix,
            "status": status}


def run(run_id, run_type, commit, *, branch=None, worktree=None, served_frontend_hash=None,
        results=None, release_decision=None, p0=0, p1=0, unknown=0, started_at=None,
        ended_at=None) -> dict:
    """A VerificationRun (§26)."""
    return {"verification_run_id": run_id, "run_type": run_type, "commit": commit, "branch": branch,
            "worktree": worktree, "served_frontend_hash": served_frontend_hash,
            "results": results or {}, "release_decision": release_decision,
            "p0_open": p0, "p1_open": p1, "unknown_count": unknown,
            "started_at": started_at, "ended_at": ended_at}


def founder_override(who, gate_id, why, *, risk_accepted, expires_at, required_follow_up, at=None) -> dict:
    """A FounderOverride record (§23) — the ONLY way a human may move Diamond, and it is recorded."""
    return {"who": who, "at": at, "gate": gate_id, "why": why, "risk_accepted": risk_accepted,
            "expires_at": expires_at, "required_follow_up": required_follow_up}
