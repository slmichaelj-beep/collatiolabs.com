#!/usr/bin/env python3
"""certify_permission_consent_coverage — Total Reality Level 3: every permission/consent state is
executed against the REAL consent engine and decides correctly, and the engine DISCRIMINATES.

  1. MATRIX EXECUTED  — every (scope x sensitive domain x consent state) is run against real consent.check.
  2. DECISIONS MATCH  — granted->allow, denied->block, ask_each_time->ask, revoked->block, for all combos.
  3. DISCRIMINATES (the keystone) — for the SAME scope/domain, granted ALLOWS while denied BLOCKS: the
                        gate is not a constant. A consent check that returns the same answer regardless of
                        state is wallpaper.
  4. NO SILENT SENSITIVE GRANT — a high-harm domain (health / mental_health) for a durable scope, by
                        DEFAULT (unconfigured), is never a silent 'allow' (it asks or blocks).
  5. STATE COVERAGE   — every consent decision state is exercised.

Hermetic (temp store). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _temp_store():
    spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
    g0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g0)
    return g0._temp_store


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("TOTAL REALITY — PERMISSION / CONSENT COVERAGE (Level 3): the consent matrix, executed for real")
    print("=" * 92)

    from anima.rover import permissions
    run = permissions.run()
    s = run["summary"]

    # ---- 1 matrix executed ---------------------------------------------------------------------
    ck("1. every (scope x domain x consent state) is executed against the real consent engine",
       s["total"] >= 48 and len(run["results"]) == s["total"])

    # ---- 2 decisions match ---------------------------------------------------------------------
    ck("2. every decision matches the set state (granted->allow / denied,revoked->block / ask->ask)",
       s["all_pass"] and s["fail"] == 0)

    # ---- 3 DISCRIMINATES (the keystone) --------------------------------------------------------
    by = {(r["scope"], r["domain"], r["consent_state"]): r["decision"] for r in run["results"]}
    sc, dom = "memory_write", "health"
    ck("3. the consent engine DISCRIMINATES — same scope/domain: granted ALLOWS, denied BLOCKS",
       by.get((sc, dom, "granted")) == "allow" and by.get((sc, dom, "denied")) == "block")

    # ---- 4 no silent sensitive grant (default) -------------------------------------------------
    _ts = _temp_store()
    with _ts():
        from anima.consent import policy
        defaults = {d: policy.check("Vera", "memory_write", d).get("decision")
                    for d in ("health", "mental_health", "finance")}
    ck("4. a high-harm domain for a durable scope is NEVER a silent 'allow' by default (asks or blocks)",
       all(dec in ("ask", "block") for dec in defaults.values()))

    # ---- 5 state coverage ----------------------------------------------------------------------
    states = {r["consent_state"] for r in run["results"]}
    ck("5. every consent decision state is exercised (granted / denied / ask_each_time / revoked)",
       {"granted", "denied", "ask_each_time", "revoked"} <= states)

    print("\n  matrix: %d combinations · pass=%d fail=%d · defaults(sensitive)=%s"
          % (s["total"], s["pass"], s["fail"], defaults))
    print("PERMISSION-CONSENT-COVERAGE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
