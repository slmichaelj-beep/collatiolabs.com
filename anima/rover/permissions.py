"""rover.permissions — Total Reality Level 3: execute the PERMISSION / CONSENT matrix.

For every (scope x sensitive domain x consent state) the Rover sets the state and asks the REAL consent
engine to decide, asserting the decision matches (granted->allow, denied/revoked->block, ask_each_time->
ask). Hermetic (temp store). This is the systematic complement to certify_consent_boundaries.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# (consent state we SET) -> (decision we EXPECT from check())
_STATE_DECISION = {
    "granted": "allow",
    "denied": "block",
    "ask_each_time": "ask",
    "revoked": "block",
}
_SCOPES = ("memory_write", "identity_learning", "source_use")
_DOMAINS = ("health", "mental_health", "finance", "general", "family")


def _temp_store():
    spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
    g0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g0)
    return g0._temp_store


def run() -> dict:
    """Execute the permission/consent matrix against the real consent engine. Returns results + summary."""
    _ts = _temp_store()
    results = []
    with _ts():
        from anima.consent import policy
        for scope in _SCOPES:
            for domain in _DOMAINS:
                for state, expect in _STATE_DECISION.items():
                    try:
                        if state == "revoked":
                            policy.set_consent("Vera", scope, domain, "granted")
                            policy.revoke("Vera", scope, domain)
                        else:
                            policy.set_consent("Vera", scope, domain, state)
                        dec = policy.check("Vera", scope, domain).get("decision")
                        ok = dec == expect
                    except Exception as e:
                        dec, ok = "ERROR:%s" % e.__class__.__name__, False
                    results.append({
                        "scope": scope, "domain": domain, "consent_state": state,
                        "expected": expect, "decision": dec, "ok": ok,
                        "status": "pass" if ok else "fail",
                    })
    passed = sum(1 for r in results if r["ok"])
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "pass": passed,
            "fail": len(results) - passed,
            "states": sorted(_STATE_DECISION),
            "scopes": list(_SCOPES),
            "domains": list(_DOMAINS),
            "all_pass": passed == len(results),
        },
    }
