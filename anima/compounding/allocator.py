"""compounding.allocator — revenue allocator + moat builder + automation/productization allocators.

The revenue allocator recommends kill/hold/fix/automate/productize/scale/hire/partner/spin_out per
workstream — a bad-quality stream can never be told to scale; every budgeted recommendation needs
approval. The moat builder respects privacy/legal boundaries (no unlawful data moat). Automation
needs repeated-workflow evidence + a margin thesis. Productization needs proof + build approval.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

ACTIONS = ("kill", "hold", "fix", "automate", "productize", "scale", "hire", "partner", "spin_out")
MOATS = ("software_automation", "lawful_workflow_data", "brand_reputation", "delivery_quality",
         "speed", "privacy_trust", "certification_framework", "customer_relationships",
         "distribution_channels", "vertical_specialization", "knowledge_packs", "team_capability",
         "operating_playbooks")


def allocate(name: str, *, workstream_id: str, cash_collected: float, gross_margin: float,
             quality_score: float, capacity_ok: bool, repeat_purchase: bool = False,
             requested_action: str = "hold", budget: float = 0.0, approval_ref: str = "",
             store: Path | None = None) -> dict:
    """Recommend a capital/effort action. A bad-quality stream cannot scale; a budgeted action
    requires approval; scale needs margin + quality + capacity."""
    if requested_action not in ACTIONS:
        return {"ok": False, "error": "unknown action %r" % requested_action}
    action = requested_action
    reason = ""
    if quality_score < 0.7 and action in ("scale", "hire"):
        action, reason = "fix", "quality too low to scale — fix first"
    elif action == "scale" and not (gross_margin > 0 and capacity_ok):
        action, reason = "hold", "scale needs positive margin + capacity"
    elif cash_collected <= 0 and action in ("scale", "hire", "partner"):
        action, reason = "hold", "no collected cash yet — earn proof before investing"
    else:
        reason = "evidence supports %s" % action
    if budget > 0 and not (approval_ref or "").strip():
        return {"ok": False, "error": "a budgeted allocation requires approval"}
    rec = {"allocation_id": "calloc_" + uuid.uuid4().hex[:10], "workstream_id": workstream_id,
           "action": action, "requested_action": requested_action, "budget": budget,
           "reason": reason, "approval_ref": approval_ref or None,
           "evidence": {"cash": cash_collected, "gross_margin": gross_margin,
                        "quality": quality_score, "capacity_ok": capacity_ok,
                        "repeat_purchase": repeat_purchase}}
    storage.save(name, "comp_alloc_%s" % workstream_id, rec, store)
    _idx(name, workstream_id, store)
    storage.emit_truth(name, "comp_alloc", rec["allocation_id"], "ALLOCATE %s -> %s" % (workstream_id, action),
                       actor="user", store=store)
    return {"ok": True, "allocation": rec}


def moat(name: str, *, workstream_id: str, moat_type: str, lawful_data: bool = True,
         store: Path | None = None) -> dict:
    """Propose a durability moat. An unlawful data moat is refused outright."""
    if moat_type not in MOATS:
        return {"ok": False, "error": "unknown moat type %r" % moat_type}
    if moat_type == "lawful_workflow_data" and not lawful_data:
        return {"ok": False, "error": "no unlawful data moat — refused"}
    rec = {"moat_id": "moat_" + uuid.uuid4().hex[:8], "workstream_id": workstream_id, "moat_type": moat_type,
           "respects_privacy_legal": True, "includes_quality_reputation": True}
    storage.save(name, "comp_moat_%s" % rec["moat_id"], rec, store)
    return {"ok": True, "moat": rec}


def automation(name: str, *, workstream_id: str, repeated_workflow: bool, qa_pass_rate: float,
               build_cost_estimate: float, margin_improvement_estimate: float, store: Path | None = None) -> dict:
    """Recommend automating a service. Blocked without repeated-workflow proof; needs a margin thesis."""
    if not repeated_workflow:
        return {"ok": False, "error": "automation blocked without repeated-workflow proof"}
    if margin_improvement_estimate <= 0:
        return {"ok": False, "error": "automation needs a positive margin thesis"}
    rec = {"automation_id": "auto_" + uuid.uuid4().hex[:8], "workstream_id": workstream_id,
           "qa_pass_rate": qa_pass_rate, "build_cost_estimate": build_cost_estimate,
           "margin_improvement_estimate": margin_improvement_estimate,
           "recommended": "build automation", "estimates_are_assumptions": True}
    storage.save(name, "comp_auto_%s" % workstream_id, rec, store)
    return {"ok": True, "automation": rec}


def productize(name: str, *, workstream_id: str, proof_present: bool, free_layer: str,
               paid_layers: list, build_approval_ref: str = "", store: Path | None = None) -> dict:
    """Recommend turning a service into a product. Needs proof; building needs approval."""
    if not proof_present:
        return {"ok": False, "error": "productization needs workflow/demand proof"}
    if not (build_approval_ref or "").strip():
        return {"ok": False, "error": "building a product requires approval"}
    if not paid_layers:
        return {"ok": False, "error": "a product needs a paid layer"}
    rec = {"productization_id": "cprod_" + uuid.uuid4().hex[:8], "workstream_id": workstream_id,
           "free_layer": free_layer, "paid_layers": list(paid_layers),
           "build_approval_ref": build_approval_ref, "recommended_form": "free_core_paid_product"}
    storage.save(name, "comp_prod_%s" % workstream_id, rec, store)
    return {"ok": True, "productization": rec}


def _idx(name, wid, store):
    idx = storage.load(name, "comp_alloc_index", store, default={"ids": []})
    if wid not in idx["ids"]:
        idx["ids"].append(wid); storage.save(name, "comp_alloc_index", idx, store)


def allocations(name, store=None) -> list:
    idx = storage.load(name, "comp_alloc_index", store, default={"ids": []})["ids"]
    return [a for a in (storage.load(name, "comp_alloc_%s" % i, store, default=None) for i in idx) if a]
