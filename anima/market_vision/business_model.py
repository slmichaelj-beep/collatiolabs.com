"""market_vision.business_model — ethical revenue models + free-core economics.

Generates business models that do NOT depend on selling user data. Data-sale / dark-pattern /
deceptive-ads / privacy-washing models are refused outright. A privacy-position claim must be
evidence-backed; cost-to-serve and gross-margin assumptions are always labeled assumptions.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

ALLOWED_FAMILIES = ("free_core_paid_pro", "free_local_paid_support", "free_tool_paid_hosting",
                    "free_tool_paid_teams", "free_tool_paid_automation", "open_core_paid_managed",
                    "paid_implementation", "paid_compliance_audit", "paid_knowledge_packs",
                    "paid_integrations", "enterprise_private_deployment", "usage_based", "premium_templates")
FORBIDDEN_FAMILIES = ("sell_user_data", "dark_pattern", "deceptive_ads", "fake_scarcity",
                      "privacy_washing", "spam_monetization")
DATA_POLICY = ("no_sale", "local_first", "minimal_collection", "unknown")


def generate(name: str, opportunity_id: str, *, family: str, free_layer: str, paid_layers: list,
             data_policy: str = "no_sale", cost_to_serve: str = "", gross_margin_assumption: str = "",
             privacy_position: str = "", privacy_evidence_refs: list | None = None,
             store: Path | None = None) -> dict:
    """Generate an ethical business model. A forbidden family is refused; a strong privacy claim
    needs evidence; data_policy may never be a sale model."""
    if family in FORBIDDEN_FAMILIES or family not in ALLOWED_FAMILIES:
        return {"ok": False, "error": "business model family %r is forbidden/unknown" % family}
    if data_policy not in DATA_POLICY or data_policy == "unknown":
        data_policy = "minimal_collection"
    if privacy_position and not (privacy_evidence_refs or []):
        return {"ok": False, "error": "a privacy-position claim requires evidence refs — refused"}
    if not paid_layers:
        return {"ok": False, "error": "no paid layer — model is not economically real"}
    rec = {"model_id": "bm_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id, "family": family,
           "free_layer": free_layer, "paid_layers": list(paid_layers),
           "gross_margin_assumption": gross_margin_assumption or "ASSUMPTION: not yet validated",
           "cost_to_serve": cost_to_serve or "ASSUMPTION: estimate pending",
           "privacy_position": privacy_position, "data_policy": data_policy,
           "privacy_evidence_refs": list(privacy_evidence_refs or []),
           "revenue_paths": list(paid_layers), "no_data_sale": True}
    storage.save(name, "mv_model_%s" % opportunity_id, rec, store)
    storage.emit_truth(name, "mv_model", rec["model_id"], "MODEL %s for %s" % (family, opportunity_id),
                       actor="vera", store=store)
    return {"ok": True, "model": rec}


def model_free_core(name: str, opportunity_id: str, *, what_is_free: str, what_is_paid: str,
                    why_upgrade: str, cost_per_free_user: float, conversion_assumption: float,
                    support_burden: str = "low", store: Path | None = None) -> dict:
    """Make the free tier economically real. Refused if the free tier is economically impossible
    (positive per-user cost with a zero conversion assumption)."""
    if cost_per_free_user > 0 and conversion_assumption <= 0:
        return {"ok": False, "error": "free tier economically impossible (cost>0, conversion=0)"}
    break_even = round(cost_per_free_user / conversion_assumption, 2) if conversion_assumption > 0 else None
    rec = {"free_core_id": "fc_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id,
           "what_is_free": what_is_free, "what_is_paid": what_is_paid, "why_upgrade": why_upgrade,
           "cost_per_free_user": cost_per_free_user,
           "conversion_assumption": conversion_assumption,
           "conversion_is_assumption": True,
           "break_even_paid_value": break_even, "support_burden": support_burden,
           "ethical_upsell_policy": "no dark patterns; upgrade is value-driven, not coerced"}
    storage.save(name, "mv_freecore_%s" % opportunity_id, rec, store)
    return {"ok": True, "free_core": rec}
