#!/usr/bin/env python3
"""certify_commercial_phase1 — software asset inventory + IP/license gate + readiness auditor +
first sellable wedge ranker.

No sellable asset with unknown ownership or blocked license; a prototype is never sell_now; the
wedge ranker excludes blocked/unknown/internal-only and recommends with rationale + requires
founder approval.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial import assets, ip_license, readiness, wedge_ranker   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)

DIMS = readiness.DIMENSIONS


def main() -> int:
    t0 = time.perf_counter()
    print("COMMERCIAL PHASE 1 — inventory + IP/license + readiness + first wedge")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "P1Cert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            assets.seed(N, store=st)
            inv = assets.inventory(N, store=st)
            ck("1. inventory seeded; every asset classified (no unclassified in claimed inventory)",
               inv["assets"] and all(a.get("commercial_readiness") for a in inv["assets"]))
            a0 = inv["assets"][0]["asset_id"]; a1 = inv["assets"][1]["asset_id"]

            # IP/license gate
            ck("2. unknown ownership BLOCKS selling",
               not ip_license.can_sell(N, a0, store=st)["allowed"])
            ip_license.set_status(N, a0, ip_status="blocked", store=st)
            ck("3. blocked IP BLOCKS selling",
               "IP blocked" in str(ip_license.can_sell(N, a0, store=st)["blockers"]))
            ip_license.set_status(N, a1, ip_status="owned", license_status="clear",
                                  security_status="safe_to_demo", store=st)
            ck("4. owned + clear + safe asset CAN proceed", ip_license.can_sell(N, a1, store=st)["allowed"])
            # private data / secrets block
            a2 = inv["assets"][2]["asset_id"]
            ip_license.set_status(N, a2, ip_status="owned", license_status="clear",
                                  has_secrets=True, store=st)
            ck("5. embedded secrets BLOCK selling/demo",
               "secrets" in str(ip_license.can_sell(N, a2, store=st)["blockers"]))

            # readiness verdicts
            full = {d: 3 for d in DIMS}
            # a1 is owned/clear/safe + high scores + proof => sell_now
            assets.audit_readiness(N, a1, readiness="sellable", findings="demoable", store=st)
            v1 = readiness.audit(N, a1, scores=full, proof_present=True, store=st)
            ck("6. a cleared, high-scoring, proven asset => sell_now", v1["verdict"] == "sell_now")
            # a research/prototype asset can never be sell_now (a2 has secrets anyway -> needs_legal/kill)
            # build a prototype asset explicitly
            pa = assets.add_asset(N, "Proto Tool", "early prototype", maturity="prototype", store=st)["asset"]
            ip_license.set_status(N, pa["asset_id"], ip_status="owned", license_status="clear",
                                  security_status="safe_to_demo", store=st)
            vp = readiness.audit(N, pa["asset_id"], scores=full, proof_present=True, store=st)
            ck("7. a prototype is NEVER sell_now (=> validate_first)", vp["verdict"] == "validate_first")
            # blocked asset can't proceed
            vb = readiness.audit(N, a0, scores=full, proof_present=True, store=st)
            ck("8. a blocked-IP asset cannot be sell_now", vb["verdict"] in ("kill", "needs_legal_review"))

            # wedge ranker
            fs = {a1: {f: 3 for f in wedge_ranker.FACTORS}}
            r = wedge_ranker.rank(N, factor_scores=fs, store=st)
            ck("9. the wedge ranker recommends a first wedge with rationale + requires approval",
               r["recommended_first_wedge"] and r["why_this_first"] and r["approval_required"])
            ck("10. blocked / unknown / internal-only assets are EXCLUDED from the wedge",
               any("blocked" in e["why"].lower() or "unknown" in e["why"].lower()
                   for e in r["why_not_the_others"]))
            ck("11. the wedge report is written (evidence)",
               (ROOT / "reports" / "first_sellable_wedge.json").exists())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_commercial_phase1", "green" if green else "red",
                files_observed=["anima/commercial/assets.py", "anima/commercial/ip_license.py",
                                "anima/commercial/readiness.py", "anima/commercial/wedge_ranker.py"],
                report_paths=["reports/first_sellable_wedge.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMMERCIAL-PHASE1 CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
