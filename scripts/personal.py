#!/usr/bin/env python3
"""
personal — CLI for PERSONAL INTELLIGENCE ("Learn Lamar"), the moat.

Build, inspect, and prove the grounded model of how ONE person (the user — Lamar) thinks,
decides, prioritizes, writes, and learns. Every object is built from CAPTURED data only
(the LIRF fact ledger + the transient turn log) — nothing is invented — and carries its
grounding evidence + provenance. The thesis: personal intelligence COMPOUNDS.

FREEZE BOUNDARY ("build the mind, leave the self alone"): this models the USER only. Every
value/preference is minted through anima/lerf.py's freeze-guarded factories, which REFUSE a
Vera-self subject (FreezeViolation). `freeze-proof` demonstrates that refusal.

    python3 scripts/personal.py learn       --creature vera   # read capture -> build+store the model
    python3 scripts/personal.py profile     --creature vera   # print the grounded profile (read-only)
    python3 scripts/personal.py freeze-proof                  # prove a Vera-self value/pref is REFUSED
    python3 scripts/personal.py --selftest                    # hermetic selftest (touches no real .anima)

`learn` writes to the REAL store under .anima/{creature}.lerf.json (that is the point — it
populates the substrate from what was actually captured). `profile` and `freeze-proof` are
read-only. `--selftest` redirects ALL stores to a temp dir and asserts the real .anima is
byte-unchanged. Re-running `learn` after more capture simply grows the model (the thesis).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import personal                                    # noqa: E402


def _cmd_learn(args) -> int:
    """Read EVERY captured record for the person and build + store the whole model."""
    summary = personal.learn(args.creature, person=args.person,
                             include_turns=not args.no_turns, store=True)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"Learned {summary['total_learned']} grounded object(s) about {args.person} "
          f"from {summary['evidence_records']} captured record(s) "
          f"-> .anima/{args.creature}.lerf.json\n")
    print(f"  decision patterns : {len(summary['decision_patterns'])}")
    print(f"  writing prefs     : {len(summary['writing_preferences'])}")
    print(f"  preferences       : {len(summary['preferences'])}")
    print(f"  values/tradeoffs  : {len(summary['values'])}")
    print(f"  lessons           : {len(summary['lessons'])}")
    if summary["total_learned"] == 0:
        print("\n  (Nothing captured yet for this person — the model is honestly empty. "
              "It fills in only from what the user actually says, never invented.)")
    else:
        print("\n  --- the assembled profile ---\n")
        for line in personal.render_profile(args.creature, person=args.person).splitlines():
            print("  " + line)
    return 0


def _cmd_profile(args) -> int:
    """Print (read-only) what is KNOWN about the person — grounded, no fabrication."""
    if args.json:
        print(json.dumps(personal.personal_profile(args.creature, person=args.person),
                         indent=2))
        return 0
    print(personal.render_profile(args.creature, person=args.person))
    return 0


def _cmd_freeze_proof(args) -> int:
    """Prove the freeze boundary: a Vera-self value/preference is REFUSED."""
    res = personal.freeze_proof()
    if args.json:
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    print("FREEZE PROOF — this module models the USER (Lamar), never Vera herself.")
    print(f"  principle: {res['principle']}\n")
    for c in res["checks"]:
        mark = "REFUSED ✓" if c["refused"] else "NOT REFUSED ✗"
        print(f"  [{mark}] {c['label']}")
    print(f"\n  {'ALL SELF-REFERENTIAL VALUES/PREFERENCES REFUSED' if res['ok'] else 'FREEZE BREACH'}")
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Personal intelligence — Learn Lamar (the moat).")
    ap.add_argument("--selftest", action="store_true",
                    help="run the hermetic selftest (touches no real .anima); exits 0 on pass")
    sub = ap.add_subparsers(dest="cmd")

    def _common(p):
        p.add_argument("--creature", default="default",
                       help="creature/ledger name -> .anima/{creature}.lerf.json (default: 'default')")
        p.add_argument("--person", default="Lamar",
                       help="who the model is ABOUT (the user). Default: 'Lamar'")
        p.add_argument("--json", action="store_true", help="emit JSON instead of prose")

    p_learn = sub.add_parser("learn", help="read capture -> build + store the model")
    _common(p_learn)
    p_learn.add_argument("--no-turns", action="store_true",
                         help="use durable facts only; ignore the transient turn log")
    p_learn.set_defaults(func=_cmd_learn)

    p_prof = sub.add_parser("profile", help="print the grounded profile (read-only)")
    _common(p_prof)
    p_prof.set_defaults(func=_cmd_profile)

    p_fp = sub.add_parser("freeze-proof", help="prove a Vera-self value/pref is REFUSED")
    p_fp.add_argument("--json", action="store_true", help="emit JSON instead of prose")
    p_fp.set_defaults(func=_cmd_freeze_proof)

    args = ap.parse_args(argv)

    if args.selftest:
        return personal._selftest()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
