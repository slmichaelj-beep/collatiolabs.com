#!/usr/bin/env python3
"""
program_reality_audit — the capstone of the Program Reality Audit.

"Make the system incapable of fooling itself." This aggregates the three audit layers into
ONE honest verdict the founder/team can run:

    python3 scripts/program_reality_audit.py            # the reality report
    python3 scripts/program_reality_audit.py --gate     # exit non-zero on RED

Layers consumed:
  1. Feature inventory      reports/feature_inventory.json   (what the system CLAIMS exists)
  2. Live-path classifier   scripts/certify_live_paths.py    (what each claim ACTUALLY is)
  3. Stub-marker scan       anima/** + scripts/**            (obvious placeholders, informational)

Verdict law (the Prime Law, machine-enforced):
  RED if ANY feature is WALLPAPER, or any feature the contract claims COMPLETE has a broken
  live path, or any REGRESSED. PARTIAL/UNKNOWN/STUB-in-scaffolding are honest gaps that are
  REPORTED, not hidden — they do not by themselves flip the verdict to RED (they raise risk).

Hermetic: this script only RUNS the hermetic live-path classifier (which asserts the real
.anima is byte-identical) and READS/WRITES under reports/. It never writes .anima, never hits
the live server, never runs the heavy live gate.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
LIVE_RESULTS = REPORTS / "live_path_results.json"
INVENTORY = REPORTS / "feature_inventory.json"

# the worklist of fixes a given status implies (so the report ends with "Required next work")
_NEXT_WORK = {
    "WALLPAPER": "FIX NOW or remove the misleading surface — behavior contradicts the claim.",
    "REGRESSED": "REGRESSION — a previously-COMPLETE feature now fails its live path.",
    "PARTIAL": "complete the missing live-path link(s), or label the surface PARTIAL.",
    "STUB": "implement, gate behind dev-mode, or delete.",
    "UNREACHABLE": "expose a user path or drop the claim.",
    "UNKNOWN": "audit (often needs --live model + a concrete fixture).",
}
_STUB_MARKERS = re.compile(
    r"\b(TODO|FIXME|XXX|NotImplementedError|coming soon|not implemented|placeholder|"
    r"\bstub\b|\bmock\b|\bfake\b|\bdummy\b|hardcoded|wallpaper)\b", re.I)


def _run_live_paths() -> tuple[int, dict]:
    """Run the authoritative live-path classifier (hermetic) and load its fresh results."""
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_live_paths.py")],
                        cwd=str(ROOT), capture_output=True, text=True)
    data = {}
    if LIVE_RESULTS.exists():
        try:
            data = json.loads(LIVE_RESULTS.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    return rc.returncode, data


def _ensure_inventory() -> dict:
    if not INVENTORY.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "inventory_features.py")],
                       cwd=str(ROOT), capture_output=True, text=True)
    try:
        return json.loads(INVENTORY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _stub_scan() -> dict:
    """Informational marker count across anima/ + scripts/ (never gates)."""
    hits, files = 0, 0
    for base in ("anima", "scripts"):
        for p in sorted((ROOT / base).rglob("*.py")):
            files += 1
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if _STUB_MARKERS.search(line):
                        hits += 1
            except Exception:
                pass
    return {"files_scanned": files, "marker_hits": hits}


def _features(results: dict) -> list[dict]:
    """Normalise the classifier output into a list of {feature, status, ...}."""
    feats = results.get("features") or results.get("results") or results
    if isinstance(feats, dict):
        out = []
        for k, v in feats.items():
            if isinstance(v, dict):
                v = dict(v)
                v.setdefault("feature", k)
                out.append(v)
        return out
    return [f for f in feats if isinstance(f, dict)] if isinstance(feats, list) else []


def main(argv=None) -> int:
    gate = "--gate" in (argv or sys.argv[1:])

    inv = _ensure_inventory()
    inv_items = inv.get("features") if isinstance(inv, dict) else inv
    inv_count = len(inv_items) if isinstance(inv_items, list) else (
        inv.get("count") if isinstance(inv, dict) else 0)

    live_rc, results = _run_live_paths()
    feats = _features(results)
    by_status: dict[str, list[str]] = {}
    for f in feats:
        by_status.setdefault(str(f.get("status", "UNKNOWN")).upper(), []).append(
            f.get("feature", "?"))

    stubs = _stub_scan()

    wallpaper = by_status.get("WALLPAPER", [])
    regressed = by_status.get("REGRESSED", [])
    red = bool(wallpaper or regressed) or live_rc != 0
    verdict = "RED" if red else ("AMBER" if (by_status.get("PARTIAL") or by_status.get("UNKNOWN")) else "GREEN")

    # ---- emit ----
    bar = "=" * 92
    out = [bar, f"PROGRAM REALITY AUDIT: {verdict}", bar,
           f"  inventory: {inv_count} claimed features   ·   classified: {len(feats)}   ·   "
           f"stub-markers: {stubs['marker_hits']} across {stubs['files_scanned']} files (informational)",
           ""]
    order = ["COMPLETE", "PARTIAL", "WALLPAPER", "STUB", "UNREACHABLE", "REGRESSED", "UNKNOWN"]
    for st in order:
        names = by_status.get(st, [])
        if names:
            out.append(f"  {st:<12} {len(names):>2}   {', '.join(sorted(names))}")
    out.append("")
    if wallpaper or regressed:
        out.append("  BLOCKING (flips the verdict RED):")
        for f in feats:
            if str(f.get("status", "")).upper() in ("WALLPAPER", "REGRESSED"):
                out.append(f"   ✗ {f.get('feature')} [{f.get('status')}] — "
                           f"{(f.get('reason') or f.get('evidence') or '')!s:.180}")
        out.append("")
    # required next work, risk-ordered
    out.append("  REQUIRED NEXT WORK:")
    for st in ("WALLPAPER", "REGRESSED", "PARTIAL", "STUB", "UNREACHABLE", "UNKNOWN"):
        for name in sorted(by_status.get(st, [])):
            out.append(f"   - [{st}] {name}: {_NEXT_WORK.get(st, '')}")
    out.append("")
    out.append(f"  verdict law: RED iff any WALLPAPER/REGRESSED, or a COMPLETE-claimed feature "
               f"has a broken live path (classifier --gate exit was {live_rc}).")
    out.append(bar)
    report = "\n".join(out)
    print(report)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "program_reality_audit.md").write_text(report + "\n", encoding="utf-8")
    (REPORTS / "program_reality_audit.json").write_text(json.dumps({
        "verdict": verdict, "red": red, "live_path_gate_exit": live_rc,
        "counts": {k: len(v) for k, v in by_status.items()},
        "by_status": by_status, "blocking": wallpaper + regressed,
        "inventory_count": inv_count, "stub_scan": stubs,
    }, indent=2), encoding="utf-8")

    if gate:
        return 1 if red else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
