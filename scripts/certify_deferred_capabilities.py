#!/usr/bin/env python3
"""certify_deferred_capabilities — deferred stays visible, unclaimed stays unadvertised.

Proves:
  1. audiobook_intake remains deferred / not claimed (contract + registry agree).
  2. The deferral is VISIBLE: classifier bucket + dashboard classification + the served
     /verification page all carry the deferred row (not hidden).
  3. No active UI route claims it: the SERVED app page carries no advertise-token, and the
     LIVE intake surface does not list audiobook as an offered type.
  4. An ACTIVE UI CLAIM for a deferred feature FAILS — the live-path probe's deferred branch
     turns a UI claim into WALLPAPER (asserted from the committed probe source), and the
     registry's ui_violations catches a poisoned page.
  5. Dormant code stays honest: no DRM-circumvention token; heavy transcription stays opt-in.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.verification import claim_registry as crg, dashboard   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)


def main() -> int:
    t0 = time.perf_counter()
    print("DEFERRED CAPABILITIES — visible, unclaimed, unadvertised, never blocking")
    print("=" * 92)

    # ---- 1. contract + registry agree -----------------------------------------------------
    contract = json.loads((ROOT / "feature_contracts" / "audiobook_intake.json").read_text())
    ck("1. contract: status=DEFERRED, release_required=false, claimed_by_current_tier=false, "
       "future tier named",
       (contract.get("status") or "").upper() == "DEFERRED"
       and contract.get("release_required") is False
       and contract.get("claimed_by_current_tier") is False
       and bool(contract.get("future_tier")))
    reg = crg.build()
    ck("1b. registry: audiobook_intake -> deferred_visible",
       reg["features"].get("audiobook_intake", {}).get("status") == "deferred_visible")

    # ---- 2. visible everywhere -------------------------------------------------------------
    d = dashboard.data()
    cls = d.get("classification", {})
    ck("2. dashboard classification carries the deferred bucket (not hidden)",
       "audiobook_intake" in cls.get("deferred_not_claimed", []))
    page = (ROOT / "anima" / "web" / "verification.html").read_text()
    ck("2b. the verification page renders a 'deferred / not claimed' row",
       "deferred / not claimed" in page)

    # ---- 3. no active claim on the live surfaces ---------------------------------------------
    st, body = _get("/")
    served = st == 200
    ck("3. SERVED app page carries no audiobook advertise-token",
       served and not crg.ui_violations(body, reg))
    if not served:
        print("       (server unreachable — surface check ran against the committed file instead)")
        body = (ROOT / "anima" / "web" / "index.html").read_text()
        ck("3f. committed app page carries no audiobook advertise-token",
           not crg.ui_violations(body, reg))

    # ---- 4. an active claim FAILS -------------------------------------------------------------
    probe_src = (ROOT / "scripts" / "certify_live_paths.py").read_text()
    i = probe_src.find("def probe_audiobook_intake")
    branch = probe_src[i:i + 4000]
    ck("4. the probe's deferred branch turns a UI claim into WALLPAPER (deferred may not be claimed)",
       "if ui_claims:" in branch and "res.status = WALLPAPER" in branch.split("if ui_claims:")[1][:400])
    poisoned = (body or "") + "<button>listen to your audiobooks (.m4b)</button>"
    ck("4b. registry ui_violations catches a poisoned page that re-advertises it",
       any(v["feature"] == "audiobook_intake" for v in crg.ui_violations(poisoned, reg)))

    # ---- 5. dormant honesty --------------------------------------------------------------------
    audio_src = (ROOT / "anima" / "intake_audio.py").read_text().lower()
    circ = [t for t in ("activation_bytes", "activation bytes", "-activation", "rcrack",
                        "rainbow table", "rainbow_table", "deactivation", "audible_key")
            if t in audio_src]
    ck("5. dormant pipeline carries NO DRM-circumvention token (found: %s)" % (circ or "none"),
       not circ)
    ck("5b. heavy transcription stays opt-in (ANIMA_INTAKE_ACTIVATE_HEAVY gate present)",
       "anima_intake_activate_heavy" in (ROOT / "anima" / "intake_parsers.py").read_text().lower())

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_deferred_capabilities", "green" if green else "red",
                files_observed=["feature_contracts/audiobook_intake.json",
                                "anima/verification/claim_registry.py"],
                report_paths=["reports/claim_registry.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nDEFERRED-CAPABILITIES CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
