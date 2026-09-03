#!/usr/bin/env python3
"""certify_commercial_phase2 — offer packaging: pricing recommendation, proof builder, landing
draft, proposal/SOW draft.

Price is always a recommendation (never a commitment); proof never fabricates (gaps stay gaps);
landing is never published; proposal is never sent and contracts are human-only.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial import assets, ip_license, pricing, proof, landing, proposal  # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMMERCIAL PHASE 2 — pricing + proof + landing + proposal/SOW")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "P2Cert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            assets.seed(N, store=st)
            a = assets.inventory(N, store=st)["assets"]
            aid = a[0]["asset_id"]
            ip_license.set_status(N, aid, ip_status="owned", license_status="clear",
                                  security_status="safe_to_demo", store=st)

            # pricing
            pr = pricing.recommend(N, aid, model="subscription_annual", value_per_year=100000,
                                   comparables=[12000, 18000], ability_to_pay="mid", store=st)
            ck("1. pricing yields a range, not a single committed number",
               pr["recommended_range"]["low"] < pr["recommended_range"]["high"])
            ck("2. pricing is explicitly a recommendation, NOT a commitment",
               pr["is_recommendation"] and not pr["is_commitment"])
            ck("3. binding price requires human approval",
               "human" in pr["binding_requires"].lower())

            # proof — verified vs gaps; no fabrication
            pf = proof.build(N, aid, proofs=[
                {"kind": "cert_report", "claim": "52/52 certs green", "evidence_ref": "reports/x.json"},
                {"kind": "metric", "claim": "saves 10h/wk", "evidence_ref": ""},   # no evidence => gap
            ], store=st)
            ck("4. a proof with evidence is verified; one without is a GAP (not claimed)",
               len(pf["verified_proofs"]) == 1 and len(pf["gaps"]) == 1)
            ck("5. proof builder forbids fabrication", "invent" in pf["no_fabrication"].lower())

            # demo blocked when not sell-gate clear (secrets)
            aid2 = a[1]["asset_id"]
            ip_license.set_status(N, aid2, ip_status="owned", license_status="clear",
                                  has_secrets=True, store=st)
            pf2 = proof.build(N, aid2, proofs=[], store=st)
            ck("6. demo is BLOCKED when the asset isn't sell-gate clear (secrets)",
               not pf2["demo_allowed"] and pf2["demo_blocked_reason"])

            # landing draft — not published; only verified claims surface
            ld = landing.draft(N, aid, headline="Ship audited software faster",
                               subhead="from inventory to first sale",
                               value_bullets=["honest readiness", "governed sales"],
                               verified_claims=pf["verified_proofs"], store=st)
            ck("7. landing is a DRAFT and explicitly NOT published",
               ld["status"] == "draft" and "not published" in ld["publish_status"].lower())
            ck("8. landing proof section carries only verified claims",
               len(ld["proof_section"]) == 1)
            ck("9. landing renders to previewable HTML", "<h1>" in landing.render_html(ld))

            # proposal/SOW — not sent, contract human-only
            sow = proposal.draft(N, aid, client="Acme", scope=["pilot"],
                                 deliverables=["deploy", "train"], timeline="4 weeks",
                                 price_recommendation=18000, store=st)
            ck("10. proposal price is a recommendation, not a commitment",
               not sow["price_is_commitment"])
            ck("11. proposal is NOT sent and contracts are HUMAN-ONLY",
               "not sent" in sow["send_status"].lower() and "human-only" in sow["sign_status"].lower())
            ck("12. proposal renders to a markdown draft",
               "DRAFT" in proposal.render_md(sow))
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_commercial_phase2", "green" if green else "red",
                files_observed=["anima/commercial/pricing.py", "anima/commercial/proof.py",
                                "anima/commercial/landing.py", "anima/commercial/proposal.py"],
                report_paths=[], duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMMERCIAL-PHASE2 CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
