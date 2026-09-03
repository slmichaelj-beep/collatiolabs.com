#!/usr/bin/env python3
"""certify_budget_invariants - budget ledger defends itself on direct calls.

The budget module is a governance primitive, so it must enforce cumulative monthly/category caps
and validate approval refs even when future code calls it directly. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.company_operator import approvals, budget  # noqa: E402

oks, fails = [], []


def ck(label: str, cond: bool):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _approve(name: str, st: Path, *, amount: float, category: str = "", vendor: str = "",
             subject: str = "") -> str:
    rec = approvals.create(
        name, "Spend approval", "spend", cost=amount, category=category, vendor=vendor,
        subject=subject, store=st,
    )["approval"]
    approvals.decide(name, rec["approval_id"], "approved", store=st)
    return rec["approval_id"]


def main() -> int:
    t0 = time.perf_counter()
    print("BUDGET INVARIANTS - cumulative caps and direct approval validation")
    print("=" * 82)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        name = "BudgetInvariantCert"

        budget.approve_budget(name, total=1000.0, monthly_cap=100.0,
                              category_caps={"ads": 50.0}, per_transaction_cap=1000.0, store=st)
        first_ads = budget.record_spend(name, 40.0, category="ads", description="ad test", store=st)
        second_ads = budget.record_spend(name, 11.0, category="ads", description="ad over", store=st)
        ck("1. first category spend within cumulative cap succeeds", first_ads["ok"])
        ck("2. second category spend is blocked by cumulative category cap",
           not second_ads["ok"] and "category cap" in second_ads["error"])

        monthly = "BudgetMonthlyCert"
        budget.approve_budget(monthly, total=1000.0, monthly_cap=100.0,
                              per_transaction_cap=1000.0, store=st)
        m1 = budget.record_spend(monthly, 60.0, category="software", store=st)
        m2 = budget.record_spend(monthly, 41.0, category="software", store=st)
        ck("3. first monthly spend within cap succeeds", m1["ok"])
        ck("4. second monthly spend is blocked by cumulative monthly cap",
           not m2["ok"] and "monthly cap" in m2["error"])

        threshold = "BudgetApprovalCert"
        budget.approve_budget(threshold, total=1000.0, monthly_cap=1000.0,
                              approval_required_above=25.0, per_transaction_cap=1000.0, store=st)
        no_ap = budget.record_spend(threshold, 30.0, category="software", store=st)
        fake_ap = budget.record_spend(threshold, 30.0, category="software",
                                      approval_ref="not-real", store=st)
        ck("5. threshold spend without approval is blocked",
           not no_ap["ok"] and "approval_ref" in no_ap["error"])
        ck("6. fake approval refs are refused on direct budget calls",
           not fake_ap["ok"] and "no such approval" in fake_ap["error"])

        exact = _approve(threshold, st, amount=30.0, category="software", vendor="OpenAI",
                         subject="api-credits")
        exact_ok = budget.record_spend(
            threshold, 30.0, category="software", vendor="OpenAI", subject="api-credits",
            approval_ref=exact, store=st,
        )
        ck("7. exact spend approval succeeds on direct budget call", exact_ok["ok"])
        ck("8. exact spend approval is consumed after direct budget spend",
           approvals.get(threshold, exact, st)["status"] == "executed")

        replay = budget.record_spend(
            threshold, 30.0, category="software", vendor="OpenAI", subject="api-credits",
            approval_ref=exact, store=st,
        )
        ck("9. consumed direct-spend approval cannot be replayed",
           not replay["ok"] and "executed" in replay["error"])

        mismatch = _approve(threshold, st, amount=30.0, category="software", vendor="OpenAI")
        wrong_vendor = budget.record_spend(
            threshold, 30.0, category="software", vendor="Anthropic",
            approval_ref=mismatch, store=st,
        )
        ck("10. direct budget call refuses approval/action mismatch",
           not wrong_vendor["ok"] and "vendor" in wrong_vendor["error"])

        under = "BudgetUnderThresholdCert"
        budget.approve_budget(under, total=100.0, monthly_cap=100.0,
                              approval_required_above=25.0, store=st)
        bad_label = budget.record_spend(under, 10.0, approval_ref="not-real", store=st)
        clean_under = budget.record_spend(under, 10.0, store=st)
        ck("11. provided fake refs are refused even below threshold",
           not bad_label["ok"] and "no such approval" in bad_label["error"])
        ck("12. below-threshold spend without approval still succeeds", clean_under["ok"])

        exhausted = "BudgetExhaustionCert"
        budget.approve_budget(exhausted, total=50.0, monthly_cap=50.0, store=st)
        spent_all = budget.record_spend(exhausted, 50.0, store=st)
        ck("13. spending the full budget marks it exhausted",
           spent_all["ok"] and budget.get(exhausted, st)["status"] == "exhausted")

        negative = budget.record_spend(exhausted, -1.0, store=st)
        ck("14. negative spends are refused", not negative["ok"] and "positive" in negative["error"])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_budget_invariants", "green" if green else "red",
                files_observed=[
                    "anima/company_operator/budget.py",
                    "anima/company_operator/approvals.py",
                    "anima/company_operator/action_ledger.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nBUDGET-INVARIANTS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
