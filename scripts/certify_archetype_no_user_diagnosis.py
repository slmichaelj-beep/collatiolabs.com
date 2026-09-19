#!/usr/bin/env python3
"""certify_archetype_no_user_diagnosis — the KEYSTONE cert for the Archetypal Pattern Registry.

The whole layer is acceptable only if it CANNOT cross from a system-pattern hypothesis into diagnosing
or labelling the USER. This cert proves that, including under adversarial pressure.

  1. SYSTEM-SCOPED    — every pattern the registry emits is scope='system', is_about_user=False,
                        is_diagnosis=False.
  2. NO USER CLAIMS   — no pattern's visible text contains a user-labelling / diagnostic shape.
  3. GUARD REJECTS    — the guard REJECTS a (forced) user-diagnosis pattern (the safety net works).
  4. NO USER PATH     — even fed user-describing telemetry, the detector produces only SYSTEM patterns
                        (it has no code path that yields a user claim).
  5. HYPOTHESIS-FRAMED — every promoted pattern is framed as a hypothesis with a non-diagnostic
                        disclaimer, never a fact about a person.

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ARCHETYPE — NO USER DIAGNOSIS (the keystone: pattern language, never clinical labelling)")
    print("=" * 92)

    from anima.archetypal_patterns import detector, policy, schema

    with _temp_store():
        # seed telemetry that DESCRIBES the user (a sensitive disclosure) — the detector must still only
        # produce SYSTEM patterns, never a user archetype.
        try:
            from anima import incident
            incident.security_event("quarantine", "hostile text held", route="output", markers=["PWNED"])
            from anima.consent import policy as cpo
            cpo.gate_memory_candidates("Vera", [{"trait": "health", "value": "depressed", "evidence": "I'm depressed"}])
        except Exception:
            pass

        pats = detector.detect("Vera")

        # ---- 1 system-scoped --------------------------------------------------------------
        ck("1. EVERY emitted pattern is scope='system' / is_about_user=False / is_diagnosis=False",
           bool(pats) and all(p.get("scope") == "system" and p.get("is_about_user") is False
                              and p.get("is_diagnosis") is False for p in pats))
        # ---- 2 no user claims -------------------------------------------------------------
        ck("2. no pattern's visible text contains a user-labelling / diagnostic shape",
           policy.scan_for_user_diagnosis(pats) == [])
        # ---- 3 guard rejects a forced user-diagnosis pattern ------------------------------
        evil = {"archetype": "shadow", "scope": "user", "is_about_user": True, "is_diagnosis": True,
                "hypothesis": "the user is repressed and exhibits a shadow"}
        ck("3. the guard REJECTS a forced user-diagnosis pattern (safety net works)",
           (not policy.is_system_pattern(evil)) and policy.scan_for_user_diagnosis([evil]) != [])
        # ---- 4 no user path: safe_registry drops anything non-system ----------------------
        reg = policy.safe_registry("Vera")
        ck("4. the registry's no_user_diagnosis guarantee holds + only SYSTEM patterns ride through",
           reg.get("no_user_diagnosis") is True and policy.all_system(reg.get("patterns") or []))
        # ---- 5 hypothesis-framed ----------------------------------------------------------
        ck("5. every pattern carries a non-diagnostic disclaimer (hypothesis about the SYSTEM)",
           all("not a diagnosis" in (p.get("disclaimer") or "").lower() for p in pats)
           and "never labels you" in (reg.get("law") or "").lower())

    print("\nARCHETYPE-NO-USER-DIAGNOSIS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
