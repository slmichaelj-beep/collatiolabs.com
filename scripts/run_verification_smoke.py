#!/usr/bin/env python3
"""run_verification_smoke — the FAST live check (directive §28): build identity + the served-app UI
smoke (surface routes + headless DOM paint), then the computed verdict. No full gate (use --full)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def step(name, *args):
    print("\n--- %s ---" % name, flush=True)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *args[1:]], cwd=str(ROOT)).returncode
def main() -> int:
    print("VERIFICATION SMOKE — build identity + live user reality (fast)")
    print("=" * 60)
    step("deploy / build identity", "deploy_check.py")
    rc1 = step("live UI: surface routes", "certify_browser_surface_routes.py")
    rc2 = step("live UI: headless DOM paint", "certify_headless_dom_paint.py")
    print("\n=== computed verdict ===")
    step("status", "verification_status.py")
    return 0 if (rc1 == 0 and rc2 == 0) else 1
if __name__ == "__main__":
    raise SystemExit(main())
