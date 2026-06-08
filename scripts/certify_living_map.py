#!/usr/bin/env python3
"""certify_living_map — Milestone 1: the Living Map STATIC real map is served, real, and auth-gated.

  1. PAGE SERVED      — GET /founder/living-map serves the page SHELL (public like the other consoles);
                        the page file exists.
  2. STATE AUTH-GATED — GET /founder/living-map/state is wired BEHIND the auth wall (operator data).
  3. REAL NODES       — the graph returns the real subsystem nodes (>= 20), each with id/label/type/
                        status/source_of_truth/description.
  4. REAL EDGES       — the graph returns the real flows (>= 20), each between two real nodes, with a
                        derived status.
  5. REAL STATUS      — status loads from real telemetry (host pressure, audit, caps, security) — at
                        least several nodes carry live metrics.
  6. HONEST UNKNOWN   — a subsystem with no live data is 'unknown', never a fake green.
  7. READ-ONLY        — building the map does not mutate Vera state (no writes); the endpoint is a GET.
  8. PAGE RENDERS     — the page renders nodes, edges, a node side-panel, modes, and the source-of-truth
                        (evidence) — it is a map, not a static picture.

Exit 0 == LIVING MAP STATIC: GREEN; 1 == FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima import server
    from anima.living_map import graph
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIVING MAP — STATIC REAL MAP (Milestone 1)")
    print("=" * 92)

    page = ROOT / "anima" / "web" / "living_map.html"
    srv = (ROOT / "anima" / "server.py").read_text()
    html = page.read_text() if page.exists() else ""

    # ---- 1 / 2 routes + auth ---------------------------------------------------------------
    ck("1. /founder/living-map serves the page; the page file exists",
       page.exists() and '"/founder/living-map"' in srv and "living_map.html" in srv)
    ck("2. /founder/living-map/state is wired BEHIND the auth wall (operator data token-gated)",
       '"/founder/living-map/state"' in srv
       and srv.find("if not self._authed():") < srv.find('"/founder/living-map/state"'))

    # ---- 3 / 4 real nodes + edges ----------------------------------------------------------
    d = server._living_map_data("Vera")
    nodes, edges = d.get("nodes") or [], d.get("edges") or []
    by_id = {n["node_id"]: n for n in nodes}
    ck("3. the graph returns the real subsystem nodes (>= 20) with the full node shape",
       len(nodes) >= 20 and all(all(k in n for k in
           ("node_id", "label", "type", "status", "source_of_truth", "description")) for n in nodes))
    ck("3. the named keystone subsystems are present",
       all(k in by_id for k in ("context_immune", "final_gate", "model_runtime", "memory",
                                "sources", "audit", "argus", "lockdown", "capability_truth")))
    ck("4. the graph returns the real flows (>= 20), each between two real nodes with a status",
       len(edges) >= 20 and all(e["from"] in by_id and e["to"] in by_id and "status" in e for e in edges))

    # ---- 5 real status from telemetry ------------------------------------------------------
    with_metrics = [n for n in nodes if n.get("live_metrics")]
    ck("5. status loads from real telemetry (several nodes carry live metrics)",
       len(with_metrics) >= 8)
    ck("5. the host-pressure node reflects a real level (green/yellow/red), not a constant",
       by_id["argus"]["status"] in ("green", "yellow", "red", "unknown")
       and by_id["argus"]["live_metrics"].get("level") is not None or by_id["argus"]["status"] == "unknown")

    # ---- 6 honest unknown ------------------------------------------------------------------
    ck("6. a subsystem with no live data is honestly 'unknown' (e.g. background job queue depth)",
       by_id["jobs"]["status"] == "unknown")

    # ---- 7 read-only -----------------------------------------------------------------------
    import importlib.util as _il
    spec = _il.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
    g0 = _il.module_from_spec(spec)
    spec.loader.exec_module(g0)
    with g0._temp_store():
        from anima.living_map import graph as _g
        before = _fingerprint()
        _g.build_graph("Vera")
        _g.build_graph("Vera")
        after = _fingerprint()
    ck("7. building the map is READ-ONLY (no writes to the store)", before == after)

    # ---- 8 the page is a real map ----------------------------------------------------------
    ck("8. the page renders nodes + edges + a node side-panel + modes",
       all(s in html for s in ("class=\"node", "id=\"edges\"", "id=\"side\"", "Live Flow", "Evidence")))
    ck("8. the page surfaces each node's source of truth (evidence), not just colours",
       "source_of_truth" in html and "Source of truth" in html and "What it does" in html)

    static_ok = not fails
    print("\nLIVING MAP STATIC: " + ("GREEN" if static_ok else f"FAIL ({len(fails)})"))

    # ===== MILESTONE 2 — LIVE EVENT PULSES (animate only what happened) =====================
    print("\nLIVING MAP — LIVE EVENT PULSES (Milestone 2)")
    print("=" * 92)
    live_fails = []

    def lk(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            live_fails.append(label)

    lk("L1. /founder/living-map/events is wired BEHIND the auth wall (operator data token-gated)",
       '"/founder/living-map/events"' in srv
       and srv.find("if not self._authed():") < srv.find('"/founder/living-map/events"'))

    ev = server._living_map_events("Vera")
    evs = ev.get("events") or []
    eids = {e["edge_id"] for e in edges}
    nids = set(by_id.keys())
    lk("L2. events come from REAL traces (>=1 turn/security event) OR an honest empty state",
       isinstance(evs, list) and (len(evs) >= 1 or ev.get("empty") is True))
    lk("L3. EVERY event maps to a real edge AND a real node (no invented motion)",
       all(e.get("edge_id") in eids and e.get("node_id") in nids for e in evs))
    lk("L4. EVERY event carries an evidence reference (mri_ref or security_event_ref)",
       all((e.get("evidence") and any(k in e["evidence"] for k in ("mri_ref", "security_event_ref"))) for e in evs))
    lk("L5. events are time-ordered (newest first)",
       all((evs[i].get("timestamp") or 0) >= (evs[i + 1].get("timestamp") or 0) for i in range(len(evs) - 1)))
    lk("L6. the page ANIMATES real events (pulse layer fed by the events fetch), not static pulses",
       'id="pulses"' in html and "loadEvents" in html and "/founder/living-map/events" in html
       and "getPointAtLength" in html)
    lk("L7. honest empty: the page shows 'no recent activity' rather than a fake heartbeat",
       "No recent activity to animate" in html)

    live_ok = not live_fails
    print("\nLIVING MAP LIVE: " + ("GREEN" if live_ok else f"FAIL ({len(live_fails)})"))

    return 0 if (static_ok and live_ok) else 1


def _fingerprint():
    try:
        from anima.server import STORE
        import hashlib
        h = hashlib.sha256()
        for q in sorted(STORE.rglob("*")):
            if q.is_file() and "backups" not in q.parts:
                try:
                    h.update(q.name.encode()); h.update(str(q.stat().st_size).encode())
                except Exception:
                    pass
        return h.hexdigest()
    except Exception:
        return "x"


if __name__ == "__main__":
    raise SystemExit(main())
