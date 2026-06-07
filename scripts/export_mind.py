#!/usr/bin/env python3
"""
export_mind — carry a person's mind out of Vera as a portable, model-agnostic bundle (and back in).

The "portable" in Portable Personal Intelligence: a plain-JSON export of what Vera has grounded about
you — identity facts (the round-trip core), how-you-think, trajectory, what-matters, your world — that
any app or model can read, and that re-imports its identity core into a fresh store with proven
fidelity. No vendor format, no weights, no lock-in.

    python3 scripts/export_mind.py                       # export Vera's mind -> reports/portable_mind.json
    python3 scripts/export_mind.py --name Vera --out my_mind.json
    python3 scripts/export_mind.py --import my_mind.json --into VeraCopy   # round-trip the core in
    python3 scripts/export_mind.py --selftest             # hermetic round-trip proof

Export reads the per-creature stores read-only. Import writes ONLY the target's LIRF ledger via the
normal merge path (full provenance). Never a model, never the live server.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anima import portable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export/import a portable personal-intelligence bundle.")
    ap.add_argument("--name", default="Vera", help="creature/person to export (default Vera)")
    ap.add_argument("--out", help="output bundle path (default reports/portable_mind.json)")
    ap.add_argument("--import", dest="imp", help="a bundle file to import the identity core FROM")
    ap.add_argument("--into", help="target creature to import INTO (with --import)")
    ap.add_argument("--selftest", action="store_true", help="hermetic round-trip self-proof")
    args = ap.parse_args(argv)

    if args.selftest:
        return portable._selftest()

    if args.imp:
        if not args.into:
            print("error: --import requires --into <target creature>")
            return 1
        bundle = json.loads(Path(args.imp).read_text(encoding="utf-8"))
        res = portable.import_mind(bundle, args.into)
        print(f"imported {res['imported']} identity fact(s) into {args.into!r}")
        print(f"  traits: {', '.join(res['traits'])}")
        return 0

    bundle = portable.export_mind(args.name)
    out = Path(args.out) if args.out else (ROOT / "reports" / "portable_mind.json")
    portable.save_bundle(bundle, out)
    m = bundle["manifest"]
    c = m["counts"]
    print(f"exported {args.name!r}'s portable mind -> {out}")
    print(f"  schema {m['schema']} v{m['version']}")
    print(f"  identity facts : {c['identity_facts']}")
    print(f"  how you think  : {c['personal_items']} items (known={c['personal_known']})")
    print(f"  trajectory     : {c['has_trajectory']}   what-matters: {c['has_meaning']}   "
          f"world: {c['has_world']}")
    print(f"  -> plain JSON, model-agnostic; re-import the identity core with "
          f"--import {out.name} --into <name>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
