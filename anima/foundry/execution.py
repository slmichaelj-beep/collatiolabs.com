"""foundry.execution — experiments + blueprint + capital allocation + kill/pivot/scale + vendor.

Evidence-driven and governed: a paid experiment cannot run without an approved budget; capital
allocation never scales a venture without traction evidence; every venture must carry kill / pivot
/ scale criteria (a venture with none is a zombie and is flagged); vendor engagement needs approval
before any contact.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import core

EXPERIMENT_STATUS = ("draft", "approved", "running", "complete", "failed", "cancelled")
ALLOCATION = ("fund", "pause", "kill", "pivot", "scale", "research_more")


# ---- experiments ----------------------------------------------------------------------------
def create_experiment(name: str, venture_id: str, hypothesis: str, method: str, *,
                      budget: float = 0.0, success_criteria=None, kill_criteria=None,
                      store: Path | None = None) -> dict:
    if not success_criteria:
        return {"ok": False, "error": "an experiment requires explicit success_criteria"}
    if not kill_criteria:
        return {"ok": False, "error": "an experiment requires explicit kill_criteria"}
    rec = {"experiment_id": "exp_" + uuid.uuid4().hex[:12], "venture_id": venture_id,
           "hypothesis": hypothesis, "method": method, "budget": float(budget),
           "success_criteria": success_criteria, "kill_criteria": kill_criteria,
           "approval_ref": None, "status": "draft", "result": None, "created_at": storage.now()}
    exps = core.read_venture_data(name, venture_id, "experiments", store, default={"experiments": []})
    exps.setdefault("experiments", []).append(rec)
    core.write_venture_data(name, venture_id, "experiments", exps, store)
    return {"ok": True, "experiment": rec}


def run_experiment(name: str, venture_id: str, experiment_id: str, *, approval_ref: str = "",
                   store: Path | None = None) -> dict:
    """A PAID experiment requires an approved budget (via the governance budget ledger) +
    approval. A zero-budget experiment (e.g. an interview from owned contacts) may run at L0."""
    exps = core.read_venture_data(name, venture_id, "experiments", store, default={"experiments": []})
    rec = next((e for e in exps.get("experiments", []) if e["experiment_id"] == experiment_id), None)
    if rec is None:
        return {"ok": False, "error": "no such experiment"}
    if rec["budget"] > 0:
        from anima.company_operator import budget as bl, approvals as aq
        verdict = aq.validate_for_action(
            name, approval_ref, "spend", cost=rec["budget"], category="experiment",
            subject=experiment_id, store=store,
        ) if approval_ref else {"ok": False}
        if not verdict["ok"]:
            return {"ok": False, "error": "a PAID experiment needs an approved approval packet"}
        if not bl.can_spend(name, rec["budget"], category="experiment", store=store)["allowed"]:
            return {"ok": False, "error": "a PAID experiment needs an approved budget covering it"}
    rec["status"] = "running"
    rec["approval_ref"] = approval_ref or None
    core.write_venture_data(name, venture_id, "experiments", exps, store)
    return {"ok": True, "experiment": rec}


def record_result(name: str, venture_id: str, experiment_id: str, *, success: bool,
                  data: dict | None = None, store: Path | None = None) -> dict:
    exps = core.read_venture_data(name, venture_id, "experiments", store, default={"experiments": []})
    rec = next((e for e in exps.get("experiments", []) if e["experiment_id"] == experiment_id), None)
    if rec is None:
        return {"ok": False, "error": "no such experiment"}
    rec["status"] = "complete" if success else "failed"
    rec["result"] = {"success": success, "data": data or {}}
    core.write_venture_data(name, venture_id, "experiments", exps, store)
    # a failed experiment moves the venture into kill/pivot review
    if not success:
        core.update_venture(name, venture_id, {"current_phase": "kill_pivot_review"}, store)
    return {"ok": True, "experiment": rec, "triggers_review": not success}


# ---- kill / pivot / scale -------------------------------------------------------------------
def set_criteria(name: str, venture_id: str, *, kill=None, pivot=None, scale=None,
                 store: Path | None = None) -> dict:
    v = core.update_venture(name, venture_id, {"kill_criteria": kill or [], "pivot_criteria": pivot or [],
                                               "scale_criteria": scale or []}, store)
    return {"ok": v is not None, "venture": v}


def is_zombie(name: str, venture_id: str, store: Path | None = None) -> bool:
    """A venture with no kill criteria (no way to die) is a zombie."""
    v = core.get_venture(name, venture_id, store)
    return bool(v) and not v.get("kill_criteria")


def lifecycle_recommendation(name: str, venture_id: str, *, traction_evidence: bool = False,
                             store: Path | None = None) -> dict:
    v = core.get_venture(name, venture_id, store)
    if v is None:
        return {"ok": False, "error": "no such venture"}
    if not v.get("kill_criteria"):
        return {"ok": True, "recommendation": "set_criteria",
                "reason": "ZOMBIE: this venture has no kill criteria — define them before proceeding"}
    if v.get("current_phase") == "kill_pivot_review":
        return {"ok": True, "recommendation": "kill_or_pivot",
                "reason": "a key experiment failed — recommend kill or a defined pivot"}
    if not traction_evidence:
        return {"ok": True, "recommendation": "no_scale",
                "reason": "no traction evidence — scale is blocked; keep validating"}
    return {"ok": True, "recommendation": "scale", "reason": "traction evidence present — scale candidate"}


# ---- capital allocation ----------------------------------------------------------------------
def allocate(name: str, venture_id: str, *, amount: float, traction_evidence: bool = False,
             store: Path | None = None) -> dict:
    """Recommend + (if funded) reserve capital. No scale-level funding without traction; never
    beyond the unallocated portfolio budget."""
    p = core.portfolio(name, store)
    v = core.get_venture(name, venture_id, store)
    if v is None:
        return {"ok": False, "error": "no such venture"}
    if amount > p["unallocated_budget"]:
        return {"ok": False, "error": "exceeds unallocated portfolio budget ($%.2f)"
                                      % p["unallocated_budget"]}
    # an INITIAL seed (venture not yet funded) is allowed; a funding INCREASE on an
    # already-funded venture needs traction evidence — no scaling capital without proof.
    if v.get("budget", 0) > 0 and not traction_evidence:
        return {"ok": False, "recommendation": "research_more",
                "error": "a funding INCREASE needs traction evidence (no scale without proof)"}
    core.update_venture(name, venture_id, {"budget": v.get("budget", 0) + amount}, store)
    storage.emit_truth(name, "capital", venture_id, "ALLOCATE $%.2f to %s" % (amount, v["name"]),
                       actor="user", store=store)
    return {"ok": True, "recommendation": "fund", "new_budget": v.get("budget", 0) + amount}


# ---- vendor coordinator ----------------------------------------------------------------------
def vendor_sow(name: str, venture_id: str, role: str, scope: str, *, store: Path | None = None) -> dict:
    rec = {"vendor_id": "ven_" + uuid.uuid4().hex[:12], "venture_id": venture_id, "role": role,
           "scope_of_work": scope, "status": "drafted", "contact_requires_approval": True,
           "contract_requires_approval": True, "deliverables": [], "cost": 0.0,
           "created_at": storage.now()}
    vd = core.read_venture_data(name, venture_id, "vendors", store, default={"vendors": []})
    vd.setdefault("vendors", []).append(rec)
    core.write_venture_data(name, venture_id, "vendors", vd, store)
    return {"ok": True, "vendor": rec}


def can_contact_vendor(name: str, vendor_rec: dict, *, approval_ref: str = "",
                       store: Path | None = None) -> dict:
    from anima.company_operator import approvals as aq
    subject = vendor_rec.get("vendor_id", "")
    verdict = aq.validate_for_action(name, approval_ref, "vendor_contact", subject=subject,
                                     store=store) if approval_ref else {"ok": False}
    if not verdict["ok"]:
        return {"allowed": False, "reason": "contacting a vendor requires an approved packet"}
    return {"allowed": True}
