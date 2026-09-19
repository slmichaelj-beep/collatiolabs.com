#!/usr/bin/env python3
"""certify_living_map_overlay — Living Map Milestone 5 (PATTERN OVERLAY) is REAL: the Pattern
Observatory's recurring patterns are surfaced ON the map, each mapped to the node it concerns, with no
invented hotspots.

  1. REAL PATTERNS    — the overlay reads the REAL Pattern Observatory store; seeded patterns appear.
  2. MAPPED TO NODES  — every mapped pattern lands on a REAL map node, with a count + worst severity badge.
  3. NO INVENTED HOTSPOT (the keystone) — a pattern that maps to no known node goes to the 'unmapped'
                        bucket, NEVER forced onto a node. The map shows only real hotspots.
  4. WORST SEVERITY   — a node's badge reflects the WORST severity among its patterns.
  5. HONEST EMPTY     — with no patterns, the overlay is empty (no fake badges).
  6. SERVED + UI      — the overlay rides a token-gated route; the page applies pattern badges to nodes.

Standalone (patches the reports dir so it's hermetic). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import tempfile
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

    print("LIVING MAP — PATTERN OVERLAY (Milestone 5): real recurring patterns surfaced on the map")
    print("=" * 92)

    from anima.living_map import overlay, schema
    from anima import server
    srv = (ROOT / "anima" / "server.py").read_text()
    html = (ROOT / "anima" / "web" / "living_map.html").read_text()
    node_ids = {n["node_id"] for n in schema.NODES}

    # patch the reports dir to a temp one so seeded patterns don't touch the real store
    tmp = Path(tempfile.mkdtemp(prefix="lm-overlay-"))
    _orig = overlay.REPORTS
    try:
        overlay.REPORTS = tmp
        # ---- 5 honest empty (no patterns file) -------------------------------------------------
        empty = overlay.overlay("Vera")
        ck("5. with no patterns, the overlay is empty (no fake badges)",
           empty.get("empty") is True and empty.get("patterns_total") == 0)

        # seed real-shaped patterns: two mappable, one un-mappable
        (tmp / "patterns.json").write_text(json.dumps({"patterns": [
            {"pattern_id": "source_use", "title": "Source retrieved but not used", "severity": "P1", "frequency": 83},
            {"pattern_id": "model_latency", "title": "Model latency spike", "severity": "P0", "frequency": 9,
             "evidence": [{"route": "llm"}]},
            {"pattern_id": "zzz_unknown", "title": "Totally unmappable thing", "severity": "P2", "frequency": 2},
        ]}))
        o = overlay.overlay("Vera")

        # ---- 1 real patterns -------------------------------------------------------------------
        ck("1. the overlay reads the real Pattern Observatory store (seeded patterns appear)",
           o.get("patterns_total") == 3 and not o.get("empty"))

        # ---- 2 mapped to real nodes ------------------------------------------------------------
        ck("2. every mapped pattern lands on a REAL map node with a count + worst-severity badge",
           bool(o["by_node"]) and all(nid in node_ids and b["count"] >= 1 and b["worst_severity"]
                                      for nid, b in o["by_node"].items()))

        # ---- 3 NO invented hotspot (the keystone) ----------------------------------------------
        ck("3. an un-mappable pattern goes to 'unmapped', NEVER forced onto a node (no invented hotspot)",
           any(u["pattern_id"] == "zzz_unknown" for u in o["unmapped"])
           and not any(u["pattern_id"] == "zzz_unknown" for b in o["by_node"].values() for u in b["patterns"]))

        # ---- 4 worst severity ------------------------------------------------------------------
        mr = o["by_node"].get("model_runtime")
        ck("4. a node's badge reflects the WORST severity among its patterns (P0 model-latency)",
           mr is not None and mr["worst_severity"] == "P0")
    finally:
        overlay.REPORTS = _orig

    # ---- 6 served + UI -----------------------------------------------------------------------
    d = server._living_map_overlay("Vera")
    ck("6. the overlay rides a token-gated route (/founder/living-map/overlay)",
       isinstance(d, dict) and '"/founder/living-map/overlay"' in srv
       and srv.find("if not self._authed():") < srv.find('"/founder/living-map/overlay"'))
    ck("6. the page applies pattern badges to nodes (overlayView + the overlay fetch)",
       "overlayView" in html and "/founder/living-map/overlay" in html and "patbadge" in html)

    print("\nLIVING MAP OVERLAY: " + ("GREEN" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
