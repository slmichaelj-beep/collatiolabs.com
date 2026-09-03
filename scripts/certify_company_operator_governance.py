#!/usr/bin/env python3
"""certify_company_operator_governance — governed autonomy holds. Nothing external fires without
authority + approval + budget; the kill switch stops everything; financial/legal/account actions
are human-only.

Hermetic on a scratch company store.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.company import storage as cstore   # noqa: E402
from anima.company_operator import authority, approvals, budget, action_ledger, kill_switch  # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMPANY OPERATOR GOVERNANCE — no external action without authority+approval+budget")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "GovCert"

        # ---- 1. default is think-only -------------------------------------------------------
        ck("1. default authority is L0 (think-only)", authority.current_level(N, store=st) == 0)
        ck("1b. think/plan/draft is always permitted",
           authority.permits(N, "plan", store=st)["permitted"]
           and authority.permits(N, "draft", store=st)["permitted"])

        # ---- 2. at L0 every external action is blocked --------------------------------------
        for at in ("publish", "send_message", "spend", "create_account"):
            ck("2. L0 blocks %s" % at, not authority.permits(N, at, store=st)["permitted"])

        # ---- 3. action ledger blocks an external action at L0 (and records it) --------------
        r = action_ledger.perform(N, "publish", "ship the landing page", store=st)
        ck("3. perform(publish) at L0 is BLOCKED + recorded as blocked",
           not r["ok"] and r["blocked"] and r["action"]["result"] == "blocked")

        # ---- 4. raising authority unlocks the class, but approval is still required ----------
        authority.set_level(N, 3, store=st)  # bounded_execution
        r = action_ledger.perform(N, "publish", "ship the landing page", store=st)
        ck("4. L3 publish WITHOUT an approval is still blocked",
           not r["ok"] and "approved approval" in r["reason"].lower())

        # ---- 5. an approved packet lets the action through ----------------------------------
        ap = approvals.create(N, "Publish landing page", "publish", store=st)["approval"]
        approvals.decide(N, ap["approval_id"], "approved", store=st)
        r = action_ledger.perform(N, "publish", "ship the landing page",
                                  approval_ref=ap["approval_id"], store=st)
        ck("5. L3 publish WITH an approved packet succeeds + is recorded",
           r["ok"] and r["action"]["result"] == "success")
        ck("5b. a rejected packet does NOT let the action through",
           (lambda a: (approvals.decide(N, a["approval_id"], "rejected", store=st),
                       not action_ledger.perform(N, "publish", "x", approval_ref=a["approval_id"],
                                                  store=st)["ok"])[1])(
               approvals.create(N, "Publish v2", "publish", store=st)["approval"]))

        # ---- 6. spend needs budget ----------------------------------------------------------
        authority.set_level(N, 4, store=st)  # budgeted autonomy
        ap2 = approvals.create(N, "Buy a domain", "spend", cost=12.0, store=st)["approval"]
        approvals.decide(N, ap2["approval_id"], "approved", store=st)
        r = action_ledger.perform(N, "spend", "domain", cost=12.0, approval_ref=ap2["approval_id"], store=st)
        ck("6. a spend with NO approved budget is blocked", not r["ok"] and "budget" in r["reason"].lower())
        budget.approve_budget(N, total=100.0, per_transaction_cap=50.0, store=st)
        r = action_ledger.perform(N, "spend", "domain", cost=12.0, approval_ref=ap2["approval_id"], store=st)
        ck("6b. ...the same spend succeeds once a budget is approved + records the spend",
           r["ok"] and budget.get(N, store=st)["spent"] == 12.0)
        # over per-transaction cap
        ap3 = approvals.create(N, "Big buy", "spend", cost=80.0, store=st)["approval"]
        approvals.decide(N, ap3["approval_id"], "approved", store=st)
        r = action_ledger.perform(N, "spend", "big", cost=80.0, approval_ref=ap3["approval_id"], store=st)
        ck("6c. a spend over the per-transaction cap is blocked", not r["ok"])

        # ---- 7. financial/legal/account actions are HUMAN-ONLY at every level ----------------
        authority.set_level(N, 5, store=st)  # regulated — the highest
        for at in ("bank_transfer", "tax_filing", "patent_filing", "sign_contract", "create_account"):
            p = authority.permits(N, at, store=st)
            ck("7. %s is HUMAN-ONLY even at L5" % at, not p["permitted"] and p.get("human_only"))

        # ---- 8. kill switch stops everything ------------------------------------------------
        kill_switch.engage(N, by="owner", reason="cert", store=st)
        ap4 = approvals.create(N, "Publish after kill", "publish", store=st)["approval"]
        approvals.decide(N, ap4["approval_id"], "approved", store=st)
        r = action_ledger.perform(N, "publish", "should be blocked",
                                  approval_ref=ap4["approval_id"], store=st)
        ck("8. with the KILL SWITCH engaged, even an approved action at L5 is blocked",
           not r["ok"] and "kill switch" in r["reason"].lower())
        ck("8b. queued approvals are preserved through a kill (not deleted)",
           approvals.get(N, ap4["approval_id"], store=st) is not None)
        ck("8c. disengage requires explicit confirm",
           not kill_switch.disengage(N, store=st)["ok"]
           and kill_switch.disengage(N, confirm=True, store=st)["ok"])

        # ---- 9. every action (success + blocked) is in the ledger ----------------------------
        hist = action_ledger.history(N, store=st)
        ck("9. every attempt is recorded in the action ledger (success + blocked)",
           len(hist) >= 6 and any(a["result"] == "blocked" for a in hist)
           and any(a["result"] == "success" for a in hist))
        ck("9b. every action records its gate verdicts (authority/approval/budget)",
           all("gates" in a for a in hist))

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_company_operator_governance", "green" if green else "red",
                files_observed=["anima/company_operator/authority.py",
                                "anima/company_operator/approvals.py",
                                "anima/company_operator/budget.py",
                                "anima/company_operator/action_ledger.py",
                                "anima/company_operator/kill_switch.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMPANY-OPERATOR-GOVERNANCE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
