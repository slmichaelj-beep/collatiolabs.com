#!/usr/bin/env python3
"""run_master_cert_stack — run every current cert in the operator product, in dependency order,
and report a single pass/fail. This is the canonical "is the whole thing green?" command.

  python3 scripts/run_master_cert_stack.py            # run all, human summary
  python3 scripts/run_master_cert_stack.py --json      # machine-readable

Exit 0 iff every cert is CERTIFIED/GREEN.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STACK = [
    # foundation + verification spine
    ("deploy_check", []),
    ("certify_cert_result_spine", []),
    ("certify_claim_registry", []),
    ("certify_release_tier_blockers", []),
    ("certify_deferred_capabilities", []),
    ("certify_verification_dashboard", []),
    ("certify_cert_freshness", []),
    ("certify_cert_flake_classification", []),
    ("certify_no_stubs", ["--gate"]),
    ("certify_product_polish", []),
    # truth + learning
    ("certify_truth_ledger", []),
    ("certify_memory_truth_and_correction", []),
    ("certify_memory_forget_retraction", []),
    ("certify_memory_conflict_policy", []),
    ("certify_learning_integrity_dashboard", []),
    ("certify_teaching_mode", []),
    ("certify_knowledge_packs", []),
    ("certify_auto_learn_queue", []),
    ("certify_rollback_semantics", []),
    # host
    ("certify_host_runtime_contract", []),
    ("certify_host_adaptive_expansion", []),
    # company operating layer
    ("certify_company_canon", []),
    ("certify_decision_ledger", []),
    ("certify_product_doctrine_registry", []),
    ("certify_company_state_trackers", []),
    ("certify_founder_ops", []),
    # company operator
    ("certify_company_operator_governance", []),
    ("certify_company_operator_planning", []),
    ("certify_company_operator_accounts_legal", []),
    # venture foundry
    ("certify_foundry_core", []),
    ("certify_foundry_evaluation", []),
    ("certify_foundry_execution", []),
    ("certify_foundry_safety", []),
    ("certify_chairman_dashboard", []),
    # sales
    ("certify_sales_core", []),
    ("certify_sales_engagement", []),
    ("certify_sales_pipeline_revenue", []),
    # knowledge packs (business/sales)
    ("certify_business_sales_knowledge_packs", []),
    ("certify_business_sales_pack_registry", []),
    # product + first launch
    ("certify_first_launch_wizard", []),
    ("certify_polish_paths", []),
    # operator observation closure
    ("certify_operator_navigation", []),
    ("certify_new_surfaces_rover", []),
    ("certify_new_operator_surfaces_rover", []),
    ("certify_operator_observation_integration", []),
    ("certify_operator_evidence_chain", []),
    ("certify_operator_governance_visibility", []),
    # directive-named surface certs (§13 run order)
    ("certify_founder_command_center", []),
    ("certify_sales_pipeline_command_center", []),
    ("certify_foundry_product_polish", []),
    ("certify_commercial_safety_policy", []),
    # commercialization revenue surface (real /commercial + /sales)
    ("certify_software_commercialization", []),
    # commercialization deepening — the 3-phase operator
    ("certify_commercial_phase1", []),
    ("certify_commercial_phase2", []),
    ("certify_commercial_phase3", []),
    # market vision engine — opportunity intelligence
    ("certify_market_vision_engine", []),
    ("certify_market_vision_safety", []),
    # collatio operating authority + team builder
    ("certify_collatio_authority_layer", []),
    ("certify_team_builder_layer", []),
    # digital workforce foundry
    ("certify_workforce_foundry", []),
    # autonomous self-evolution + self-healing
    ("certify_self_evolution", []),
    # revenue generation — strike / swarm / compounding
    ("certify_revenue_strike_engine", []),
    ("certify_revenue_swarm_factory", []),
    ("certify_compounding_engine", []),
    # revenue infrastructure — intelligence / distribution / trust / resources / empire
    ("certify_revenue_intelligence_layer", []),
    ("certify_distribution_engine", []),
    ("certify_trust_moat", []),
    ("certify_resource_expansion_planner", []),
    ("certify_empire_allocator", []),
    # financial milestone — $16k net profit strike machine
    ("certify_revenue_milestone", []),
    # revenue operations setup — accounts / payment rails / launch readiness
    ("certify_revenue_ops_setup", []),
    # fiverr marketplace channel — governed
    ("certify_fiverr_policy_gate", []),
    ("certify_fiverr_channel_engine", []),
]

_GREEN = ("CERTIFIED", "GREEN ✓", "NO-STUB AUDIT: CERTIFIED")


def _run(name: str, extra: list) -> tuple[bool, str]:
    script = ROOT / "scripts" / ("%s.py" % name if not name.endswith(".py") else name)
    if not script.exists():
        return False, "MISSING SCRIPT"
    try:
        out = subprocess.run([sys.executable, str(script), *extra], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=900).stdout
    except Exception as e:
        return False, "ERROR %r" % e
    tail = [ln for ln in out.splitlines() if any(k in ln for k in
            ("CERT:", "GREEN ✓", "NO-STUB AUDIT:", "FAIL"))]
    last = tail[-1] if tail else "(no verdict line)"
    return any(k in last for k in _GREEN) and "FAIL" not in last, last.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    results, passed = [], 0
    for name, extra in STACK:
        ok, line = _run(name, extra)
        results.append({"cert": name, "ok": ok, "line": line})
        passed += 1 if ok else 0
        if not args.json:
            print("%-46s %s" % (name, "✓" if ok else "✗  " + line))
    green = passed == len(STACK)
    if args.json:
        print(json.dumps({"passed": passed, "total": len(STACK), "green": green,
                          "results": results}, indent=1))
    else:
        print("=" * 70)
        print("MASTER CERT STACK: %d/%d %s  (%.0fs)"
              % (passed, len(STACK), "GREEN" if green else "RED", time.perf_counter() - t0))
        if not green:
            print("FAILED: " + ", ".join(r["cert"] for r in results if not r["ok"]))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
