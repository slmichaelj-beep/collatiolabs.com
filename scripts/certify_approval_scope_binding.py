#!/usr/bin/env python3
"""certify_approval_scope_binding — approval packets bind to the exact action envelope.

An approval is not a bearer token. This cert proves an approved packet cannot be replayed across
action type, cost, vendor, category, subject, risk, or a second execution after it has been consumed.

Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.company_operator import action_ledger, approvals, authority, budget  # noqa: E402

oks, fails = [], []


def ck(label: str, cond: bool):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _approve(name: str, title: str, action_type: str, st: Path, **kw) -> str:
    ap = approvals.create(name, title, action_type, store=st, **kw)["approval"]
    approvals.decide(name, ap["approval_id"], "approved", store=st)
    return ap["approval_id"]


def main() -> int:
    t0 = time.perf_counter()
    print("APPROVAL SCOPE BINDING — approvals match the exact action envelope")
    print("=" * 82)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        name = "ApprovalScopeCert"
        authority.set_level(name, 4, store=st)
        budget.approve_budget(name, total=1000.0, category_caps={"software": 500.0},
                              per_transaction_cap=500.0, store=st)

        pub = _approve(name, "Publish landing page", "publish", st, subject="landing-v1")
        wrong_type = action_ledger.perform(
            name, "send_message", "send launch email", approval_ref=pub, subject="landing-v1", store=st
        )
        ck("1. a publish approval cannot authorize send_message",
           not wrong_type["ok"] and "scoped" in wrong_type["reason"])

        exact = _approve(name, "Buy API credits", "spend", st, cost=100.0, category="software",
                         vendor="OpenAI", subject="api-credits", risk="medium")
        ok = action_ledger.perform(
            name, "spend", "buy API credits", approval_ref=exact, cost=100.0,
            category="software", vendor="OpenAI", subject="api-credits", risk="medium", store=st
        )
        ck("2. the matching spend action succeeds", ok["ok"] and ok["action"]["result"] == "success")
        ck("3. the matching approval is consumed after success",
           approvals.get(name, exact, store=st)["status"] == "executed")

        replay = action_ledger.perform(
            name, "spend", "replay API credits", approval_ref=exact, cost=100.0,
            category="software", vendor="OpenAI", subject="api-credits", risk="medium", store=st
        )
        ck("4. an executed approval cannot be replayed",
           not replay["ok"] and "executed" in replay["reason"])

        too_much = _approve(name, "Small software buy", "spend", st, cost=50.0,
                            category="software", vendor="OpenAI")
        over = action_ledger.perform(
            name, "spend", "oversized software buy", approval_ref=too_much, cost=75.0,
            category="software", vendor="OpenAI", store=st
        )
        ck("5. action cost cannot exceed the approval ceiling",
           not over["ok"] and "cost ceiling" in over["reason"])

        vendor_ap = _approve(name, "Approved vendor buy", "spend", st, cost=25.0,
                             category="software", vendor="OpenAI")
        wrong_vendor = action_ledger.perform(
            name, "spend", "wrong vendor buy", approval_ref=vendor_ap, cost=25.0,
            category="software", vendor="Anthropic", store=st
        )
        ck("6. vendor-scoped approval refuses a different vendor",
           not wrong_vendor["ok"] and "vendor" in wrong_vendor["reason"])

        cat_ap = _approve(name, "Software buy", "spend", st, cost=25.0, category="software")
        wrong_cat = action_ledger.perform(
            name, "spend", "hardware buy", approval_ref=cat_ap, cost=25.0,
            category="hardware", store=st
        )
        ck("7. category-scoped approval refuses a different category",
           not wrong_cat["ok"] and "category" in wrong_cat["reason"])

        subj_ap = _approve(name, "Message lead A", "send", st, subject="lead-a")
        wrong_subject = action_ledger.perform(
            name, "send_message", "message lead B", approval_ref=subj_ap, subject="lead-b", store=st
        )
        ck("8. subject-scoped approval refuses a different subject",
           not wrong_subject["ok"] and "subject" in wrong_subject["reason"])

        risk_ap = _approve(name, "Low-risk send", "send", st, risk="low")
        high_risk = action_ledger.perform(
            name, "send_message", "high-risk send", approval_ref=risk_ap, risk="high", store=st
        )
        ck("9. low-risk approval refuses a higher-risk action",
           not high_risk["ok"] and "risk" in high_risk["reason"])

        hist = action_ledger.history(name, store=st)
        ck("10. every refused mismatch is still recorded in the action ledger",
           len([x for x in hist if x["result"] == "blocked"]) >= 7
           and all("approval_ref" in x and "gates" in x for x in hist))

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_approval_scope_binding", "green" if green else "red",
                files_observed=[
                    "anima/company_operator/approvals.py",
                    "anima/company_operator/action_ledger.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nAPPROVAL-SCOPE-BINDING CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
