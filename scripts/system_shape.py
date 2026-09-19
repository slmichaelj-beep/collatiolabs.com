#!/usr/bin/env python3
"""
system_shape — the one-glance, honest portrait of what kind of mind Vera is right now.

Composes the self-knowledge reports (Program Reality Audit, live-path classifier, feature inventory,
improvement backlog, pattern observatory) into a few axes a founder actually cares about: is it
honest, how much of itself does it know, how much works end-to-end, is it closing its own work
orders, and what does it currently know is wrong. Missing inputs become an honest `unknown` axis —
never a flattering guess.

    python3 scripts/system_shape.py            # the portrait (weakest axis first)
    python3 scripts/system_shape.py --json      # machine-readable
    python3 scripts/system_shape.py --selftest   # hermetic self-proof

Reads reports/*.json, writes reports/system_shape.json. Never a model, never .anima, never the
live server. Tip: refresh the inputs first with
  python3 scripts/program_reality_audit.py && python3 scripts/pattern_to_backlog.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anima import system_shape as ss

_GLYPH = {ss.STRONG: "●", ss.OK: "◐", ss.WEAK: "○", ss.UNKNOWN: "?"}


def _print(shape) -> None:
    bar = "=" * 100
    head = shape.get("headline_status", "?")
    print(bar)
    print(f"SYSTEM SHAPE — what kind of mind is Vera right now   [{_GLYPH.get(head,'?')} {head.upper()}]")
    print(bar)
    print("  " + shape.get("synthesis", ""))
    print()
    for d in ss.rank_dimensions(shape.get("dimensions", [])):
        print(f"  {_GLYPH.get(d['status'],'?')} {d['label']:<30} [{d['status'].upper():<7}]  {d['value']}")
        print(f"      {d['human']}")
    miss = [k for k, v in (shape.get("inputs_present") or {}).items() if not v]
    if miss:
        print(f"\n  (missing inputs -> shown as 'unknown': {', '.join(miss)})")
    print(bar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vera's one-glance honest portrait.")
    ap.add_argument("--json", action="store_true", help="emit the shape as JSON")
    ap.add_argument("--selftest", action="store_true", help="hermetic self-proof")
    ap.add_argument("--no-save", action="store_true", help="do not write reports/system_shape.json")
    args = ap.parse_args(argv)

    if args.selftest:
        return ss._selftest()

    shape = ss.compose()
    if not args.no_save:
        ss.save(shape)
    if args.json:
        print(json.dumps(shape, indent=2, ensure_ascii=False))
    else:
        _print(shape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
