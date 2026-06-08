#!/usr/bin/env python3
"""enterprise_readiness — Phase 14: the capstone. Is Vera explainable to a buyer / security reviewer
without Lamar in the room?

READY only when every hardening cert passes AND the evidence (docs + reports + a clean audit) exists:

  - SECURITY / PERMISSIONS / PRIVACY / PERFORMANCE / AI-SECURITY / PRODUCT-POLISH certs all CERTIFIED.
  - The audit matrix has 0 WALLPAPER / 0 STUB / 0 UNREACHABLE / 0 REGRESSED / 0 UNKNOWN; the only
    PARTIAL is honestly external-dependency-blocked.
  - The security evidence is written down (security_architecture / threat_model / permission_model).
  - The diamond baseline reports exist (a reviewer can read the posture cold).

Exit 0 == READY; 1 == NOT READY.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(script, token):
    p = SCRIPTS / script
    if not p.exists():
        return False, "missing %s" % script
    try:
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True,
                           timeout=300, cwd=str(ROOT))
        out = (r.stdout or "") + (r.stderr or "")
        return (r.returncode == 0 and token in out), out
    except Exception as e:
        return False, repr(e)


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ENTERPRISE READINESS — explainable to a reviewer without Lamar in the room")
    print("=" * 92)

    # ---- the hardening certs ---------------------------------------------------------------
    certs = [
        ("certify_security_baseline.py", "SECURITY-BASELINE CERT: CERTIFIED", "SECURITY"),
        ("certify_permissions.py", "PERMISSIONS CERT: CERTIFIED", "PERMISSIONS"),
        ("certify_privacy.py", "PRIVACY CERT: CERTIFIED", "PRIVACY"),
        ("certify_performance.py", "PERFORMANCE CERT: CERTIFIED", "PERFORMANCE"),
        ("certify_ai_security.py", "AI-SECURITY CERT: CERTIFIED", "AI-SECURITY"),
        ("certify_product_polish.py", "PRODUCT-POLISH CERT: CERTIFIED", "PRODUCT-POLISH"),
    ]
    for script, token, label in certs:
        ok, _ = _run(script, token)
        ck("hardening cert %-14s CERTIFIED" % label, ok)

    # ---- the audit matrix is clean ---------------------------------------------------------
    matrix = ROOT / "reports" / "live_path_results.json"
    clean = False
    if matrix.exists():
        try:
            d = json.load(open(matrix))
            feats = d.get("features") or []
            bad = sum(1 for f in feats if f.get("status") in
                      ("WALLPAPER", "STUB", "UNREACHABLE", "REGRESSED", "UNKNOWN"))
            # exclude this aggregate itself (it IS in the matrix it reads — a self-reference that
            # would otherwise deadlock it at PARTIAL forever) when judging the partials.
            partials = [f for f in feats if f.get("status") == "PARTIAL"
                        and f.get("feature") != "enterprise_readiness"]
            ext_only = all("EXTERNAL" in (f.get("reason") or "").upper() for f in partials)
            clean = (bad == 0 and ext_only)
            print("       (audit: %d contracts, 0 hard-gaps=%s, partials external-only=%s)"
                  % (len(feats), bad == 0, ext_only))
        except Exception:
            pass
    ck("the audit matrix is clean (0 wallpaper/stub/unknown; partials external-blocked only)", clean)

    # ---- the evidence is written down ------------------------------------------------------
    docs = ROOT / "docs"
    ck("security evidence is documented (architecture + threat model + permission model)",
       all((docs / f).exists() for f in
           ("security_architecture.md", "threat_model.md", "permission_model.md")))
    reports = ROOT / "reports"
    ck("the diamond baseline reports exist (posture readable cold)",
       (reports / "diamond_baseline.md").exists() and (reports / "no_wallpaper_report.md").exists())

    ready = not fails
    print("\nENTERPRISE READINESS: " + ("READY" if ready else f"NOT READY ({len(fails)} gaps)"))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
