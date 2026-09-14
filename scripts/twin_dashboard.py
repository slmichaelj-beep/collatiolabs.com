#!/usr/bin/env python3
"""
twin_dashboard — the Personal Digital Twin: one honest view of what Vera knows about YOU.

Composes the grounded personal stores (identity facts, how-you-think, trajectory, what-matters, your
world) into a single portrait — richest dimension first, every empty dimension shown honestly as
"nothing yet" rather than invented. This is the read-only PORTRAIT of the portable personal
intelligence, distinct from anima/twin.py (the simulation sandbox).

    python3 scripts/twin_dashboard.py                 # the portrait for Vera's person
    python3 scripts/twin_dashboard.py --name Vera
    python3 scripts/twin_dashboard.py --json
    python3 scripts/twin_dashboard.py --selftest      # hermetic self-proof

Reads the per-creature stores read-only, writes reports/twin_dashboard.json. Never a model, never a
store mutation, never the live server.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anima import twin_dashboard as td

_GLYPH = {True: "●", False: "○"}


def _print(twin) -> None:
    bar = "=" * 100
    rich = twin.get("richness", "?")
    cov = twin.get("coverage", {})
    print(bar)
    print(f"PERSONAL DIGITAL TWIN — what Vera knows about {twin.get('person','you')}   "
          f"[{rich.upper()}: {cov.get('dimensions_present',0)}/{cov.get('dimensions_total',0)} "
          f"dimensions, {cov.get('items_known',0)} items]")
    print(bar)
    print("  " + twin.get("synthesis", ""))
    print()
    for d in td.rank_dimensions(twin.get("dimensions", [])):
        g = _GLYPH.get(d["present"], "?")
        print(f"  {g} {d['label']:<46} [{d['count']:>3}]")
        for it in (d.get("items") or [])[:6]:
            print(f"        - {it}")
        if not d["present"]:
            print("        (nothing grounded yet)")
    print(bar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vera's honest portrait of what it knows about you.")
    ap.add_argument("--name", default="Vera", help="creature/person store name (default Vera)")
    ap.add_argument("--json", action="store_true", help="emit the twin as JSON")
    ap.add_argument("--selftest", action="store_true", help="hermetic self-proof")
    ap.add_argument("--no-save", action="store_true", help="do not write reports/twin_dashboard.json")
    args = ap.parse_args(argv)

    if args.selftest:
        return td._selftest()

    twin = td.compose(args.name)
    if not args.no_save:
        td.save(twin)
    if args.json:
        print(json.dumps(twin, indent=2, ensure_ascii=False))
    else:
        _print(twin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
