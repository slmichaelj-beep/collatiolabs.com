#!/usr/bin/env python3
"""certify_trust_moat — proof library + receipts + permissions + reputation, every gate.

Proof needs evidence; privacy proof needs a basis; stale/draft proof can't back a public claim;
customer-outcome proof needs permission; a case study needs a permissioned proof; QA + delivery
receipts are created; reputation reflects real data and a poor score blocks scale.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.trust import moat as m, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("TRUST / PROOF / REPUTATION MOAT — proof library / receipts / permissions / reputation")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "TrustCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            ck("1. proof without evidence is refused",
               not m.add_proof(N, offer_id="o1", proof_type="cert", claim_supported="52/52 green", evidence_refs=[], store=st)["ok"])
            ck("2. a privacy proof without a basis is refused",
               not m.add_proof(N, offer_id="o1", proof_type="privacy", claim_supported="no data sale",
                               evidence_refs=["policy"], privacy_basis="", store=st)["ok"])
            p = m.add_proof(N, offer_id="o1", proof_type="cert", claim_supported="52/52 certs green",
                            evidence_refs=["reports/master.json"], store=st)["proof"]
            ck("3. an active, evidence-backed proof can back a public claim",
               m.can_claim_publicly(N, p["proof_id"], store=st)["allowed"])
            m.mark_stale(N, p["proof_id"], store=st)
            ck("4. a stale proof cannot back a public claim",
               not m.can_claim_publicly(N, p["proof_id"], store=st)["allowed"])

            co = m.add_proof(N, offer_id="o1", proof_type="customer_outcome", claim_supported="saved 10h/wk",
                             evidence_refs=["email"], store=st)["proof"]
            ck("5. a customer-outcome proof requires permission to claim publicly",
               not m.can_claim_publicly(N, co["proof_id"], store=st)["allowed"])
            ck("6. a case study cannot be built without permission",
               not m.case_study(N, proof_id=co["proof_id"], headline="Acme saved 10h", store=st)["ok"])
            m.grant_permission(N, co["proof_id"], permission_ref="signed_consent_1", store=st)
            ck("7. with permission, the outcome can be claimed publicly",
               m.can_claim_publicly(N, co["proof_id"], store=st)["allowed"])
            ck("8. a case study builds from a permissioned proof",
               m.case_study(N, proof_id=co["proof_id"], headline="Acme saved 10h", store=st)["ok"])

            ck("9. a QA receipt is created with checks", m.qa_receipt(N, work_order_id="wo1", requested="audit",
               delivered="report", checks=["accuracy", "completeness"], store=st)["qa_receipt"]["passed"])
            ck("10. a delivery receipt records producer + time",
               m.delivery_receipt(N, work_order_id="wo1", produced_by="vera+human-review", delivery_time="3d",
                                  store=st)["delivery_receipt"]["produced_by"] == "vera+human-review")

            ck("11. a poor reputation blocks scale",
               not m.reputation(N, quality_score=0.5, refund_rate=0.3, store=st)["reputation"]["scale_allowed"])
            ck("12. a healthy reputation allows scale",
               m.reputation(N, quality_score=0.9, refund_rate=0.05, store=st)["reputation"]["scale_allowed"])

            d = api.dashboard(N, store=st)
            ck("13. the dashboard shows proofs + reputation + honest claim policy",
               d["ok"] and "stale proof is blocked" in d["honesty"])
            ck("14. the dashboard counts stale proof honestly", d["stale_proofs"] >= 1)
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_trust_moat", "green" if green else "red",
                files_observed=["anima/trust/moat.py"], report_paths=["reports/trust_reputation_moat.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nTRUST-MOAT CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
