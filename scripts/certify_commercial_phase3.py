#!/usr/bin/env python3
"""certify_commercial_phase3 — governed sales sprint + board revenue briefing.

The sprint queues outreach for HUMAN approval (Vera never sends); unqualified leads can't be queued;
unapproved items can't be marked sent; the board briefing distinguishes activity / pipeline /
closed revenue and never fakes revenue. Writes reports/board_revenue_briefing.{json,md}.
"""
from __future__ import annotations

import json, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial import assets, ip_license, sales_sprint, revenue_briefing   # noqa: E402
from anima.commercial.sales_mastery import core as smc, engagement as sme         # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("COMMERCIAL PHASE 3 — governed sales sprint + board revenue briefing")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "P3Cert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            assets.seed(N, store=st)
            offer_id = "offer_demo"
            sp = sales_sprint.open_sprint(N, goal="first 5 qualified conversations",
                                          offer_id=offer_id, store=st)
            ck("1. a sprint opens with a human-readable goal", sp["goal"] and sp["status"] == "open")

            # an unqualified lead cannot be queued
            lead = smc.add_lead(N, offer_id, source="referral", company="Acme", store=st)["lead"]
            msg = sme.draft_message(N, mtype="cold_intro", buyer_pain="manual audits are slow",
                                    outcome="audited in minutes", proof_point="cert report", store=st)["message"]
            bad = sales_sprint.queue_outreach(N, sp["sprint_id"], lead_id=lead["lead_id"],
                                              message_rec=msg, store=st)
            ck("2. an UNQUALIFIED lead cannot be queued for outreach", not bad["ok"])

            # qualify, then queue
            smc.qualify(N, lead["lead_id"], pain_fit="high", budget_fit="high",
                        authority_fit="high", timing="now", store=st)
            q = sales_sprint.queue_outreach(N, sp["sprint_id"], lead_id=lead["lead_id"],
                                            message_rec=msg, store=st)
            ck("3. a qualified lead's outreach queues (status=queued, not sent)",
               q["ok"] and q["item"]["status"] == "queued")

            # approval queue shows it; nothing is sent
            aq = sales_sprint.approval_queue(N, sp["sprint_id"], store=st)
            ck("4. the approval queue lists the pending item + states the send policy",
               len(aq["pending_approval"]) == 1 and "never sends" in aq["send_policy"].lower())

            item_id = q["item"]["item_id"]
            # can't mark sent before approval
            pre = sales_sprint.mark_sent(N, sp["sprint_id"], item_id, sent_by="lamar", store=st)
            ck("5. an UNAPPROVED item cannot be marked sent", not pre["ok"])

            # approval requires a human approver
            noapprover = sales_sprint.approve_item(N, sp["sprint_id"], item_id, approver="", store=st)
            ck("6. approval requires a named human approver", not noapprover["ok"])
            ap = sales_sprint.approve_item(N, sp["sprint_id"], item_id, approver="lamar", store=st)
            ck("7. a human approval records authorization but does NOT send",
               ap["ok"] and "does not send" in ap["note"].lower())

            sent = sales_sprint.mark_sent(N, sp["sprint_id"], item_id, sent_by="lamar", store=st)
            ck("8. a human can record that THEY sent an approved item",
               sent["ok"] and sent["item"]["status"] == "sent_by_human")

            # board revenue briefing
            br = revenue_briefing.build(N, store=st)
            rt = br["loop"]["revenue_truth"]
            ck("9. the board briefing separates activity / pipeline forecast / closed revenue",
               set(("activity", "pipeline_value_forecast", "closed_revenue")) <= set(rt))
            ck("10. closed revenue is honest (0 with no closed deal) — never faked",
               rt["closed_revenue"] == 0)
            ck("11. the briefing names the highest-leverage next move + the honesty caveat",
               br["highest_leverage_next_move"] and "forecast" in br["honesty"].lower())

            rp = ROOT / "reports"; rp.mkdir(exist_ok=True)
            (rp / "board_revenue_briefing.json").write_text(json.dumps(br, indent=1))
            (rp / "board_revenue_briefing.md").write_text(
                "# Board revenue briefing\n\nNext move: %s\n\n%s\n"
                % (br["highest_leverage_next_move"], br["honesty"]))
            ck("12. the board revenue briefing report is written (evidence)",
               (rp / "board_revenue_briefing.json").exists())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_commercial_phase3", "green" if green else "red",
                files_observed=["anima/commercial/sales_sprint.py",
                                "anima/commercial/revenue_briefing.py", "anima/web/board_revenue.html"],
                report_paths=["reports/board_revenue_briefing.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCOMMERCIAL-PHASE3 CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
