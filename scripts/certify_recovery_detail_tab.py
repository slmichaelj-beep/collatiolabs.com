#!/usr/bin/env python3
"""certify_recovery_detail_tab — the Recovery / Fallback tab carries row-level evidence."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from certify_verification_detail_tabs import verify_tab
if __name__ == "__main__":
    print("RECOVERY DETAIL TAB — row-level evidence")
    raise SystemExit(verify_tab("recovery"))
