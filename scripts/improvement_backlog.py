#!/usr/bin/env python3
"""
improvement_backlog — the SELF-IMPROVING backlog the system keeps on itself.

Shows the Improvement Engine's tracked backlog (reports/improvement_backlog.json) ranked actionable-
first, in human-level terms: for each work order — what it is, how bad (P0/P1/P2), the root cause,
the suggested fix, and the cert that PROVES it done. With --verify it actually RUNS each item's
cert_required and updates the status from the result, so "done" is decided by the cert, never asserted.

    python3 scripts/improvement_backlog.py                  # view the ranked backlog
    python3 scripts/improvement_backlog.py --verify         # run cert_required, prove/refute each fix
    python3 scripts/improvement_backlog.py --verify --only conversation_repair
    python3 scripts/improvement_backlog.py --json           # machine-readable payload
    python3 scripts/improvement_backlog.py --selftest       # hermetic engine self-proof
    python3 scripts/improvement_backlog.py --gate           # exit non-zero if any P0 is NEEDS_WORK

If the backlog is empty it is built from reports/patterns.json on the fly. Reads reports/*.json,
writes reports/improvement_backlog.json. --verify shells the certs (themselves hermetic); the engine
never writes .anima or touches the live server.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anima import improvement_engine as ie

_SEV = {"P0": "P0 ship-blocking", "P1": "P1 important", "P2": "P2 cleanup"}
_STATUS_GLYPH = {ie.CERTIFIED: "✓ CERTIFIED", ie.NEEDS_WORK: "✗ NEEDS WORK",
                 ie.OPEN: "· OPEN", ie.MANUAL: "? MANUAL"}


def _wrap(s: str, width: int = 104, indent: str = "         ") -> str:
    import textwrap
    s = " ".join((s or "").split())
    if not s:
        return ""
    return ("\n").join(textwrap.wrap(s, width=width, initial_indent=indent,
                                     subsequent_indent=indent))


def _load_or_build():
    items = ie.load_backlog()
    if not items and ie.PATTERNS_JSON.exists():
        items = ie.ingest(ie.load_patterns())
        ie.save_backlog(items)
    return items


def _print_report(items) -> None:
    st = ie.stats(items)
    bar = "=" * 108
    print(bar)
    print("IMPROVEMENT BACKLOG — the system's tracked work orders on itself (Phase 6)")
    print(bar)
    print(f"  {st['total']} item(s)   ·   by severity {st['by_severity']}   ·   by status "
          f"{st['by_status']}")
    print(f"  actionable now (OPEN/NEEDS_WORK): {st['open_actionable']}   ·   "
          f"proven done (CERTIFIED): {st['certified']}")
    print()
    for it in ie.rank(items):
        glyph = _STATUS_GLYPH.get(it.status, it.status)
        sev = _SEV.get(it.severity, it.severity)
        print(f"  [{glyph}]  {it.title}   ({sev}, seen {it.frequency}x)   <{it.pattern_id}>")
        if it.root_cause:
            print("     why it happens:")
            print(_wrap(it.root_cause))
        if it.recommended_fix:
            print("     what to do:")
            print(_wrap(it.recommended_fix))
        if it.cert_required:
            print("     proven by:  " + "  |  ".join(it.cert_required))
        ver = it.verification or {}
        if ver.get("results"):
            for r in ver["results"]:
                print(f"       cert {('OK  ' if r.get('ok') else 'FAIL')}  exit={r.get('exit')}  "
                      f"{r.get('cmd')}")
        elif ver.get("note"):
            print(f"       note: {ver['note']}")
        print()
    print(bar)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The system's self-improvement backlog.")
    ap.add_argument("--verify", action="store_true", help="run cert_required and update status")
    ap.add_argument("--only", help="with --verify, restrict to a single pattern_id")
    ap.add_argument("--json", action="store_true", help="emit the backlog payload as JSON")
    ap.add_argument("--gate", action="store_true", help="exit non-zero if any P0 item is NEEDS_WORK")
    ap.add_argument("--selftest", action="store_true", help="hermetic engine self-proof")
    args = ap.parse_args(argv)

    if args.selftest:
        return ie._selftest()

    items = _load_or_build()
    if not items:
        print("backlog empty and no reports/patterns.json — run scripts/pattern_observatory.py "
              "then scripts/pattern_to_backlog.py first.")
        return 1

    if args.verify:
        targets = [it for it in items if (not args.only or it.pattern_id == args.only)]
        if args.only and not targets:
            print(f"no backlog item with pattern_id={args.only!r}")
            return 1
        for it in targets:
            print(f"verifying <{it.pattern_id}> — running {len(ie.runnable_certs(it.cert_required))} "
                  f"cert(s)…", flush=True)
            ie.verify_item(it)
            print(f"  -> {it.status}")
        ie.save_backlog(items)

    if args.json:
        print(json.dumps({"stats": ie.stats(items),
                          "items": [it.to_dict() for it in ie.rank(items)]},
                         indent=2, ensure_ascii=False))
    else:
        _print_report(items)

    if args.gate:
        blocking = [it.pattern_id for it in items
                    if it.severity == "P0" and it.status == ie.NEEDS_WORK]
        if blocking:
            print(f"\nGATE: {len(blocking)} P0 item(s) NEEDS_WORK -> {blocking}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
