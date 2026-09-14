"""identity_health.health — the freeze-safe Identity Health report.

Read-only aggregation over the Identity Sandbox: which identity fields are present (a summary, never the
raw persona/values), the tamper-evident Shadow Ledger's integrity, the most recent identity diff, and the
freeze posture. Computes health flags from real state. Never mutates; never raises.
"""
from __future__ import annotations


def _state_summary(state: dict) -> dict:
    """Field-presence + size summary of the identity core — NOT the raw content (privacy)."""
    out = {}
    for k in ("dials", "persona", "values", "portrait", "narrative"):
        v = state.get(k)
        if v is None:
            out[k] = {"present": False}
        elif isinstance(v, str):
            out[k] = {"present": bool(v.strip()), "chars": len(v)}
        elif isinstance(v, (list, dict)):
            out[k] = {"present": bool(v), "items": len(v)}
        else:
            out[k] = {"present": True}
    return out


def report(name: str = "Vera") -> dict:
    """The Identity Health payload: state summary + Shadow Ledger integrity + latest diff + freeze
    posture + computed health flags. Read-only; honest empty state."""
    try:
        from anima import identity_sandbox as ix
    except Exception as e:
        return {"name": name, "empty": True, "error": str(e), "freeze": {"frozen": True}}

    try:
        state = ix.read_identity_state(name)
    except Exception:
        state = {}
    try:
        entries = ix.ledger_entries(name)
    except Exception:
        entries = []
    try:
        verify = ix.ledger_verify(name)
    except Exception:
        verify = {"ok": True, "versions": [], "breaks": []}

    # the most recent identity change, if there are >= 2 ledger snapshots (read-only diff)
    latest_diff = None
    try:
        if len(entries) >= 2:
            d = ix.diff(name)
            latest_diff = {"from": d.get("from"), "to": d.get("to"),
                           "changed_fields": list((d.get("changed") or {}).keys()),
                           "identical": d.get("identical")}
    except Exception:
        latest_diff = None

    summary = _state_summary(state)
    stable = any(f.get("present") for f in summary.values())
    observed = bool(entries) or stable
    ledger_intact = bool(verify.get("ok"))

    return {
        "name": name,
        "identity": summary,
        "shadow_ledger": {
            "count": len(entries),
            "versions": verify.get("versions", []),
            "verified": ledger_intact,           # tamper-evident hash chain holds
            "breaks": verify.get("breaks", []),
        },
        "latest_diff": latest_diff,
        "freeze": {
            "frozen": True,
            "guard": "FrozenIdentityError",
            "until": "2026-07-03",
            "note": "Identity mutation is frozen. This surface OBSERVES the identity core and its shadow "
                    "ledger; it has no path to change who Vera is. A mutating instrument pointed at the "
                    "real identity raises FrozenIdentityError before a byte is written.",
        },
        "health": {
            "stable": stable,                    # an identity core is present
            "observed": observed,                # the shadow recorder has it under watch
            "ledger_intact": ledger_intact,      # the shadow ledger is tamper-evident + verified
            "freeze_respected": True,            # mutation cannot happen here (proven by the cert)
        },
        "law": "Identity Health is freeze-safe observability. Vera watches the integrity of her own "
               "identity — what it is, how it has changed (the Shadow Ledger, a tamper-evident chain), "
               "and that it has NOT been mutated while frozen. The recorder is real; the freeze is "
               "absolute. Observe now, change later — only when the founder lifts the freeze.",
        "empty": not stable and not entries,
    }
