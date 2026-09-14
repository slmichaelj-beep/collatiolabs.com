"""self_evolution.observe — self-map + health model + diagnostic engine + doctrine monitor.

The self-map enumerates Vera's systems and assigns each a self-modification policy; the
constitutional core is `frozen`. The health model classifies system status with evidence. The
diagnostic engine turns a symptom into a root-cause hypothesis + a fix class + a risk level — and
high-risk / unknown-root-cause diagnoses can never auto-heal. The doctrine monitor flags drift
(fake green, unsupported claims, unapproved spend, etc.) as incidents.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

# the constitutional core — never auto-mutable
FROZEN_SYSTEMS = ("identity_doctrine", "authority_policy", "budget_policy", "safety_policy",
                  "truth_ledger_schema", "observation_contract", "diamond_gate", "rollback_system",
                  "legal_financial_boundaries")
SELF_MODIFY_POLICY = ("auto_repair_allowed", "sandbox_only", "approval_required", "frozen")
HEALTH = ("green", "amber", "red", "unknown")
FIX_CLASSES = ("config", "data", "route", "ui", "cert", "doc", "runtime", "dependency", "code", "human_review")
DOCTRINE_CHECKS = ("no_fake_green", "no_unsupported_memory", "no_unsupported_market_claim",
                   "no_unapproved_spend", "no_unapproved_outreach", "no_hidden_external_action",
                   "no_stale_cert_claim", "no_pipeline_as_revenue", "no_self_mod_without_gate")


def self_map(name: str, *, commit: str = "unknown", store: Path | None = None) -> dict:
    """Generate Vera's self-map. Core systems are marked frozen; product systems sandbox/approval."""
    systems = [
        {"system_id": "truth", "category": "truth", "criticality": "core", "self_modify_policy": "frozen"},
        {"system_id": "observation", "category": "observation", "criticality": "core", "self_modify_policy": "frozen"},
        {"system_id": "authority", "category": "security", "criticality": "core", "self_modify_policy": "frozen"},
        {"system_id": "diamond_gate", "category": "cert", "criticality": "core", "self_modify_policy": "frozen"},
        {"system_id": "rollback", "category": "cert", "criticality": "core", "self_modify_policy": "frozen"},
        {"system_id": "market_vision", "category": "market_vision", "criticality": "high", "self_modify_policy": "sandbox_only"},
        {"system_id": "commercial", "category": "commercial", "criticality": "high", "self_modify_policy": "sandbox_only"},
        {"system_id": "workforce", "category": "workforce", "criticality": "high", "self_modify_policy": "sandbox_only"},
        {"system_id": "collatio", "category": "collatio", "criticality": "high", "self_modify_policy": "approval_required"},
        {"system_id": "teams", "category": "teams", "criticality": "medium", "self_modify_policy": "sandbox_only"},
        {"system_id": "ui", "category": "ui", "criticality": "medium", "self_modify_policy": "sandbox_only"},
        {"system_id": "reports", "category": "cert", "criticality": "low", "self_modify_policy": "auto_repair_allowed"},
    ]
    rec = {"self_map_id": "sm_" + uuid.uuid4().hex[:10], "commit": commit, "systems": systems,
           "frozen_systems": list(FROZEN_SYSTEMS), "generated_at": storage.now(), "truth_refs": []}
    storage.save(name, "self_map", rec, store)
    storage.emit_truth(name, "self_map", rec["self_map_id"], "SELF-MAP generated (%d systems)" % len(systems),
                       actor="vera", store=store)
    return rec


def is_frozen(system_id: str) -> bool:
    sm = {"truth": "truth_ledger_schema", "observation": "observation_contract", "authority": "authority_policy",
          "diamond_gate": "diamond_gate", "rollback": "rollback_system"}
    return system_id in FROZEN_SYSTEMS or sm.get(system_id) in FROZEN_SYSTEMS


def health(name: str, *, system_id: str, status: str, symptoms: list | None = None,
           evidence_refs: list | None = None, store: Path | None = None) -> dict:
    rec = {"health_id": "h_" + uuid.uuid4().hex[:8], "system_id": system_id,
           "status": status if status in HEALTH else "unknown",
           "severity": {"green": "info", "amber": "warning", "red": "blocking", "unknown": "warning"}.get(status, "warning"),
           "observed_symptoms": list(symptoms or []), "evidence_refs": list(evidence_refs or []),
           "self_heal_eligible": status == "amber" and not is_frozen(system_id)}
    storage.save(name, "self_health_%s" % system_id, rec, store)
    return rec


def diagnose(name: str, *, symptom: str, affected_systems: list, fix_class: str,
             root_cause: str = "", risk_level: str = "low", store: Path | None = None) -> dict:
    """Diagnose a fault. Unknown root cause or a frozen/core/high-risk target can never auto-heal."""
    frozen_hit = any(is_frozen(s) for s in affected_systems)
    confidence = "low" if not root_cause else "medium"
    self_heal = (fix_class in ("config", "data", "cert", "runtime") and risk_level == "low"
                 and bool(root_cause) and not frozen_hit)
    rec = {"diagnosis_id": "dx_" + uuid.uuid4().hex[:10], "symptom": symptom,
           "affected_systems": list(affected_systems),
           "root_cause_hypotheses": [root_cause] if root_cause else [],
           "confidence": confidence,
           "recommended_fix_class": fix_class if fix_class in FIX_CLASSES else "human_review",
           "risk_level": "core" if frozen_hit else risk_level,
           "self_heal_allowed": self_heal,
           "sandbox_required": fix_class in ("route", "ui", "cert", "code") and not self_heal,
           "approval_required": frozen_hit or risk_level in ("high", "core"),
           "rollback_required": True, "evidence_refs": []}
    storage.save(name, "self_dx_%s" % rec["diagnosis_id"], rec, store)
    storage.emit_truth(name, "self_dx", rec["diagnosis_id"], "DIAGNOSIS: %s (%s)" % (symptom, rec["risk_level"]),
                       actor="vera", store=store)
    return rec


def doctrine_scan(name: str, *, violations: list | None = None, store: Path | None = None) -> dict:
    """Record doctrine-drift incidents. Each named violation becomes a tracked incident."""
    violations = violations or []
    incidents = [{"check": v, "severity": "high" if v in ("no_fake_green", "no_unapproved_spend",
                                                           "no_self_mod_without_gate") else "medium"}
                 for v in violations if v in DOCTRINE_CHECKS]
    rec = {"doctrine_scan_id": "ds_" + uuid.uuid4().hex[:10], "incidents": incidents,
           "clean": not incidents, "checks_run": list(DOCTRINE_CHECKS)}
    storage.save(name, "self_doctrine", rec, store)
    if incidents:
        storage.emit_truth(name, "self_doctrine", rec["doctrine_scan_id"],
                           "DOCTRINE incidents: %d" % len(incidents), actor="vera", risk="high", store=store)
    return rec
