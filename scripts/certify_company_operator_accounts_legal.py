#!/usr/bin/env python3
"""certify_company_operator_accounts_legal — account registry + legal/IP prep + department operators.

Accounts are PLANNED + REGISTERED, never silently created; no raw credentials stored; KYC/bank are
human-required. Legal/IP is drafts + attorney packets only — filings + signatures blocked.
Departments are governed role modules (forbidden/approval/allowed) under the authority ladder.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company_operator import accounts, legal_ip, departments, authority   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("ACCOUNTS / LEGAL / DEPARTMENTS — planned, drafted, governed; nothing executed")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "AcctLegalCert"

        # ---- accounts ----------------------------------------------------------------------
        em = accounts.plan_account(N, "Google Workspace", "email", purpose="business email", store=st)
        ck("1. an account is PLANNED (status=planned), not created",
           em["status"] == "planned" and em["account_id"])
        ck("1b. 2FA + recovery + ownership are recorded; creds go to a manager (never Vera)",
           em["requires_2fa"] and em["recovery_plan"] and "password_manager" in em["credentials_location"])
        bank = accounts.plan_account(N, "Mercury", "banking", requires_kyc=True, requires_bank=True, store=st)
        ck("2. a banking/KYC account is HUMAN-required (never Vera-created)",
           bank["creation_method"] == "human_required" and bank["requires_human_identity"])
        ck("3. Vera REFUSES to store raw credentials",
           not accounts.store_credentials(N, em["account_id"], "hunter2", store=st)["ok"])
        ck("4. comms accounts carry an anti-spam/posting policy in the checklist",
           any("anti-spam" in c for c in em["checklist"]))

        # ---- legal / IP ---------------------------------------------------------------------
        ck("5. a legal checklist needs a jurisdiction", not legal_ip.legal_checklist(N, "", store=st)["ok"])
        lc = legal_ip.legal_checklist(N, "US-DE", store=st)
        ck("6. entity formation / trademark / patent are filing_blocked in the checklist",
           lc["ok"] and all(any(i["area"] == a and i["action_level"] == "filing_blocked"
                                for i in lc["checklist"]["items"])
                            for a in ("entity_formation", "trademark", "patent")))
        ck("7. Vera can NEVER file or sign",
           not legal_ip.can_file(N, "patent")["allowed"]
           and not legal_ip.can_sign_contract(N)["allowed"])
        inv = legal_ip.invention_disclosure(N, "Local truth-ledger memory", problem="provenance",
                                            mechanism="append-only ledger", store=st)
        ck("8. an invention disclosure is prepared with patentability UNCERTAIN + filing blocked",
           inv["ok"] and inv["disclosure"]["filing_status"] == "blocked_pending_human"
           and "UNCERTAIN" in inv["disclosure"]["patentability"])

        # ---- departments --------------------------------------------------------------------
        d = departments.spin_up(N, "marketing", "awareness + growth under policy", store=st)
        ck("9. a department operator spins up with allowed/approval/forbidden sets",
           d["ok"] and d["department"]["forbidden_actions"] and d["department"]["approval_required_actions"])
        ck("10. a forbidden action is refused for the department",
           not departments.can_act(N, "finance_ops", "bank_transfer", store=st)["allowed"])
        ck("11. an approval-required action is queued, not auto-run",
           departments.can_act(N, "marketing", "spend", store=st).get("needs_approval") is True)
        # allowed action still gated by the global authority ladder (L0 default => draft ok, plan ok)
        ck("12. an allowed draft/plan action passes the authority ladder at L0; publish does not",
           departments.can_act(N, "strategy", "plan", store=st)["allowed"]
           and not departments.can_act(N, "product", "publish", store=st)["allowed"])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_company_operator_accounts_legal", "green" if green else "red",
                files_observed=["anima/company_operator/accounts.py",
                                "anima/company_operator/legal_ip.py",
                                "anima/company_operator/departments.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nACCOUNTS-LEGAL-DEPARTMENTS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
