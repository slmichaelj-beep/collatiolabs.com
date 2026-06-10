#!/usr/bin/env python3
"""certify_collatio_authority_layer — Collatio Labs LLC operating-authority layer, every gate.

Unknown entity facts stay unknown (no invented facts; verified facts need evidence). Records:
missing creates a task, secrets refused. Filings: unknown jurisdiction blocks a due date; filing
needs approval. Authority: L0 default; external needs approval; legal/tax/contract need professional
review; forbidden blocked. Accounts: KYC/banking human-only; creation needs approval; no raw creds.
Contracts: Vera never signs; customer commitment needs approval + capacity. IP: unknown ownership
blocks sale.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.collatio import (entity as e, authority as au, filings as f, accounts as ac,  # noqa: E402
                            contracts as c, ip_assets as ip, api)

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COLLATIO AUTHORITY LAYER — entity / records / filings / authority / accounts / contracts / IP")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "CollCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            p = e.profile(N, store=st)
            ck("1. entity profile exists with unknown facts left unknown",
               p["jurisdiction"] == e.UNKNOWN and p["ein_status"] == "unknown")
            ck("2. a verified fact without evidence is refused (no invented facts)",
               not e.verify_fact(N, "jurisdiction", "DE", evidence_ref="", store=st)["ok"])
            ck("3. a verified fact with evidence is recorded",
               e.verify_fact(N, "jurisdiction", "DE", evidence_ref="formation.pdf", store=st)["ok"])

            ck("4. a missing record becomes a task (not a fake fact)",
               e.note_missing(N, record_type="formation", title="Articles of Organization", store=st)["ok"]
               and "Articles of Organization" in e.records(N, st)["missing"])
            ck("5. a record with raw secrets is refused",
               not e.register_record(N, record_type="banking", title="bank", storage_ref="password: hunter2", store=st)["ok"])

            fil = f.create_filing(N, filing_type="annual_report", description="DE annual report",
                                  jurisdiction=e.UNKNOWN, due_date="2026-12-31", store=st)["filing"]
            ck("6. unknown jurisdiction blocks an authoritative due-date claim", fil["due_date"] is None)
            ck("7. a filing cannot be filed without approval (Vera never files)",
               not f.file_action(N, fil["filing_id"], approval_ref="", store=st)["ok"])
            ck("8. tax/accounting packet prepares but never files/moves money",
               "human" in f.build_packet(N, packet_type="cpa_packet", items=["q1"], store=st)["packet"]["filing_action"].lower())

            ck("9. authority defaults to L0 think-only", au.policy(N, st)["default_level"] == "L0")
            ck("10. research is allowed without approval", au.can_do(N, "research", store=st)["allowed"])
            ck("11. an external message needs approval",
               not au.can_do(N, "external_message", store=st)["allowed"])
            ck("12. a legal filing needs professional review + approval",
               not au.can_do(N, "legal_filing", approval_ref="x", store=st)["allowed"])
            ck("13. a forbidden action (fake identity) is blocked",
               not au.can_do(N, "fake_identity", store=st)["allowed"])

            bank = ac.register(N, service_name="Mercury", category="banking", store=st)["account"]
            ck("14. a banking account is human-only (Vera cannot create it)",
               not ac.create_account_action(N, bank["account_id"], approval_ref="lamar", store=st)["ok"])
            email = ac.register(N, service_name="Fastmail", category="email", store=st)["account"]
            ck("15. a non-KYC account still needs approval to create",
               not ac.create_account_action(N, email["account_id"], approval_ref="", store=st)["ok"])
            ck("16. an approved non-KYC account can be created (2FA required, creds as ref only)",
               ac.create_account_action(N, email["account_id"], approval_ref="lamar", store=st)["ok"]
               and email["requires_2fa"] and email["credentials_location"] == "password_manager_ref_only")

            ct = c.draft_contract(N, counterparty="Acme", contract_type="customer", store=st)["contract"]
            ck("17. Vera never signs a contract (even with approval + review)",
               c.sign_action(N, ct["contract_id"], approval_ref="lamar", professional_review_ref="atty",
                             store=st).get("note", "").find("did not sign") >= 0)
            ck("18. a customer commitment without capacity check is refused",
               not c.customer_commitment(N, summary="24/7 support", approval_ref="lamar", capacity_ok=False, store=st)["ok"])
            ck("19. a review packet requires questions + is queued ready-for-lamar",
               c.review_packet(N, review_type="legal", title="OA review", summary="s", questions=["q1"], store=st)["review"]["status"] == "ready_for_lamar")

            a1 = ip.register_asset(N, title="Vera", asset_type="software", owner="unknown", store=st)["asset"]
            ck("20. an unknown-ownership asset cannot be sold by the entity",
               not ip.can_entity_sell(N, a1["asset_id"], store=st)["allowed"])
            a2 = ip.register_asset(N, title="Argus", asset_type="software", owner="Collatio Labs LLC",
                                   assignment_status="assigned", commercial_use_status="clear",
                                   license_status="clear", store=st)["asset"]
            ck("21. a clearly-owned, assigned, clear asset can be sold",
               ip.can_entity_sell(N, a2["asset_id"], store=st)["allowed"])

            d = api.dashboard(N, store=st)
            ck("22. the dashboard assembles entity/authority/records/filings/accounts/contracts/IP",
               d["ok"] and "human-only" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_collatio_authority_layer", "green" if green else "red",
                files_observed=["anima/collatio/entity.py", "anima/collatio/authority.py",
                                "anima/collatio/filings.py", "anima/collatio/accounts.py",
                                "anima/collatio/contracts.py", "anima/collatio/ip_assets.py"],
                report_paths=["reports/collatio_operating_authority_layer.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nCOLLATIO-AUTHORITY-LAYER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
