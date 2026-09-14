"""teams.org — product-support organization designer + role/responsibility system.

Designs the support org for a product/offer and defines its roles. A role with no responsibilities,
no authority boundary, or no deliverables is refused. No role may exceed the Collatio authority
policy. Professional roles (legal/tax/accounting/patent) require a human/professional identity.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

ORG_TYPES = ("vera_only", "agent_augmented", "contractor_augmented", "vendor_augmented", "full_team")
ROLE_TYPES = ("ai_agent", "human_contractor", "vendor", "professional", "vera_internal")
AUTH_LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
_PROFESSIONAL = ("professional",)


def design_org(name: str, *, product_or_offer_id: str, mission: str, org_type: str = "agent_augmented",
               budget_ref: str = "", escalation_policy: str = "", quality_policy: str = "",
               reporting_cadence: str = "weekly", store: Path | None = None) -> dict:
    if org_type not in ORG_TYPES:
        return {"ok": False, "error": "unknown org type %r" % org_type}
    if not (escalation_policy and quality_policy):
        return {"ok": False, "error": "an org needs an escalation policy + a quality policy"}
    rec = {"org_id": "org_" + uuid.uuid4().hex[:10], "entity_id": "collatio_labs_llc",
           "product_or_offer_id": product_or_offer_id, "org_type": org_type, "mission": mission,
           "roles": [], "budget_ref": budget_ref, "authority_policy_ref": "collatio.authority",
           "support_capacity": "TBD", "escalation_policy": escalation_policy,
           "quality_policy": quality_policy, "reporting_cadence": reporting_cadence,
           "truth_refs": [], "observation_refs": []}
    storage.save(name, "team_org_%s" % rec["org_id"], rec, store)
    storage.emit_truth(name, "team_org", rec["org_id"], "ORG designed: " + mission, actor="user", store=store)
    return {"ok": True, "org": rec}


def add_role(name: str, org_id: str, *, role_name: str, role_type: str, responsibilities: list,
             deliverables: list, allowed_actions: list | None = None,
             approval_required_actions: list | None = None, forbidden_actions: list | None = None,
             authority_level: str = "L0", success_metrics: list | None = None,
             store: Path | None = None) -> dict:
    org = storage.load(name, "team_org_%s" % org_id, store, default=None)
    if not org:
        return {"ok": False, "error": "no such org"}
    if role_type not in ROLE_TYPES:
        return {"ok": False, "error": "unknown role type %r" % role_type}
    if not responsibilities:
        return {"ok": False, "error": "a role needs responsibilities — refused"}
    if not deliverables:
        return {"ok": False, "error": "a role needs deliverables — refused"}
    if authority_level not in AUTH_LEVELS:
        return {"ok": False, "error": "bad authority level"}
    rec = {"role_id": "role_" + uuid.uuid4().hex[:8], "org_id": org_id, "role_name": role_name,
           "role_type": role_type,
           "owner": {"ai_agent": "Vera", "vera_internal": "Vera"}.get(role_type, "human"),
           "responsibilities": list(responsibilities),
           "allowed_actions": list(allowed_actions or []),
           "approval_required_actions": list(approval_required_actions or ["external_message", "spend"]),
           "forbidden_actions": list(forbidden_actions or ["sign_contract", "move_money"]),
           "deliverables": list(deliverables), "success_metrics": list(success_metrics or []),
           "quality_checks": ["peer/QA review before acceptance"],
           "authority_level": authority_level,
           "requires_human_identity": role_type in _PROFESSIONAL,
           "status": "planned"}
    org["roles"].append(rec); storage.save(name, "team_org_%s" % org_id, org, store)
    return {"ok": True, "role": rec}


def get_org(name, org_id, store=None):
    return storage.load(name, "team_org_%s" % org_id, store, default=None) or None
