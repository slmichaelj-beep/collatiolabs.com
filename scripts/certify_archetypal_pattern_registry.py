#!/usr/bin/env python3
"""certify_archetypal_pattern_registry — the Archetypal Pattern Registry (an enhancement to the
Pattern -> Improvement loop, Human Operating Layer L10) is REAL: it
recognises SYSTEM archetype patterns from real telemetry, requires repeated evidence + provenance,
maps a promoted pattern to an improvement, and is served under Patterns & Improvements — never
diagnosing the user.

  1. SIX ARCHETYPES   — the system pattern language is present (shadow/trickster/persona/self/mentor/
                        threshold), each scoped to the SYSTEM.
  2. REAL EVIDENCE    — patterns carry evidence counts + provenance refs from the real stores.
  3. EVIDENCE THRESH  — a pattern is only a 'hypothesis' with >= the threshold of real occurrences;
                        below it, it is honestly 'watching' (no single-event inference).
  4. TO IMPROVEMENT   — a promoted SYSTEM hypothesis maps to an improvement SUGGESTION (product action),
                        never a claim about the user.
  5. SERVED + AUTH    — the registry rides through _console_data; the page renders an Archetypal
                        Patterns tab with the non-diagnostic framing.
  6. NO USER DIAGNOSIS — (delegates to the keystone) the registry never crosses into user labelling.

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

    print("ARCHETYPAL PATTERN REGISTRY (extends L10 · Pattern->Improvement) — system pattern language, not user diagnosis")
    print("=" * 92)

    from anima.archetypal_patterns import detector, policy, schema
    from anima import server

    html = (ROOT / "anima" / "web" / "console.html").read_text()
    srv = (ROOT / "anima" / "server.py").read_text()

    with _temp_store():
        # seed enough real events so at least one archetype promotes to a hypothesis
        try:
            from anima import incident
            for _ in range(4):
                incident.security_event("quarantine", "hostile text held", route="output", markers=["PWNED"])
        except Exception:
            pass

        pats = detector.detect("Vera")
        by = {p["archetype"]: p for p in pats}

        # ---- 1 six archetypes --------------------------------------------------------------
        ck("1. the six system archetypes are present, each scoped to the SYSTEM",
           set(by) == set(schema.ARCHETYPE_IDS) and all(p["scope"] == "system" for p in pats))

        # ---- 2 real evidence ---------------------------------------------------------------
        ck("2. patterns carry evidence counts + provenance refs from the real stores",
           any(p["evidence_count"] > 0 and p["evidence"] for p in pats))

        # ---- 3 evidence threshold ----------------------------------------------------------
        promoted = [p for p in pats if p["status"] == "hypothesis"]
        watching = [p for p in pats if p["status"] == "watching"]
        ck("3. a pattern is a 'hypothesis' ONLY at/above the evidence threshold; else 'watching'",
           all(p["evidence_count"] >= schema.EVIDENCE_THRESHOLD for p in promoted)
           and all(p["evidence_count"] < schema.EVIDENCE_THRESHOLD for p in watching)
           and len(promoted) >= 1)

        # ---- 4 to improvement --------------------------------------------------------------
        imp = policy.to_improvement(promoted[0])
        ck("4. a promoted SYSTEM hypothesis maps to an improvement suggestion (not a user claim)",
           bool(imp) and imp.get("is_about_user") is False and imp.get("recommendation")
           and imp.get("source_archetype") in schema.ARCHETYPE_IDS)
        ck("4. a 'watching' (sub-threshold) pattern does NOT yield an improvement",
           policy.to_improvement(watching[0]) == {} if watching else True)

        # ---- 5 served + UI -----------------------------------------------------------------
        d = server._console_data("Vera")
        ck("5. the registry rides through the Founder Console data (_console_data.archetypes)",
           isinstance(d.get("archetypes"), dict) and d["archetypes"].get("patterns"))
        ck("5. the page renders an Archetypal Patterns tab with the non-diagnostic framing",
           "archView" in html and "Archetypal Patterns" in html and "system, not you" in html)

    # ---- 6 keystone (no user diagnosis) ----------------------------------------------------
    rc, tail = None, ""
    try:
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_archetype_no_user_diagnosis.py")],
                           capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        rc, tail = r.returncode, r.stdout + r.stderr
    except Exception:
        pass
    ck("6. the keystone holds: certify_archetype_no_user_diagnosis CERTIFIED",
       rc == 0 and "ARCHETYPE-NO-USER-DIAGNOSIS CERT: CERTIFIED" in tail)

    print("\nARCHETYPAL-REGISTRY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
