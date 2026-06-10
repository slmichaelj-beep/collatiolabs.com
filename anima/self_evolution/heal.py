"""self_evolution.heal — self-heal policy + repair plans + sandbox + rollback + backup.

Self-healing restores intended function; it never changes doctrine/identity/authority/budget/safety.
Auto-allowed: regenerate report, refresh index, rerun cert, restart service, restore generated state.
Sandbox-required: route/UI/cert/code repair. Approval-required: any core-policy change. Forbidden:
weakening safety, disabling observation/Diamond, erasing audit history, hiding incidents. Every
repair needs a diagnosis + a rollback point; promotion needs validation certs.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import observe as _obs

AUTO_ALLOWED = ("restart_service", "regenerate_report", "refresh_index", "clear_cache",
                "rebuild_non_authoritative_view", "rerun_cert", "restore_generated_state_from_backup")
SANDBOX_REQUIRED = ("repair_route", "repair_ui_component", "repair_observation_wiring",
                    "repair_cert_script", "repair_non_core_module")
APPROVAL_REQUIRED = ("change_core_policy", "change_authority_boundary", "change_budget_boundary",
                     "change_safety_policy", "change_identity_doctrine", "change_truth_schema",
                     "change_diamond_gate", "change_rollback_system")
FORBIDDEN = ("remove_safety_gate", "weaken_authority_policy", "disable_observation", "disable_diamond",
             "erase_audit_history", "hide_incident")


def policy() -> dict:
    return {"auto_allowed": list(AUTO_ALLOWED), "sandbox_required": list(SANDBOX_REQUIRED),
            "approval_required": list(APPROVAL_REQUIRED), "forbidden_without_lamar": list(FORBIDDEN)}


def classify_repair(repair_class: str) -> dict:
    if repair_class in FORBIDDEN:
        return {"class": "forbidden", "allowed": False, "reason": "forbidden without Lamar (and never to weaken safety)"}
    if repair_class in APPROVAL_REQUIRED:
        return {"class": "approval_required", "auto_allowed": False, "approval_required": True}
    if repair_class in SANDBOX_REQUIRED:
        return {"class": "sandbox_required", "auto_allowed": False, "sandbox_required": True}
    if repair_class in AUTO_ALLOWED:
        return {"class": "auto_allowed", "auto_allowed": True}
    return {"class": "unknown", "auto_allowed": False, "reason": "unknown repair class -> deny"}


def repair_plan(name: str, *, diagnosis_id: str, repair_class: str, steps: list,
                rollback_plan: str, validation_certs: list, store: Path | None = None) -> dict:
    """Build a repair plan. Refused without a diagnosis, a rollback plan, and validation certs.
    A forbidden repair class is refused outright."""
    dx = storage.load(name, "self_dx_%s" % diagnosis_id, store, default=None)
    if not dx:
        return {"ok": False, "error": "no repair without a diagnosis"}
    cls = classify_repair(repair_class)
    if cls.get("class") == "forbidden":
        return {"ok": False, "error": cls["reason"]}
    if not (rollback_plan or "").strip():
        return {"ok": False, "error": "no repair without a rollback plan"}
    if not validation_certs:
        return {"ok": False, "error": "no repair promotion without validation certs"}
    rec = {"repair_plan_id": "rp_" + uuid.uuid4().hex[:10], "diagnosis_id": diagnosis_id,
           "repair_class": repair_class, "steps": list(steps),
           "risk_level": dx["risk_level"], "auto_allowed": bool(cls.get("auto_allowed")),
           "sandbox_required": bool(cls.get("sandbox_required")),
           "approval_required": bool(cls.get("approval_required")) or dx["risk_level"] in ("high", "core"),
           "validation_certs": list(validation_certs), "rollback_plan": rollback_plan,
           "status": "draft"}
    storage.save(name, "self_rp_%s" % rec["repair_plan_id"], rec, store)
    return {"ok": True, "repair_plan": rec}


def sandbox(name: str, *, repair_plan_id: str, store: Path | None = None) -> dict:
    """Create an isolated sandbox descriptor — temp stores, no real external integrations, no real
    spend/customer/action effects. (Descriptor only; the executor honors it.)"""
    return {"ok": True, "sandbox": {"sandbox_id": "sb_" + uuid.uuid4().hex[:8], "repair_plan_id": repair_plan_id,
            "isolated": True, "temp_store": True, "external_actions_disabled": True,
            "real_spend_disabled": True, "production_mutation": False}}


def rollback_point(name: str, *, target: str, pre_state_ref: str, store: Path | None = None) -> dict:
    """Create a rollback point before any promotion. Audit history is never erased."""
    rec = {"rollback_id": "rb_" + uuid.uuid4().hex[:10], "target": target, "pre_state_ref": pre_state_ref,
           "created_at": storage.now(), "result": None, "audit_preserved": True}
    storage.save(name, "self_rollback_%s" % rec["rollback_id"], rec, store)
    return {"ok": True, "rollback": rec}


def validate_repair(name: str, *, repair_plan_id: str, cert_results: dict, ui_affected: bool = False,
                    rover_passed: bool | None = None, systemic: bool = False,
                    diamond_passed: bool | None = None, store: Path | None = None) -> dict:
    """Validate a repair before promotion. Any failed cert blocks; UI repair needs Rover; systemic
    repair needs Diamond."""
    failed = [c for c, ok in cert_results.items() if not ok]
    promotion_allowed = not failed
    if ui_affected and not rover_passed:
        promotion_allowed = False; failed.append("rover")
    if systemic and not diamond_passed:
        promotion_allowed = False; failed.append("diamond")
    rec = {"validation_id": "v_" + uuid.uuid4().hex[:8], "repair_plan_id": repair_plan_id,
           "certs_run": list(cert_results), "failed": failed, "passed": not failed and promotion_allowed,
           "promotion_allowed": promotion_allowed, "rollback_required": not promotion_allowed}
    storage.save(name, "self_validation_%s" % repair_plan_id, rec, store)
    return {"ok": True, "validation": rec}


def backup_manifest(name: str, *, store: Path | None = None) -> dict:
    """Record which critical stores are backed up for restore/regeneration."""
    rec = {"backup_id": "bk_" + uuid.uuid4().hex[:10],
           "critical_stores": ["repo", ".anima", "truth_ledger", "observation_store",
                               "decision_ledger", "authority_ledger", "budget_ledger", "action_ledger",
                               "knowledge_pack_registry", "cert_reports", "host_profile", "self_map"],
           "created_at": storage.now(), "restore_tested": False}
    storage.save(name, "self_backup", rec, store)
    return {"ok": True, "backup": rec}
