#!/usr/bin/env python3
"""certify_consent_data_control_detail_tab — the Consent / Privacy / Data Control tab carries row-level evidence."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from certify_verification_detail_tabs import verify_tab
if __name__ == "__main__":
    print("CONSENT / DATA CONTROL DETAIL TAB — row-level evidence")
    raise SystemExit(verify_tab("consent_privacy"))
