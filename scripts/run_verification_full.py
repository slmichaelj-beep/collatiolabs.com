#!/usr/bin/env python3
"""run_verification_full — the works (directive §28): the live UI smoke, then Diamond v2 repeatability
(which runs the full gate N times on the same head), then the computed §28 verdict."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def step(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *args[1:]], cwd=str(ROOT)).returncode
def main() -> int:
    print("VERIFICATION FULL — live UI smoke + Diamond v2 repeatability + verdict")
    print("=" * 60)
    step("certify_browser_surface_routes.py")
    step("certify_headless_dom_paint.py")
    rc = step("run_diamond_v2.py", "--gate", "--runs", "3")
    print("\n=== computed §28 verdict ===")
    step("verification_status.py")
    return rc
if __name__ == "__main__":
    raise SystemExit(main())
