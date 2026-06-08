#!/usr/bin/env python3
"""certify_observatory — the served Observatory page shows REAL data, no jargon, no wallpaper.

  1. PAGE SERVED    — GET /observatory returns the HTML shell (public, like index.html).
  2. DATA WIRED     — GET /observatory.json is behind the auth wall and aggregates the real surfaces.
  3. REAL AUDIT     — the audit numbers equal the live-path matrix (95/96, 0 wallpaper) — not hardcoded.
  4. REAL MIND      — the system-shape dimensions ride through (honesty / live-path / coverage).
  5. REAL TWIN      — what Vera knows about you rides through (grounded dimensions + items).
  6. REAL ACTIVITY  — the latest turn (input -> reply -> stages) rides through from the MRI trace.
  7. HONEST NULLS   — a missing report becomes a null section, never a faked one (no wallpaper).
  8. NO JARGON      — the page translates the internals (What's real / What kind of mind / What I know
                      about you / Latest activity), so a non-builder can read it.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima import server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("OBSERVATORY — a served, no-jargon window that shows REAL data")
    print("=" * 92)

    # ---- 1. PAGE SERVED + 2. ROUTE WIRED + auth posture ------------------------------------
    page = ROOT / "anima" / "web" / "observatory.html"
    srv = (ROOT / "anima" / "server.py").read_text()
    ck("1. the Observatory page exists and is served at /observatory",
       page.exists() and '"/observatory"' in srv and "observatory.html" in srv)
    ck("2. /observatory.json is wired and sits BEHIND the auth wall (personal data token-gated)",
       '"/observatory.json"' in srv
       and srv.find("if not self._authed():") < srv.find('"/observatory.json"'))

    # ---- the aggregator returns REAL data --------------------------------------------------
    d = server._observatory_data("Vera")

    # ---- 3. REAL AUDIT (matches the live-path matrix, not hardcoded) ------------------------
    try:
        m = json.loads((ROOT / "reports" / "live_path_results.json").read_text())
        c = m.get("counts") or {}
        a = d.get("audit") or {}
        ck("3. the audit numbers EQUAL the live-path matrix (real, not hardcoded)",
           a.get("complete") == c.get("COMPLETE") and a.get("wallpaper") == c.get("WALLPAPER")
           and a.get("total") == sum(c.values()))
    except Exception as e:
        ck("3. the audit numbers EQUAL the live-path matrix", False)

    # ---- 4/5/6. REAL mind / twin / activity ------------------------------------------------
    sh = d.get("shape") or {}
    ck("4. the system-shape dimensions ride through (honesty / live-path / coverage)",
       bool(sh.get("dimensions")) and any("honest" in (x.get("label", "").lower()) for x in sh["dimensions"]))
    tw = d.get("twin") or {}
    ck("5. what Vera knows about you rides through (grounded dimensions)",
       bool(tw.get("dimensions")) and any((x.get("count") or 0) > 0 for x in tw["dimensions"]))
    lt = d.get("lastTurn") or {}
    ck("6. the latest turn rides through (input -> reply -> stages, from the MRI trace)",
       bool(lt.get("reply")) and bool(lt.get("stages")))

    # ---- 7. HONEST NULLS (a missing report -> null, never faked) ---------------------------
    # the aggregator must degrade gracefully: feed it a name with no MRI/twin and the sections are
    # null/empty, NOT invented. (lastTurn for a never-seen creature has no trace.)
    d2 = server._observatory_data("NoSuchCreature_xyz")
    ck("7. a creature with no trace yields an HONEST null activity section (no wallpaper)",
       d2.get("lastTurn") is None)

    # ---- 8. NO JARGON (the page translates the internals) -----------------------------------
    html = page.read_text()
    ck("8. the page is no-jargon (What's real / What kind of mind / What I know about you / Latest activity)",
       all(s in html for s in ("What's real", "kind of mind", "know about you", "Latest activity")))
    ck("8. the page is read-only + local-first framed (nothing leaves the Mac)",
       "Read-only" in html and "leaves your Mac" in html)

    print("\nOBSERVATORY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
