#!/usr/bin/env python3
"""certify_data_type_coverage — Total Reality Level 4: every DATA CLASS is driven through the real
classifiers and handled correctly — hostile flagged + neutralised, sensitive flagged, benign spared.

  1. EVERY CLASS RUN  — every representative data class is classified by the REAL immune + sensitivity
                        classifiers (>= 8 classes).
  2. CORRECT HANDLING — hostile is flagged hostile, the must-be-sensitive classes are flagged sensitive,
                        and the benign classes are not falsely flagged hostile.
  3. DISCRIMINATES (the keystone) — the classifiers tell classes apart: a hostile class is hostile and a
                        public class is not; a sensitive class is sensitive and a public class is not.
  4. CREDENTIAL CAUGHT — a credential/secret (password / API key) is classified sensitive (the gap the
                        Total Reality Test surfaced, now closed) — never silently trusted.
  5. UNKNOWN HANDLED  — an unknown/garbage class is handled (no crash, not silently trusted).

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("TOTAL REALITY — DATA-TYPE COVERAGE (Level 4): every data class through the real classifiers")
    print("=" * 92)

    from anima.rover import data_types
    run = data_types.run()
    s = run["summary"]
    by = {r["data_class"]: r for r in run["results"]}

    # ---- 1 every class run ---------------------------------------------------------------------
    ck("1. every representative data class is classified by the real classifiers (>= 8)",
       s["total"] >= 8 and len(run["results"]) == s["total"])

    # ---- 2 correct handling --------------------------------------------------------------------
    ck("2. hostile flagged, sensitive classes flagged, benign classes not falsely hostile",
       s["all_pass"] and s["fail"] == 0)

    # ---- 3 DISCRIMINATES (the keystone) --------------------------------------------------------
    ck("3. the classifiers DISCRIMINATE — hostile class is hostile, public class is not; sensitive is, public is not",
       by["hostile_instruction"]["hostile"] and not by["public"]["hostile"]
       and by["sensitive_personal"]["sensitive"] and not by["public"]["sensitive"])

    # ---- 4 credential caught (the surfaced gap, now closed) ------------------------------------
    ck("4. a credential / secret (password / API key) is classified sensitive (never silently trusted)",
       by["credential_secret"]["sensitive"] is True)

    # ---- 5 unknown handled ---------------------------------------------------------------------
    ck("5. an unknown/garbage class is handled (no crash, not silently trusted as benign-hostile)",
       by["unknown_classification"]["handled"] is True and by["unknown_classification"]["ok"] is True)

    print("\n  data classes: %d · pass=%d fail=%d" % (s["total"], s["pass"], s["fail"]))
    print("DATA-TYPE-COVERAGE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
