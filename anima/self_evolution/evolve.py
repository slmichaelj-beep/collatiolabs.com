"""self_evolution.evolve — capability genesis + promotion gate + retirement + continuity + autonomy.

Self-evolution grows new organs from EVIDENCE of recurring need (a one-off request never auto-
promotes). A proposal needs a gap, benefit/risk, a cert plan, an observation plan, and a rollback
plan. The promotion gate blocks without gap evidence, rollback, passing certs, Diamond (if released),
and approval (if high-risk/core). Retirement requires impact analysis (active dependency blocks it).
Continuity provides a survival manifest, restore drill, and time capsule. Autonomy levels A0–A10
keep the constitutional core protected (A10 ≠ "do anything").
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import observe as _obs

AUTONOMY_LEVELS = {
    "A0": "observe only", "A1": "diagnose", "A2": "recommend repair",
    "A3": "auto-heal low-risk generated state", "A4": "sandbox-build repairs/extensions",
    "A5": "promote low-risk repairs after certs", "A6": "propose high-risk evolution for approval",
    "A7": "long-horizon continuity drills", "A8": "budgeted autonomous maintenance",
    "A9": "autonomous business operation within strict policy",
    "A10": "core self-modification FORBIDDEN without Lamar (constitutional protection)",
}


def capability_gap(name: str, *, title: str, description: str, evidence_refs: list, frequency: int,
                   business_impact: str = "medium", store: Path | None = None) -> dict:
    """Detect a capability gap from REPEATED evidence. A one-off (frequency < 2) cannot auto-promote
    to a new module."""
    auto_promotable = frequency >= 2 and len(evidence_refs) >= 2
    rec = {"gap_id": "cg_" + uuid.uuid4().hex[:10], "title": title, "description": description,
           "evidence_refs": list(evidence_refs), "frequency": frequency,
           "business_impact": business_impact,
           "recommended_response": ("new_module" if auto_promotable else "document"),
           "can_become_module": auto_promotable,
           "confidence": "medium" if auto_promotable else "low"}
    storage.save(name, "self_capgap_%s" % rec["gap_id"], rec, store)
    return {"ok": True, "capability_gap": rec}


def proposal(name: str, *, gap_id: str, proposed_capability: str, risk_level: str,
             new_certs: list, observation_events: list, rollback_plan: str,
             store: Path | None = None) -> dict:
    """A structural-evolution proposal. Refused without gap evidence, a cert plan, an observation
    plan, and a rollback plan."""
    gap = storage.load(name, "self_capgap_%s" % gap_id, store, default=None)
    if not gap:
        return {"ok": False, "error": "no proposal without a capability gap"}
    if not gap.get("can_become_module"):
        return {"ok": False, "error": "gap lacks repeated evidence — cannot propose a module yet"}
    if not new_certs:
        return {"ok": False, "error": "no proposal without a cert plan"}
    if not observation_events:
        return {"ok": False, "error": "no proposal without an observation plan"}
    if not (rollback_plan or "").strip():
        return {"ok": False, "error": "no proposal without a rollback plan"}
    rec = {"proposal_id": "pr_" + uuid.uuid4().hex[:10], "gap_id": gap_id,
           "proposed_capability": proposed_capability, "risk_level": risk_level,
           "new_certs": list(new_certs), "observation_events": list(observation_events),
           "rollback_plan": rollback_plan, "approval_required": risk_level in ("high", "core"),
           "status": "ready_for_review"}
    storage.save(name, "self_proposal_%s" % rec["proposal_id"], rec, store)
    storage.emit_truth(name, "self_proposal", rec["proposal_id"], "EVOLUTION proposal: " + proposed_capability,
                       actor="vera", store=store)
    return {"ok": True, "proposal": rec}


def promote(name: str, *, proposal_id: str, cert_results: dict, rollback_ref: str = "",
            diamond_passed: bool = False, released: bool = True, approval_ref: str = "",
            store: Path | None = None) -> dict:
    """The promotion gate. Blocks without gap evidence, a rollback ref, passing certs, Diamond (if
    released), and approval (if high-risk/core)."""
    prop = storage.load(name, "self_proposal_%s" % proposal_id, store, default=None)
    if not prop:
        return {"ok": False, "error": "no such proposal"}
    if not (rollback_ref or "").strip():
        return {"ok": False, "error": "promotion blocked: no rollback point"}
    failed = [c for c, ok in cert_results.items() if not ok]
    if failed:
        return {"ok": False, "error": "promotion blocked: failing certs %s" % failed}
    if released and not diamond_passed:
        return {"ok": False, "error": "promotion blocked: Diamond not green for a released change"}
    if prop["approval_required"] and not (approval_ref or "").strip():
        return {"ok": False, "error": "promotion blocked: high-risk/core change needs approval"}
    rec = {"promotion_id": "promo_" + uuid.uuid4().hex[:10], "proposal_id": proposal_id,
           "risk_level": prop["risk_level"], "approval_ref": approval_ref or None,
           "rollback_ref": rollback_ref, "cert_results": cert_results, "diamond_passed": diamond_passed,
           "status": "promoted"}
    storage.save(name, "self_promotion_%s" % rec["promotion_id"], rec, store)
    storage.emit_truth(name, "self_promotion", rec["promotion_id"], "PROMOTED: " + proposal_id,
                       actor="user", store=store)
    return {"ok": True, "promotion": rec}


def retire(name: str, *, capability: str, reason: str, active_dependencies: list | None = None,
           impact_analysis: str = "", store: Path | None = None) -> dict:
    """Retire a capability. Refused if it has active dependencies or no impact analysis."""
    if active_dependencies:
        return {"ok": False, "error": "active dependencies block retirement: %s" % active_dependencies}
    if not (impact_analysis or "").strip():
        return {"ok": False, "error": "retirement requires an impact analysis"}
    rec = {"retirement_id": "ret_" + uuid.uuid4().hex[:10], "capability": capability, "reason": reason,
           "impact_analysis": impact_analysis, "deprecation_notice": "issued",
           "rollback_plan": "restore from backup", "status": "deprecated"}
    storage.save(name, "self_retire_%s" % rec["retirement_id"], rec, store)
    return {"ok": True, "retirement": rec}


# ---- continuity ----
def survival_manifest(name: str, *, commit: str = "unknown", store: Path | None = None) -> dict:
    rec = {"survival_manifest_id": "surv_" + uuid.uuid4().hex[:10], "commit": commit,
           "created_at": storage.now(),
           "critical_ledgers": ["truth_ledger", "observation_store", "decision_ledger",
                                "authority_ledger", "budget_ledger", "action_ledger"],
           "rebuild_steps": ["clone repo", "restore .anima", "regenerate indexes", "start server"],
           "restore_steps": ["restore stores into temp", "verify ledgers readable", "run deploy_check"],
           "verification_steps": ["deploy_check", "master cert stack", "Diamond"],
           "human_recovery_instructions": ["see time capsule"], "machine_recovery_instructions": ["see manifest"],
           "integrity_hashes": {"note": "computed at backup time"}}
    storage.save(name, "self_survival", rec, store)
    return {"ok": True, "survival_manifest": rec}


def restore_drill(name: str, *, server_started: bool, ledgers_readable: bool, deploy_check_passed: bool,
                  store: Path | None = None) -> dict:
    """Record a restore drill outcome. A drill only 'passes' if the server starts, ledgers are
    readable, and deploy_check passes."""
    passed = server_started and ledgers_readable and deploy_check_passed
    rec = {"drill_id": "drill_" + uuid.uuid4().hex[:10], "server_started": server_started,
           "ledgers_readable": ledgers_readable, "deploy_check_passed": deploy_check_passed,
           "passed": passed, "at": storage.now()}
    storage.save(name, "self_drill", rec, store)
    return {"ok": True, "drill": rec}


def time_capsule(name: str, *, store: Path | None = None) -> dict:
    rec = {"time_capsule_id": "tc_" + uuid.uuid4().hex[:10],
           "what_vera_is": "Lamar's private local-first AI operating system",
           "core_doctrine": "no fake green; truth-ledgered; governed authority; human-only legal/financial",
           "frozen_systems": list(_obs.FROZEN_SYSTEMS),
           "how_to_restore": "follow survival_manifest restore_steps + verification_steps",
           "how_not_to_break_her": "never auto-mutate frozen systems; never disable observation/Diamond",
           "human_readable": True, "machine_readable": True}
    storage.save(name, "self_timecapsule", rec, store)
    return {"ok": True, "time_capsule": rec}


def autonomy_policy() -> dict:
    return {"levels": AUTONOMY_LEVELS,
            "core_protection": "A10 forbids core self-modification without Lamar — not 'do anything'"}
