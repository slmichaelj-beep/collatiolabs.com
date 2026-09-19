#!/usr/bin/env python3
"""certify_ui_truth_consistency — the UI may simplify truth, but it may not contradict it. The served
dashboard's headline numbers must match the backing reports.

  1. CONSISTENT      — when the served payload matches the computed floor/build-identity, status green.
  2. MISMATCH BITES  — (keystone) a served payload whose p0_open / running_commit / program-reality
                       count disagrees with the backend is flagged RED with the specific mismatch.

Hermetic (synthetic served payloads). Exit 0 == CERTIFIED.
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

    print("UI TRUTH CONSISTENCY — the served UI must not contradict the backend (computed, with teeth)")
    print("=" * 92)

    from anima.verification import gates

    floor = {"p0_open": 0, "complete": 110}
    bi = {"running_commit": "abc1234"}
    pr_gate = {"gate_id": "program_reality", "evidence": "110 COMPLETE / 1 PARTIAL"}

    # consistent served payload
    served_ok = {"top": {"p0_open": 0, "running_commit": "abc1234"}, "gates": [pr_gate]}
    r_ok = gates._ui_truth({}, floor, bi, served=served_ok)
    ck("1. a served payload matching the backend is CONSISTENT (green)",
       r_ok["status"] == "green" and not r_ok["mismatches"])

    # mismatched p0
    served_p0 = {"top": {"p0_open": 3, "running_commit": "abc1234"}, "gates": [pr_gate]}
    r_p0 = gates._ui_truth({}, floor, bi, served=served_p0)
    ck("2a. MISMATCH BITES — served p0_open != backend is flagged RED",
       r_p0["status"] == "red" and any("p0_open" in m for m in r_p0["mismatches"]))

    # mismatched running commit
    served_cm = {"top": {"p0_open": 0, "running_commit": "zzzz9999"}, "gates": [pr_gate]}
    r_cm = gates._ui_truth({}, floor, bi, served=served_cm)
    ck("2b. MISMATCH BITES — served running_commit != build identity is flagged RED",
       r_cm["status"] == "red" and any("running_commit" in m for m in r_cm["mismatches"]))

    # mismatched program-reality count
    served_pr = {"top": {"p0_open": 0, "running_commit": "abc1234"},
                 "gates": [{"gate_id": "program_reality", "evidence": "99 COMPLETE / 12 PARTIAL"}]}
    r_pr = gates._ui_truth({}, floor, bi, served=served_pr)
    ck("2c. MISMATCH BITES — served program_reality complete count != backend is flagged RED",
       r_pr["status"] == "red" and any("program_reality" in m for m in r_pr["mismatches"]))

    print("\nUI-TRUTH-CONSISTENCY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
