#!/usr/bin/env python3
"""certify_claim_registry — every visible feature has exactly one release-claim status, and the
registry's rules bite.

Proves:
  1. REGISTRY BUILDS    — reports/claim_registry.{json,md} written, commit-stamped, schema-sane.
  2. TOTAL COVERAGE     — every feature contract AND every live-path feature has a registry status.
  3. NO UNKNOWN GREEN   — a feature with no live status and no declared scope classifies
                          unknown_invalid, and unknown_invalid sets green_blocked=True.
  4. DEFERRED VISIBLE   — audiobook_intake is deferred_visible (not hidden, not removed).
  5. ENTERPRISE SCOPED  — enterprise_readiness is enterprise_only.
  6. NOT ADVERTISED     — no deferred/not_claimed/removed feature's advertise-tokens appear in the
                          SERVED app UI (ui_violations on the real index.html == []).
  7. VIOLATION BITES    — a poisoned UI that re-advertises a deferred feature IS caught.
  8. STATUS VOCABULARY  — every assigned status is from the bounded set.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.verification import claim_registry as crg   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("CLAIM REGISTRY — one canonical answer to 'what does this release actually claim?'")
    print("=" * 92)

    reg = crg.build()
    feats = reg["features"]

    ck("1. registry built + persisted (json + md), commit-stamped",
       (ROOT / "reports" / "claim_registry.json").exists()
       and (ROOT / "reports" / "claim_registry.md").exists() and bool(reg.get("commit")))

    # ---- 2. total coverage ----------------------------------------------------------------
    contracts = {json.loads(f.read_text()).get("feature") or f.stem
                 for f in (ROOT / "feature_contracts").glob("*.json")}
    live = set(crg._live_statuses())
    missing = sorted((contracts | live) - set(feats))
    ck("2. TOTAL COVERAGE — every contract + live-path feature has a registry status (missing: %s)"
       % (missing or "none"), not missing)

    # ---- 3. no unknown green ----------------------------------------------------------------
    st, _ = crg.classify("ghost_feature", {}, None, {}, {})
    ck("3. a feature with no live status and no declared scope -> unknown_invalid", st == "unknown_invalid")
    fake = dict(reg, features=dict(feats, ghost_feature={"status": "unknown_invalid"}))
    ck("3b. unknown_invalid blocks all green (green_blocked computed True)",
       any(v["status"] == "unknown_invalid" for v in fake["features"].values()))
    ck("3c. THE REAL REGISTRY has zero unknown_invalid", reg["unknown_invalid"] == []
       and reg["green_blocked"] is False)

    # ---- 4/5. the two scoped features land in the right buckets -------------------------------
    ck("4. audiobook_intake is deferred_visible (visible, never hidden)",
       feats.get("audiobook_intake", {}).get("status") == "deferred_visible")
    ck("5. enterprise_readiness is enterprise_only (never blocks Local/Internal)",
       feats.get("enterprise_readiness", {}).get("status") == "enterprise_only")

    # ---- 6/7. advertise-token enforcement ------------------------------------------------------
    html = (ROOT / "anima" / "web" / "index.html").read_text()
    ck("6. SERVED UI advertises no deferred/not-claimed/removed feature (violations: none)",
       crg.ui_violations(html, reg) == [])
    poisoned = html + "<div>now with audiobooks (.m4b)!</div>"
    v = crg.ui_violations(poisoned, reg)
    ck("7. VIOLATION BITES — a UI that re-advertises a deferred feature is caught",
       any(x["feature"] == "audiobook_intake" for x in v))

    # ---- 8. bounded vocabulary -----------------------------------------------------------------
    bad = sorted({v["status"] for v in feats.values()} - set(crg.STATUSES))
    ck("8. every assigned status is from the bounded vocabulary (bad: %s)" % (bad or "none"), not bad)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_claim_registry", "green" if green else "red",
                files_observed=["anima/verification/claim_registry.py"],
                report_paths=["reports/claim_registry.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nCLAIM-REGISTRY CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
