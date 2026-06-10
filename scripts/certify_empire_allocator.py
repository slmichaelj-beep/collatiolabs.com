#!/usr/bin/env python3
"""certify_empire_allocator — host registry / routing / scheduler / capital / workforce, every gate.

Sensitive task needs a certified host; private data on cloud needs approval; professional review
routes to the human queue. Scheduler: paid work outranks research; security/legal/self-heal override
revenue; low-value deferred under load. Capital: no spend without approval; winners need evidence;
hardware needs a business case; reserve protected. Workforce: overloaded team blocks work.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.empire import registry as r, allocator as al, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("MULTI-HOST EMPIRE + CAPITAL ALLOCATOR — hosts / routing / scheduler / capital / workforce")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "EmpCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            primary = r.register_host(N, host_name="MacStudio", role="primary", security_status="certified",
                                      data_access_scope="restricted", store=st)["host"]
            worker = r.register_host(N, host_name="worker1", role="worker", store=st)["host"]
            cloud = r.register_host(N, host_name="cloudburst", role="cloud", store=st)["host"]
            hq = r.register_host(N, host_name="human-queue", role="human_queue", security_status="certified", store=st)["host"]
            ck("1. a host registers (uncertified => planned)", worker["status"] == "planned")

            ck("2. a sensitive task to an uncertified host is refused",
               not r.route_task(N, task_kind="memory_work", sensitivity="private", host_id=worker["host_id"], store=st)["allowed"])
            ck("3. a sensitive task to a certified host is routed",
               r.route_task(N, task_kind="memory_work", sensitivity="private", host_id=primary["host_id"], store=st)["allowed"])
            r.certify_host(N, cloud["host_id"], cert_ref="sec_cert_1", store=st)
            ck("4. private data on a cloud host without approval is refused",
               not r.route_task(N, task_kind="analysis", sensitivity="private", host_id=cloud["host_id"], store=st)["allowed"])
            ck("5. private data on a cloud host WITH approval is routed",
               r.route_task(N, task_kind="analysis", sensitivity="private", host_id=cloud["host_id"],
                            cloud_approval_ref="lamar", store=st)["allowed"])
            ck("6. professional review must route to the human queue",
               not r.route_task(N, task_kind="professional_review", sensitivity="restricted",
                                host_id=primary["host_id"], store=st)["allowed"])
            ck("7. professional review routes fine to the human queue",
               r.route_task(N, task_kind="professional_review", sensitivity="restricted", host_id=hq["host_id"], store=st)["allowed"])

            # scheduler
            tasks = [{"id": "t1", "kind": "opportunity_research"}, {"id": "t2", "kind": "paid_customer_delivery"},
                     {"id": "t3", "kind": "security_incident"}, {"id": "t4", "kind": "low_value_maintenance"}]
            sc = al.schedule(N, tasks=tasks, store=st)["schedule"]
            ck("8. security incident is scheduled first (outranks revenue)", sc["top"] == "security_incident")
            ck("9. paid customer delivery outranks opportunity research",
               sc["ordered_kinds"].index("paid_customer_delivery") < sc["ordered_kinds"].index("opportunity_research"))
            scl = al.schedule(N, tasks=tasks, under_load=True, store=st)["schedule"]
            ck("10. under load, low-value work is deferred", "t4" in scl["deferred"])

            # capital
            ck("11. capital allocation without approval is refused",
               not al.allocate_capital(N, period="2026-06", available_budget=10000, target="sales_experiments",
                                       amount=1000, evidence_present=True, approval_ref="", store=st)["ok"])
            ck("12. funding automation without evidence is refused",
               not al.allocate_capital(N, period="2026-06", available_budget=10000, target="automation",
                                       amount=1000, evidence_present=False, approval_ref="lamar", store=st)["ok"])
            ck("13. hardware spend without a business case is refused",
               not al.allocate_capital(N, period="2026-06", available_budget=10000, target="hardware",
                                       amount=1000, evidence_present=True, approval_ref="lamar", store=st)["ok"])
            ck("14. an allocation breaching the reserve is refused",
               not al.allocate_capital(N, period="2026-06", available_budget=1000, target="sales_experiments",
                                       amount=900, evidence_present=True, approval_ref="lamar", reserve_pct=0.2, store=st)["ok"])
            ck("15. an evidence-backed, approved, reserve-safe allocation is recorded",
               al.allocate_capital(N, period="2026-06", available_budget=10000, target="sales_experiments",
                                   amount=1000, evidence_present=True, approval_ref="lamar", store=st)["ok"])

            ck("16. an overloaded team blocks workforce assignment",
               not al.allocate_workforce(N, workstream_id="w1", assignee="agent", host_id=primary["host_id"],
                                         team_capacity_ok=False, store=st)["ok"])
            ck("17. a capacity-OK workforce assignment is recorded",
               al.allocate_workforce(N, workstream_id="w1", assignee="agent", host_id=primary["host_id"],
                                     team_capacity_ok=True, store=st)["ok"])

            d = api.dashboard(N, store=st)
            ck("18. the dashboard shows hosts + capital + honest scaling/security rules",
               d["ok"] and d["certified_hosts"] >= 2 and "uncertified host" in d["honesty"])
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_empire_allocator", "green" if green else "red",
                files_observed=["anima/empire/registry.py", "anima/empire/allocator.py"],
                report_paths=["reports/multi_host_empire_allocator.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nEMPIRE-ALLOCATOR CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
