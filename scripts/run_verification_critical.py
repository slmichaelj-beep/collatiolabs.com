#!/usr/bin/env python3
"""run_verification_critical — the critical gates (directive §28): the full live-path Program Reality
gate (one pass) + the computed verdict. Heavier than smoke; lighter than --full (no 3x repeatability)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def main() -> int:
    print("VERIFICATION CRITICAL — full live-path gate (single pass) + verdict")
    print("=" * 60)
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_live_paths.py"), "--gate"],
                        cwd=str(ROOT)).returncode
    print("\n=== computed verdict ===")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "verification_status.py")], cwd=str(ROOT))
    return rc
if __name__ == "__main__":
    raise SystemExit(main())
