#!/usr/bin/env python3
"""certify_self_evolution — observe → heal → evolve → continuity, every gate, frozen core enforced.

Self-map marks the constitutional core frozen; a frozen system never auto-heals. Diagnosis: unknown
root cause / high-risk / frozen target cannot auto-heal. Repair: needs diagnosis + rollback + certs;
forbidden classes refused; safety-weakening refused. Promotion: blocked without rollback / passing
certs / Diamond / approval. Retirement: active-dependency blocks. Continuity: survival manifest +
restore drill + time capsule. Autonomy A10 protects the core.
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.self_evolution import observe as obs, heal, evolve as ev, api  # noqa: E402

oks, fails = [], []
def ck(l, x): (oks if x else fails).append(l); print(("  ok   " if x else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("AUTONOMOUS SELF-EVOLUTION — self-map / diagnosis / heal / evolve / continuity (frozen core)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "SelfCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            sm = obs.self_map(N, commit="abc123", store=st)
            ck("1. the self-map marks the constitutional core frozen",
               "authority_policy" in sm["frozen_systems"] and "diamond_gate" in sm["frozen_systems"])
            ck("2. a frozen system is recognized as frozen", obs.is_frozen("authority"))
            ck("3. a product system is NOT frozen", not obs.is_frozen("market_vision"))

            h = obs.health(N, system_id="reports", status="amber", symptoms=["stale report"], store=st)
            ck("4. an amber non-frozen system is self-heal eligible", h["self_heal_eligible"])
            hf = obs.health(N, system_id="authority", status="amber", store=st)
            ck("5. a frozen system is NEVER self-heal eligible", not hf["self_heal_eligible"])

            dunk = obs.diagnose(N, symptom="weird", affected_systems=["market_vision"], fix_class="code", store=st)
            ck("6. an unknown-root-cause diagnosis cannot auto-heal", not dunk["self_heal_allowed"])
            dcore = obs.diagnose(N, symptom="authority drift", affected_systems=["authority"],
                                 fix_class="config", root_cause="bad toggle", store=st)
            ck("7. a frozen-target diagnosis is core-risk + approval-required + no auto-heal",
               dcore["risk_level"] == "core" and dcore["approval_required"] and not dcore["self_heal_allowed"])
            dlow = obs.diagnose(N, symptom="stale report", affected_systems=["reports"], fix_class="cert",
                                root_cause="cache miss", risk_level="low", store=st)
            ck("8. a low-risk, known-cause, non-frozen fault can auto-heal", dlow["self_heal_allowed"])

            ds = obs.doctrine_scan(N, violations=["no_fake_green"], store=st)
            ck("9. a doctrine violation becomes a high-severity incident",
               ds["incidents"] and ds["incidents"][0]["severity"] == "high")

            ck("10. self-heal policy forbids weakening safety",
               not heal.classify_repair("remove_safety_gate").get("auto_allowed", False)
               and heal.classify_repair("remove_safety_gate")["class"] == "forbidden")
            ck("11. a code repair is sandbox-required (not auto)",
               heal.classify_repair("repair_non_core_module")["class"] == "sandbox_required")
            ck("12. a core-policy change is approval-required",
               heal.classify_repair("change_core_policy")["class"] == "approval_required")

            ck("13. a repair plan without a rollback plan is refused",
               not heal.repair_plan(N, diagnosis_id=dlow["diagnosis_id"], repair_class="regenerate_report",
                                    steps=["regen"], rollback_plan="", validation_certs=["c"], store=st)["ok"])
            ck("14. a forbidden repair class is refused",
               not heal.repair_plan(N, diagnosis_id=dlow["diagnosis_id"], repair_class="disable_diamond",
                                    steps=["x"], rollback_plan="rb", validation_certs=["c"], store=st)["ok"])
            rp = heal.repair_plan(N, diagnosis_id=dlow["diagnosis_id"], repair_class="regenerate_report",
                                  steps=["regen report"], rollback_plan="restore prior report",
                                  validation_certs=["certify_cert_freshness"], store=st)["repair_plan"]
            ck("15. a valid auto-allowed repair plan is built", rp["auto_allowed"])
            ck("16. the sandbox descriptor disables external actions + production mutation",
               heal.sandbox(N, repair_plan_id=rp["repair_plan_id"], store=st)["sandbox"]["external_actions_disabled"]
               and not heal.sandbox(N, repair_plan_id=rp["repair_plan_id"], store=st)["sandbox"]["production_mutation"])
            ck("17. a failed validation blocks promotion + requires rollback",
               not heal.validate_repair(N, repair_plan_id=rp["repair_plan_id"],
                                        cert_results={"certify_cert_freshness": False}, store=st)["validation"]["promotion_allowed"])
            ck("18. a UI repair without Rover cannot promote",
               not heal.validate_repair(N, repair_plan_id=rp["repair_plan_id"],
                                        cert_results={"c": True}, ui_affected=True, rover_passed=False, store=st)["validation"]["promotion_allowed"])
            ck("19. a rollback point preserves the audit history",
               heal.rollback_point(N, target="reports", pre_state_ref="snap1", store=st)["rollback"]["audit_preserved"])

            one = ev.capability_gap(N, title="x", description="d", evidence_refs=["e1"], frequency=1, store=st)
            ck("20. a one-off capability gap cannot become a module", not one["capability_gap"]["can_become_module"])
            rep = ev.capability_gap(N, title="recurring export pain", description="users keep asking",
                                    evidence_refs=["e1", "e2", "e3"], frequency=4, store=st)["capability_gap"]
            ck("21. a repeated capability gap can become a module", rep["can_become_module"])

            noev = ev.proposal(N, gap_id=rep["gap_id"], proposed_capability="exporter", risk_level="medium",
                               new_certs=[], observation_events=["x"], rollback_plan="rb", store=st)
            ck("22. a proposal without a cert plan is refused", not noev["ok"])
            prop = ev.proposal(N, gap_id=rep["gap_id"], proposed_capability="exporter", risk_level="medium",
                               new_certs=["certify_exporter"], observation_events=["export_run"],
                               rollback_plan="remove module + restore", store=st)["proposal"]
            ck("23. a complete proposal is ready for review", prop["status"] == "ready_for_review")

            ck("24. promotion is blocked without a rollback ref",
               not ev.promote(N, proposal_id=prop["proposal_id"], cert_results={"certify_exporter": True},
                              rollback_ref="", diamond_passed=True, store=st)["ok"])
            ck("25. promotion is blocked with a failing cert",
               not ev.promote(N, proposal_id=prop["proposal_id"], cert_results={"certify_exporter": False},
                              rollback_ref="rb1", diamond_passed=True, store=st)["ok"])
            ck("26. promotion is blocked without Diamond for a released change",
               not ev.promote(N, proposal_id=prop["proposal_id"], cert_results={"certify_exporter": True},
                              rollback_ref="rb1", diamond_passed=False, released=True, store=st)["ok"])
            ok = ev.promote(N, proposal_id=prop["proposal_id"], cert_results={"certify_exporter": True},
                            rollback_ref="rb1", diamond_passed=True, released=True, store=st)
            ck("27. a fully-gated promotion succeeds", ok["ok"])

            ck("28. retirement with an active dependency is blocked",
               not ev.retire(N, capability="exporter", reason="unused", active_dependencies=["dashboard"],
                             impact_analysis="x", store=st)["ok"])
            ck("29. retirement without impact analysis is refused",
               not ev.retire(N, capability="old_thing", reason="unused", impact_analysis="", store=st)["ok"])

            ck("30. a survival manifest lists critical ledgers + restore + verification steps",
               ev.survival_manifest(N, commit="abc", store=st)["survival_manifest"]["verification_steps"])
            ck("31. a restore drill only passes if server starts + ledgers readable + deploy_check passes",
               ev.restore_drill(N, server_started=True, ledgers_readable=True, deploy_check_passed=True, store=st)["drill"]["passed"]
               and not ev.restore_drill(N, server_started=True, ledgers_readable=False, deploy_check_passed=True, store=st)["drill"]["passed"])
            ck("32. the time capsule lists the frozen systems + how-not-to-break", ev.time_capsule(N, store=st)["time_capsule"]["frozen_systems"])
            ck("33. autonomy A10 forbids core self-modification without Lamar", "FORBIDDEN" in ev.AUTONOMY_LEVELS["A10"])

            d = api.dashboard(N, store=st)
            ck("34. the dashboard shows frozen systems + governed self-mod honesty",
               d["ok"] and d["frozen_systems"] and "frozen" in d["honesty"].lower())
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_self_evolution", "green" if green else "red",
                files_observed=["anima/self_evolution/observe.py", "anima/self_evolution/heal.py",
                                "anima/self_evolution/evolve.py"],
                report_paths=["reports/autonomous_self_evolution_final_diamond.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as ex:
        print("  (emit failed: %r)" % ex)
    print("\nSELF-EVOLUTION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
