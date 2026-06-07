#!/usr/bin/env python3
"""
pattern_to_backlog — the bridge from the Pattern Observatory to the Improvement Backlog.

Reads the Observatory's work orders (reports/patterns.json), folds them into the tracked
improvement backlog (reports/improvement_backlog.json), and prints a short summary. Known
pattern_ids keep their created stamp + last verification/status; their work-order fields are
refreshed from the latest patterns.json so a re-detected pattern cannot drift from its remediation.

    python3 scripts/pattern_to_backlog.py                 # patterns.json -> backlog (merge)
    python3 scripts/pattern_to_backlog.py --from-observatory   # regenerate patterns.json first

Hermetic: reads reports/*.json, writes reports/improvement_backlog.json. Never .anima, never the
live server. (--from-observatory shells the Pattern Observatory, which is itself read-only.)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anima import improvement_engine as ie


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--from-observatory" in argv:
        print("regenerating reports/patterns.json via the Pattern Observatory…")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "pattern_observatory.py")],
                       cwd=str(ROOT))

    if not ie.PATTERNS_JSON.exists():
        print(f"no {ie.PATTERNS_JSON.relative_to(ROOT)} — run scripts/pattern_observatory.py first "
              f"(or pass --from-observatory).")
        return 1

    patterns = ie.load_patterns()
    existing = ie.load_backlog()
    items = ie.ingest(patterns, existing=existing)
    out = ie.save_backlog(items)
    st = ie.stats(items)

    n_new = len([it for it in items if it.pattern_id not in {e.pattern_id for e in existing}])
    print(f"ingested {len(ie._patterns_list(patterns))} work order(s) "
          f"({n_new} new) -> {out.relative_to(ROOT)}")
    print(f"  backlog: {st['total']} items   ·   "
          f"by severity {st['by_severity']}   ·   by status {st['by_status']}")
    print(f"  actionable (OPEN/NEEDS_WORK): {st['open_actionable']}   ·   "
          f"certified: {st['certified']}")
    print("  next: python3 scripts/improvement_backlog.py            # view the ranked backlog")
    print("        python3 scripts/improvement_backlog.py --verify   # run cert_required, prove fixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
