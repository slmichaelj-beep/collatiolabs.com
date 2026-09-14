#!/usr/bin/env python3
"""certify_resource_expansion_planner — monitor / bottleneck / request / host plan, every gate.

Status records carry a recommended action; bottlenecks tie to blocked revenue; a resource request
needs a business case + >=2 priced options (no vague request) and is approval-gated; Vera never
purchases without approval; a host plan can't default to full data access and needs a security policy.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.resources import planner as p, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("RESOURCE + HARDWARE EXPANSION PLANNER — monitor / bottleneck / request / multi-host")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "ResCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            p.record_status(N, host_id="mac1", resource_type="cpu", current_usage="92%", capacity="100%",
                            status="green", store=st)
            red = p.record_status(N, host_id="mac1", resource_type="disk", current_usage="95%", capacity="100%",
                                  status="red", bottleneck_for=["fulfillment of report service"],
                                  business_impact="cannot store deliverables", store=st)["status"]
            ck("1. a red disk resource recommends buying storage", red["recommended_action"] == "buy_storage")
            bn = p.detect_bottlenecks(N, store=st)
            ck("2. the detector flags the bottleneck + ties it to blocked revenue",
               bn["bottlenecks"] and "fulfillment of report service" in bn["blocked_revenue"])

            ck("3. a resource request with no business case is refused",
               not p.resource_request(N, request_type="storage", title="NAS", problem="full disk",
                                      business_case="", options=[{"option_name": "min", "estimated_cost": "$200"}],
                                      recommended_option="min", store=st)["ok"])
            ck("4. a resource request with <2 options is refused",
               not p.resource_request(N, request_type="storage", title="NAS", problem="full disk",
                                      business_case="store deliverables to keep selling reports",
                                      options=[{"option_name": "min", "estimated_cost": "$200"}],
                                      recommended_option="min", store=st)["ok"])
            req = p.resource_request(N, request_type="storage", title="Add 4TB NAS", problem="disk full",
                                     business_case="unblocks report-service fulfillment (~$X/mo)",
                                     options=[{"option_name": "minimum", "estimated_cost": "$200", "expected_unlock": "more deliverables"},
                                              {"option_name": "recommended", "estimated_cost": "$500", "expected_unlock": "redundancy"},
                                              {"option_name": "premium", "estimated_cost": "$1200"}],
                                     recommended_option="recommended", bottleneck_evidence_refs=[red["resource_status_id"]], store=st)["request"]
            ck("5. a complete request is procurement-ready + approval-gated + Vera cannot buy",
               req["status"] == "ready_for_lamar" and req["approval_required"] and not req["vera_can_purchase"])
            ck("6. purchasing without approval is refused",
               not p.purchase(N, req["resource_request_id"], approval_ref="", store=st)["ok"])
            ck("7. purchasing with approval records it as a human action",
               "human action" in p.purchase(N, req["resource_request_id"], approval_ref="lamar", store=st)["note"])

            ck("8. a host plan defaulting to full data access is refused",
               not p.host_plan(N, plan_name="worker1", purpose="worker", data_access_scope="full",
                               security_policy="x", store=st)["ok"])
            ck("9. a host plan without a security policy is refused",
               not p.host_plan(N, plan_name="worker1", purpose="worker", data_access_scope="restricted",
                               security_policy="", store=st)["ok"])
            hp = p.host_plan(N, plan_name="worker1", purpose="worker", data_access_scope="restricted",
                             security_policy="no customer PII; sandbox only", store=st)["host_plan"]
            ck("10. a security-scoped host plan requires trust setup + certs",
               hp["approval_required"] and "trust setup" in hp["setup_steps"] and hp["certs_required"])

            d = api.dashboard(N, store=st)
            ck("11. the dashboard shows bottlenecks + requests + 'Vera never buys' honesty",
               d["ok"] and d["bottlenecks"] and "never purchases" in d["honesty"])
            ck("12. blocked revenue is surfaced on the dashboard", d["blocked_revenue"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_resource_expansion_planner", "green" if green else "red",
                files_observed=["anima/resources/planner.py"],
                report_paths=["reports/resource_expansion_planner.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nRESOURCE-EXPANSION-PLANNER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
