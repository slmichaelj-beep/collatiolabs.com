"""market_vision.validation — the cheapest next proof for every opportunity.

Recommends a validation experiment. Every recommendation REQUIRES success criteria, kill criteria,
a budget, and explicit approval before any spend or outreach. Vera prepares the experiment; a human
approves and runs anything that costs money or contacts a person.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

METHODS = ("landing_page_smoke_test", "waitlist", "customer_interview", "pricing_survey",
           "demo_mock", "concierge_mvp", "outreach_test", "search_demand_test",
           "competitor_teardown", "prototype_test", "pilot_offer")
# methods that touch money or people => always need approval before running
_SPEND_OR_OUTREACH = ("landing_page_smoke_test", "outreach_test", "pilot_offer", "concierge_mvp",
                      "search_demand_test")


def recommend(name: str, opportunity_id: str, *, hypothesis: str, method: str, budget: float,
              duration: str, success_criteria: list, kill_criteria: list, expected_learning: str = "",
              store: Path | None = None) -> dict:
    """Recommend an experiment. Refused without success criteria, kill criteria, and a budget value."""
    if method not in METHODS:
        return {"ok": False, "error": "unknown validation method %r" % method}
    if not success_criteria:
        return {"ok": False, "error": "an experiment needs success criteria — refused"}
    if not kill_criteria:
        return {"ok": False, "error": "an experiment needs kill criteria — refused"}
    if budget is None:
        return {"ok": False, "error": "an experiment needs a budget (even $0) — refused"}
    rec = {"experiment_id": "exp_" + uuid.uuid4().hex[:10], "opportunity_id": opportunity_id,
           "hypothesis": hypothesis, "method": method, "budget": float(budget), "duration": duration,
           "success_criteria": list(success_criteria), "kill_criteria": list(kill_criteria),
           "expected_learning": expected_learning,
           "required_approval": True,
           "touches_spend_or_outreach": method in _SPEND_OR_OUTREACH,
           "approval_note": ("REQUIRES human approval before any spend/outreach"
                             if (budget > 0 or method in _SPEND_OR_OUTREACH)
                             else "no-cost desk research; still queued for approval"),
           "status": "recommended", "approval_ref": None, "created_at": storage.now()}
    storage.save(name, "mv_experiment_%s" % opportunity_id, rec, store)
    storage.emit_truth(name, "mv_experiment", rec["experiment_id"],
                       "VALIDATION %s ($%s) for %s — approval required" % (method, budget, opportunity_id),
                       actor="vera", store=store)
    return {"ok": True, "experiment": rec}


def get(name, opportunity_id, store=None):
    return storage.load(name, "mv_experiment_%s" % opportunity_id, store, default=None) or None
