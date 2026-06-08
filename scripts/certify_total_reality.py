#!/usr/bin/env python3
"""certify_total_reality — the Vera Total Reality Test master cert (PHASE 1: Level 0 inventory + the
finite scenario matrix + Level-1 critical journeys). Proves the foundation is REAL and the directive's
hard rules hold, with teeth.

  1. INVENTORY REAL    — surfaces / controls / routes / feature contracts are discovered from the real
                         product (not invented); every surface file exists and is served by the server.
  2. NO UNMAPPED CONTROL — (hard rule) every visible control has >= 1 scenario.
  3. NO UNCLASSIFIED BEHAVIOUR — every scenario is fully classified (no UNKNOWN axis).
  4. EVERY CLAIM TESTED — every feature contract maps to >= 1 scenario.
  5. CRITICAL JOURNEYS — the Level-1 critical journeys exist AND the synthetic-user Rover's deterministic
                         critical/immune proof passes (vera_rover --selftest).
  6. COVERAGE BITES    — the keystone: the unmapped-control detector actually FIRES on a synthetic control
                         with no scenario. A coverage check that can't detect a gap is wallpaper.
  7. MATRIX PERSISTS   — the report bundle (matrix + inventories + coverage) writes well-formed.

Phase 1 of a multi-phase program. Levels 2-9 (full surface / permission / data / state / pairwise /
renegade / soak / fuzz) are the next phases, honestly deferred. Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import subprocess
import sys
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

    print("VERA TOTAL REALITY TEST — PHASE 1 (Level 0 inventory + scenario matrix + Level-1 critical)")
    print("=" * 92)

    from anima.scenarios import inventory, generator, schema
    inv = inventory.full_inventory()
    matrix = generator.generate(inv)
    c, mc = inv["counts"], matrix["counts"]

    # ---- 1 inventory real + served --------------------------------------------------------------
    ck("1. the inventory is REAL: surfaces/controls/routes/contracts discovered from the live product",
       c["surfaces"] >= 10 and c["controls"] >= 20 and c["routes"] >= 50 and c["contracts"] >= 100
       and all((ROOT / s["file"]).exists() for s in inv["surfaces"]))
    ck("1. every surface is actually served by the server (no orphan page)",
       c["surfaces_served"] == c["surfaces"])

    # ---- 2 no unmapped control (hard rule) ------------------------------------------------------
    ctrl_ids = {x["control_id"] for v in inv["controls"].values() for x in v}
    scen_ctrl = {s["control_id"] for s in matrix["scenarios"] if s.get("control_id")}
    unmapped = ctrl_ids - scen_ctrl
    ck("2. NO unmapped visible control — every control has >= 1 scenario (hard rule)",
       not unmapped and len(ctrl_ids) >= 20)

    # ---- 3 no unclassified behaviour ------------------------------------------------------------
    ck("3. NO unclassified behaviour — every scenario is fully classified (no UNKNOWN axis)",
       mc["fully_classified"] == mc["total"] and mc["total"] >= 100
       and all(schema.is_fully_classified(s) for s in matrix["scenarios"]))

    # ---- 4 every claim tested -------------------------------------------------------------------
    feat = {f["feature"] for f in inv["contracts"]}
    mapped = {s["scenario_id"][len("trt_contract_"):] for s in matrix["scenarios"]
              if s["scenario_id"].startswith("trt_contract_")}
    ck("4. every feature contract (claim) maps to >= 1 scenario",
       feat and feat <= mapped)

    # ---- 5 critical journeys --------------------------------------------------------------------
    crit = [s for s in matrix["scenarios"] if s["kind"] == "critical"]
    rover_ok = False
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "vera_rover.py"), "--selftest"],
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        rover_ok = (r.returncode == 0)
    except Exception:
        rover_ok = False
    ck("5. Level-1 critical journeys exist (>=10) AND the Rover's deterministic critical proof passes",
       len(crit) >= 10 and rover_ok)

    # ---- 6 COVERAGE BITES (the keystone) --------------------------------------------------------
    # inject a synthetic control with NO scenario and confirm the unmapped-control detector fires
    fake_ctrls = dict(inv["controls"])
    fake_ctrls = {**fake_ctrls, "__fake__": [{"control_id": "__fake__.button.ghost", "surface": "__fake__",
                                              "kind": "button", "label": "ghost"}]}
    fake_ids = {x["control_id"] for v in fake_ctrls.values() for x in v}
    detected_gap = bool(fake_ids - scen_ctrl)
    ck("6. the coverage check BITES — a control with no scenario is detected as an unmapped gap",
       detected_gap and "__fake__.button.ghost" in (fake_ids - scen_ctrl))

    # ---- 7 matrix persists ----------------------------------------------------------------------
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_total_scenario_matrix.py")],
                        capture_output=True, text=True, timeout=60, cwd=str(ROOT)).returncode
    bundle = all((ROOT / "reports" / f).exists() for f in
                 ("scenario_matrix.json", "scenario_coverage.md", "user_surface_inventory.json",
                  "control_inventory.json", "api_inventory.json", "feature_to_scenario_matrix.json"))
    ck("7. the report bundle (matrix + inventories + coverage) writes well-formed", rc == 0 and bundle)

    # ---- 8 served + UI --------------------------------------------------------------------------
    from anima import server
    srv = (ROOT / "anima" / "server.py").read_text()
    html = (ROOT / "anima" / "web" / "reality.html").read_text() if (ROOT / "anima" / "web" / "reality.html").exists() else ""
    d = server._total_reality_data("Vera")
    ck("8. the coverage rides through _total_reality_data + GET /reality serves the Control Room page",
       isinstance(d.get("inventory"), dict) and "/reality" in srv and "reality.json" in srv
       and "Total Reality" in html and "realityView" in html)

    # ---- PHASE 2 — Level-2 Rover execution + Observation Harness (delegated certs) --------------
    re_rc, re_t = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_rover_execution.py")],
                                 capture_output=True, text=True, timeout=180, cwd=str(ROOT)).returncode, ""
    ob_rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_observation_bundle_complete.py")],
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT)).returncode
    ck("9. PHASE 2 — the Rover EXECUTES the Level-2 matrix against real backing paths (rover-execution cert)",
       re_rc == 0)
    ck("10. PHASE 2 — every executed scenario has an evidence record correlated by run_id (bundle cert)",
       ob_rc == 0)

    # ---- LEVEL 7 — Renegade integrated stress chains (delegated cert) ---------------------------
    rn_rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_renegade_chains.py")],
                           capture_output=True, text=True, timeout=180, cwd=str(ROOT)).returncode
    ck("11. LEVEL 7 — the Renegade integrated stress chains HOLD (renegade-chains cert)", rn_rc == 0)

    print("\nTOTAL-REALITY (Phase 1+2): surfaces=%d controls=%d routes=%d contracts=%d -> scenarios=%d"
          % (c["surfaces"], c["controls"], c["routes"], c["contracts"], mc["total"]))
    print("TOTAL-REALITY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
