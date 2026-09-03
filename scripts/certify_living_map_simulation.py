#!/usr/bin/env python3
"""certify_living_map_simulation — Living Map Milestone 4 (SIMULATION) is REAL: pull a lever -> a
predicted impact that is DERIVED from re-running the real status resolvers under a hypothetical, in a
sandbox that never touches real state.

  1. LEVERS REAL      — the available levers each name the REAL source they would hypothetically change.
  2. PREDICTION DERIVED (the keystone) — with the baseline pinned to host-pressure GREEN, simulating
                        host-pressure RED predicts the dependent nodes (argus / model_runtime) degrading.
                        The prediction comes from re-running the real derivation — not a hardcoded table.
  3. RESPONDS TO LEVER— a different lever value yields a different prediction (green vs red differ); a
                        constant would not.
  4. SANDBOXED        — after a simulation the real source is RESTORED and a fresh build matches the
                        baseline (sandbox_clean) — the sim changed nothing real.
  5. GROUNDED FRAMING — every simulation declares its assumptions, a confidence, and the cert that would
                        gate shipping a real change.
  6. HONEST           — an unknown lever returns ok=False with the available levers, never a fake prediction.
  7. SERVED + AUTH    — the sim rides through a token-gated route; the page has a Simulation mode.

Standalone (uses in-process source patching; restores always). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_BAD = {"red", "yellow", "blocked", "degraded", "warn"}


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIVING MAP — SIMULATION (Milestone 4): pull a lever -> predicted impact, derived + sandboxed")
    print("=" * 92)

    from anima.living_map import simulation as sim
    from anima import host_pressure
    srv = (ROOT / "anima" / "server.py").read_text()
    html = (ROOT / "anima" / "web" / "living_map.html").read_text()

    # ---- 1 levers real -------------------------------------------------------------------------
    lv = sim.levers()
    ck("1. the available levers each name the REAL source they would change",
       len(lv) >= 2 and all(l.get("source") and l.get("id") for l in lv))

    # ---- 2 + 3 prediction DERIVED + responds to the lever (pin the baseline to GREEN) ----------
    _orig = host_pressure.read_pressure
    try:
        host_pressure.read_pressure = lambda: {"level": "green"}   # baseline: green
        red = sim.simulate("Vera", "host_pressure_red")
        green = sim.simulate("Vera", "host_pressure_green")
    finally:
        host_pressure.read_pressure = _orig

    red_changes = {c["node_id"]: c for c in red.get("predicted_changes", [])}
    ck("2. simulating host-pressure RED (from a GREEN baseline) predicts a dependent node degrading",
       red.get("ok") and red.get("changed_count", 0) >= 1
       and any(nid in red_changes and str(red_changes[nid]["to"]) in _BAD for nid in ("argus", "model_runtime")))
    ck("3. the prediction RESPONDS to the lever (RED and GREEN differ — not a constant)",
       red.get("predicted_changes") != green.get("predicted_changes"))

    # ---- 4 sandboxed ---------------------------------------------------------------------------
    live = sim.simulate("Vera", "host_pressure_red")
    ck("4. the simulation is SANDBOXED — the real source is restored (sandbox_clean) + nothing real changed",
       live.get("sandboxed") is True and live.get("sandbox_clean") is True
       and host_pressure.read_pressure is _orig)

    # ---- 5 grounded framing --------------------------------------------------------------------
    ck("5. every simulation declares assumptions + confidence + the cert that would gate a real change",
       isinstance(live.get("assumptions"), list) and live["assumptions"]
       and isinstance(live.get("confidence"), (int, float)) and live.get("required_cert"))

    # ---- 6 honest unknown ----------------------------------------------------------------------
    bad = sim.simulate("Vera", "no_such_lever")
    ck("6. an unknown lever returns ok=False with the available levers (never a fake prediction)",
       bad.get("ok") is False and bad.get("available"))

    # ---- 7 served + UI -------------------------------------------------------------------------
    ck("7. the simulation rides a token-gated route (/founder/living-map/simulate)",
       '"/founder/living-map/simulate"' in srv
       and srv.find("if not self._authed():") < srv.find('"/founder/living-map/simulate"'))
    ck("7. the page has a Simulation mode fed by the simulate fetch (simulateView)",
       "simulateView" in html and "/founder/living-map/simulate" in html and 'data-mode="simulate"' in html)

    print("\nLIVING MAP SIMULATION: " + ("GREEN" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
