#!/usr/bin/env python3
"""
certify_system_shape — the honest one-glance portrait is REAL, GROUNDED, and refuses to fabricate.

anima/system_shape.compose() reads the reports the system already writes about ITSELF and composes
them into five founder-level axes. This certifies that the composer can only MIRROR those reports —
never invent a flattering shape — by driving compose()/save()/rank_dimensions() against synthetic
self-reports fabricated in a temp dir (compose(reports_dir) + save(path) both take explicit paths,
so the REAL reports/ is neither read nor written):

  A. FIVE GROUNDED AXES — exactly five axes compose; each carries its source's RAW evidence and a
     status/value derived from it: honesty<-audit counts (0 wallpaper/regressed => STRONG), self_
     knowledge<-classified/inventory, live_integrity<-COMPLETE/total, self_improvement<-backlog
     stats, open_work<-pattern P0/P1/P2. (A real composition off the reports, not a stub.)
  B. IT READS THE FILES, NOT A CONSTANT — flipping the audit to a WALLPAPER world flips honesty to
     WEAK and the headline to WEAK and the synthesis to "NOT fully honest"; and changing the self-
     knowledge inputs (classified/inventory) changes that axis's value + status. So the shape is a
     function OF the reports on disk, not a fixed payload — the contract's whole point.
  C. ANTI-FABRICATION (the no-wallpaper core) — with NO reports present EVERY axis is `unknown` and
     the headline is `unknown`: a missing report yields an honest empty, never a guessed value.
  D. DETERMINISTIC — composing the SAME reports twice yields an identical object (no randomness in
     the compose path).
  E. WEAKEST-FIRST — rank_dimensions() puts a weak axis ahead of ok/strong (founder sees what needs
     attention first).
  F. DURABLE + ISOLATED — save() round-trips valid JSON to the TEMP path AND the real
     reports/system_shape.json is NOT created by this cert.

Hermetic + offline: wrapped in gate0_prime_experience._temp_store (NO model, NO network, NO .anima
write); system_shape reads no STORE (it reads reports/), and we pass it ONLY a temp reports dir, so
nothing real is touched. The real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def _write_healthy(rd: Path) -> None:
    """A healthy synthetic self-world: AMBER audit (0 wallpaper/regressed), 12/81 classified,
    9 COMPLETE, 1 certified work order + 0 open, 0 P0 / 1 P1 pattern."""
    (rd / "program_reality_audit.json").write_text(json.dumps({
        "verdict": "AMBER", "counts": {"COMPLETE": 9, "PARTIAL": 2, "UNKNOWN": 1}}))
    (rd / "feature_inventory.json").write_text(json.dumps({"features": list(range(81))}))
    (rd / "live_path_results.json").write_text(json.dumps({"features": {}}))
    (rd / "improvement_backlog.json").write_text(json.dumps({
        "stats": {"total": 1, "certified": 1, "open_actionable": 0}}))
    (rd / "patterns.json").write_text(json.dumps({"counts": {"P0": 0, "P1": 1, "P2": 0}}))


def main() -> int:
    from anima import system_shape as ss
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("SYSTEM SHAPE — the honest one-glance portrait is real, grounded, and won't fabricate")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)
    real_report = ss.REPORTS / "system_shape.json"
    real_report_existed = real_report.exists()

    with _temp_store():
        import tempfile
        with tempfile.TemporaryDirectory(prefix="syshape-cert-") as td:
            rd = Path(td)
            _write_healthy(rd)

            shape = ss.compose(rd)
            by = {d["key"]: d for d in shape["dimensions"]}

            # ---- A. FIVE GROUNDED AXES -------------------------------------------------------
            ck("A1: exactly five axes compose (honesty/self_knowledge/live_integrity/"
               "self_improvement/open_work)",
               len(shape["dimensions"]) == 5
               and set(by) == {"honesty", "self_knowledge", "live_integrity",
                               "self_improvement", "open_work"})
            ck("A2: honesty is STRONG and grounded in the audit counts (0 wallpaper, 0 regressed)",
               by["honesty"]["status"] == ss.STRONG
               and by["honesty"]["evidence"].get("wallpaper") == 0
               and by["honesty"]["evidence"].get("regressed") == 0)
            ck("A3: self_knowledge reads classified/inventory (12/81 -> OK, ≥10%) and carries the raw "
               "evidence", by["self_knowledge"]["status"] == ss.OK
               and by["self_knowledge"]["value"].startswith("12/81")
               and by["self_knowledge"]["evidence"].get("classified") == 12
               and by["self_knowledge"]["evidence"].get("inventory") == 81)
            ck("A4: live_integrity reads COMPLETE/total (9/12 -> OK) and is grounded",
               by["live_integrity"]["status"] == ss.OK
               and by["live_integrity"]["evidence"].get("complete") == 9
               and by["live_integrity"]["evidence"].get("classified") == 12)
            ck("A5: self_improvement reads the backlog stats (all certified -> STRONG)",
               by["self_improvement"]["status"] == ss.STRONG
               and by["self_improvement"]["evidence"].get("certified") == 1
               and by["self_improvement"]["evidence"].get("actionable") == 0)
            ck("A6: open_work reads the pattern counts (P0==0, P1>0 -> OK)",
               by["open_work"]["status"] == ss.OK
               and by["open_work"]["evidence"].get("P0") == 0
               and by["open_work"]["evidence"].get("P1") == 1)
            ck("A7: the headline is OK (no weak axis, not all strong) and the synthesis is grounded "
               "in the axes (honest + self-improving)",
               shape["headline_status"] == ss.OK
               and "honest" in shape["synthesis"] and "self-improving" in shape["synthesis"])
            ck("A8: inputs_present truthfully records that all five reports were found",
               all(shape["inputs_present"].values()))

            # ---- B. IT READS THE FILES, NOT A CONSTANT ---------------------------------------
            # B-i: a WALLPAPER audit flips honesty + the headline to weak (the shape tracks the report).
            (rd / "program_reality_audit.json").write_text(json.dumps({
                "verdict": "RED", "counts": {"COMPLETE": 8, "WALLPAPER": 1}}))
            wall = ss.compose(rd)
            wby = {d["key"]: d for d in wall["dimensions"]}
            ck("B1: a WALLPAPER audit flips honesty to WEAK (composer mirrors the report)",
               wby["honesty"]["status"] == ss.WEAK
               and wby["honesty"]["evidence"].get("wallpaper") == 1)
            ck("B2: a WEAK axis flips the headline to WEAK and the synthesis to 'NOT fully honest'",
               wall["headline_status"] == ss.WEAK and "NOT fully honest" in wall["synthesis"])
            # restore a healthy audit so the next probe isolates the self_knowledge change
            _write_healthy(rd)
            # B-ii: changing the self_knowledge inputs changes that axis's value + status (not a constant).
            (rd / "feature_inventory.json").write_text(json.dumps({"features": list(range(20))}))
            (rd / "program_reality_audit.json").write_text(json.dumps({
                "verdict": "GREEN", "counts": {"COMPLETE": 18, "PARTIAL": 0}}))
            sk = ss.compose(rd)
            skd = {d["key"]: d for d in sk["dimensions"]}["self_knowledge"]
            ck("B3: changing classified/inventory changes self_knowledge (18/20 -> STRONG, ≥50%) — "
               "value is a function of the report, not a fixed string",
               skd["status"] == ss.STRONG and skd["value"].startswith("18/20")
               and skd["evidence"].get("classified") == 18 and skd["evidence"].get("inventory") == 20)

            # ---- C. ANTI-FABRICATION (the no-wallpaper core) ---------------------------------
            empty = ss.compose(Path(td) / "does_not_exist")
            ck("C1: with NO reports present, EVERY axis is `unknown` (honest empty, never a guess)",
               all(d["status"] == ss.UNKNOWN for d in empty["dimensions"])
               and len(empty["dimensions"]) == 5)
            ck("C2: the headline is `unknown` with no evidence (refuses to invent a flattering shape)",
               empty["headline_status"] == ss.UNKNOWN)
            ck("C3: inputs_present honestly reports every report ABSENT",
               not any(empty["inputs_present"].values()))

            # ---- D. DETERMINISTIC ------------------------------------------------------------
            _write_healthy(rd)
            ck("D1: composing the SAME reports twice yields an identical object (no compose-path "
               "randomness)", ss.compose(rd) == ss.compose(rd))

            # ---- E. WEAKEST-FIRST ------------------------------------------------------------
            ranked = ss.rank_dimensions(wall["dimensions"])
            ck("E1: rank_dimensions puts a weak axis first (founder sees what needs attention first)",
               ranked[0]["status"] == ss.WEAK)

            # ---- F. DURABLE + ISOLATED -------------------------------------------------------
            out = ss.save(shape, rd / "system_shape.json")
            ck("F1: save() round-trips valid JSON to the temp path (durable)",
               json.loads(out.read_text())["headline_status"] == shape["headline_status"])
            ck("F2: this cert did NOT create the real reports/system_shape.json (isolated)",
               real_report.exists() == real_report_existed)

    # ---- HERMETICITY --------------------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nSYSTEM-SHAPE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
