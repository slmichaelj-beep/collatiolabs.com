#!/usr/bin/env python3
"""certify_security_detail_tab — the Security / AI Safety tab carries row-level evidence."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from certify_verification_detail_tabs import verify_tab
if __name__ == "__main__":
    print("SECURITY DETAIL TAB — row-level evidence")
    raise SystemExit(verify_tab("ai_security"))
