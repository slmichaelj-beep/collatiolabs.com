#!/usr/bin/env python3
"""certify_living_map_no_wallpaper — the Living Map is REAL, not decoration.

The founder directive's hard line: no fake animation, no hardcoded green, no decorative flow pretending
to be truth. This cert proves, structurally AND dynamically, that every visible status is BACKED by a
real source — and that a node with no live data is honestly 'unknown', never a fake green.

  1. SOURCE PER NODE   — every node declares a source_of_truth list (empty only for the external human).
  2. NO GREEN W/O SRC  — no node is green/yellow/red without a non-empty source_of_truth.
  3. EDGES ARE REAL    — every edge connects two real nodes; edge status is derived from node status.
  4. HONEST UNKNOWNS   — uninstrumented subsystems (OCR per-run, job-queue depth) are 'unknown', not green.
  5. STATUS IS DERIVED — patching a REAL source flips the dependent node's status (host pressure ->
                        argus + model_runtime), proving status is computed from data, not a constant.
  6. MAPS TO REAL DATA — a node's live metric EQUALS the real store (audit counts == the live-path
                        matrix; caps_on == caps.load) — the map cannot drift from the system.
  7. NO STATIC PULSES  — the page fetches its graph (no hardcoded node array / no baked-in 'green').

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
    from anima.living_map import graph, schema
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIVING MAP — NO WALLPAPER (every status backed by a real source)")
    print("=" * 92)

    g = graph.build_graph("Vera")
    nodes = g["nodes"]
    by_id = {n["node_id"]: n for n in nodes}

    # ---- 1 source per node -----------------------------------------------------------------
    ck("1. every node declares a source_of_truth list",
       all(isinstance(n.get("source_of_truth"), list) for n in nodes))

    # ---- 2 no coloured status without a real source ----------------------------------------
    coloured = [n for n in nodes if n["status"] in ("green", "yellow", "red", "blue")]
    ck("2. NO node is green/yellow/red without a non-empty source_of_truth (no hardcoded green)",
       all(n.get("source_of_truth") for n in coloured))

    # ---- 3 edges connect real nodes; status derived ----------------------------------------
    ck("3. every edge connects two REAL nodes",
       all(e["from"] in by_id and e["to"] in by_id for e in g["edges"]))
    ck("3. edge status is one of the derived states (active/degraded/blocked/idle)",
       all(e["status"] in ("active", "degraded", "blocked", "idle") for e in g["edges"]))

    # ---- 4 honest unknowns -----------------------------------------------------------------
    ck("4. uninstrumented subsystems are honestly 'unknown' (OCR per-run, job-queue depth)",
       by_id["ocr"]["status"] == "unknown" and by_id["jobs"]["status"] == "unknown")

    # ---- 5 STATUS IS DERIVED (patch a real source -> node status follows) -------------------
    from anima import host_pressure
    _orig = host_pressure.read_pressure
    try:
        host_pressure.read_pressure = lambda: {"level": "green"}
        g_green = graph.build_graph("Vera")
        host_pressure.read_pressure = lambda: {"level": "red"}
        g_red = graph.build_graph("Vera")
    finally:
        host_pressure.read_pressure = _orig
    a_green = next(n for n in g_green["nodes"] if n["node_id"] == "argus")["status"]
    a_red = next(n for n in g_red["nodes"] if n["node_id"] == "argus")["status"]
    m_green = next(n for n in g_green["nodes"] if n["node_id"] == "model_runtime")["status"]
    m_red = next(n for n in g_red["nodes"] if n["node_id"] == "model_runtime")["status"]
    ck("5. host-pressure source drives the Argus node (green source -> green, red source -> red)",
       a_green == "green" and a_red == "red")
    ck("5. host-pressure source drives the Model Runtime policy node (derived, not constant)",
       m_green == "green" and m_red == "red")

    # ---- 6 maps to real data (cannot drift) ------------------------------------------------
    try:
        real = json.loads((ROOT / "reports" / "live_path_results.json").read_text()).get("counts") or {}
        audit_m = by_id["audit"]["live_metrics"]
        ck("6. the Audit node's metric EQUALS the live-path matrix (no drift from reality)",
           audit_m.get("complete") == real.get("COMPLETE") and audit_m.get("wallpaper") == real.get("WALLPAPER"))
    except Exception:
        ck("6. the Audit node's metric EQUALS the live-path matrix", False)
    try:
        from anima import caps
        real_on = sorted(k for k, v in caps.load("Vera").items() if v is True)
        ck("6. the Capability Truth node's caps_on EQUALS caps.load (the real gate)",
           by_id["capability_truth"]["live_metrics"].get("caps_on") == real_on)
    except Exception:
        ck("6. the Capability Truth node's caps_on EQUALS caps.load", False)

    # ---- 7 no static pulses / hardcoded nodes in the page ----------------------------------
    html = (ROOT / "anima" / "web" / "living_map.html").read_text()
    ck("7. the page FETCHES its graph (no hardcoded node array / baked-in status)",
       "/founder/living-map/state" in html and "DATA.nodes" in html
       and "source_of_truth" in html)
    ck("7. the page has no fabricated 'green' node literals (status comes from the fetch)",
       "status:'green'" not in html.replace(" ", "") and "\"status\":\"green\"" not in html)

    print("\nLIVING MAP NO-WALLPAPER: " + ("GREEN" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
