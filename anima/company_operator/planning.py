"""company_operator.planning — idea -> validation -> go/no-go -> business case -> blueprint.

Pure planning. No external action, no spend, no account creation — this only produces structured
artifacts the founder reviews. Market claims must cite sources or be labeled assumptions (no fake
certainty). The committee is willing to say NO. Nothing here advances without founder approval.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

# ---- idea intake ----------------------------------------------------------------------------
IDEA_REQUIRED = ("problem", "target_customer", "proposed_solution", "budget_limit",
                 "revenue_goal", "timeline", "jurisdiction", "risk_tolerance")


def intake(name: str, raw_idea: str, fields: dict | None = None, *, store: Path | None = None) -> dict:
    f = fields or {}
    rec = {"idea_id": "idea_" + uuid.uuid4().hex[:12], "raw_idea": raw_idea[:2000],
           "problem": f.get("problem", ""), "target_customer": f.get("target_customer", ""),
           "proposed_solution": f.get("proposed_solution", ""), "why_now": f.get("why_now", ""),
           "differentiation": f.get("differentiation", ""), "constraints": f.get("constraints", []),
           "budget_limit": float(f.get("budget_limit", 0) or 0),
           "revenue_goal": float(f.get("revenue_goal", 0) or 0),
           "timeline": f.get("timeline", ""), "risk_tolerance": f.get("risk_tolerance", "medium"),
           "jurisdiction": f.get("jurisdiction", ""), "created_at": storage.now()}
    missing = [k for k in IDEA_REQUIRED if not rec.get(k)]
    rec["missing_fields"] = missing
    rec["status"] = "ready_for_validation" if not missing else "draft"
    storage.save(name, "idea_%s" % rec["idea_id"], rec, store)
    storage.emit_truth(name, "idea", rec["idea_id"], "IDEA: " + raw_idea[:140], actor="user", store=store)
    return rec


def validate_market(name: str, idea: dict, *, claims=None, store: Path | None = None) -> dict:
    """Market validation. Each claim is {text, source|assumption}. A claim with neither a source
    nor an explicit assumption label is REFUSED (no unsupported market certainty)."""
    cleaned, refused = [], []
    for c in claims or []:
        if c.get("source"):
            cleaned.append({"text": c["text"], "source": c["source"], "kind": "sourced"})
        elif c.get("assumption"):
            cleaned.append({"text": c["text"], "kind": "assumption"})
        else:
            refused.append(c.get("text", ""))
    verdict = "maybe_if_changed"
    if idea.get("missing_fields"):
        verdict = "research_more"
    rec = {"validation_id": "val_" + uuid.uuid4().hex[:12], "idea_id": idea["idea_id"],
           "claims": cleaned, "refused_unsupported_claims": refused,
           "unknowns": [c["text"] for c in cleaned if c["kind"] == "assumption"],
           "verdict": verdict, "rationale": "needs founder review; claims labeled by evidence",
           "created_at": storage.now()}
    storage.save(name, "validation_%s" % idea["idea_id"], rec, store)
    return rec


def committee(name: str, idea: dict, validation: dict, *, store: Path | None = None) -> dict:
    """Go / No-Go investment committee — biased toward truth, NOT toward building."""
    kill, go = [], []
    if idea.get("missing_fields"):
        kill.append("incomplete idea (missing: %s)" % ", ".join(idea["missing_fields"]))
    if validation.get("refused_unsupported_claims"):
        kill.append("market case rests on unsupported claims")
    if idea.get("budget_limit", 0) <= 0:
        kill.append("no budget set — cannot assess fit")
    if validation.get("unknowns"):
        go.append("clear assumptions to test")
    if not idea.get("differentiation"):
        kill.append("no stated differentiation")
    rec = {"committee_id": "cmte_" + uuid.uuid4().hex[:12], "idea_id": idea["idea_id"],
           "kill_reasons": kill, "go_reasons": go,
           "recommendation": "no_go" if len(kill) >= 2 else ("research_more" if kill else "go"),
           "board_questions": ["Is the budget loss-tolerable?", "Which assumption is riskiest?"],
           "created_at": storage.now()}
    storage.save(name, "committee_%s" % idea["idea_id"], rec, store)
    storage.emit_truth(name, "committee", idea["idea_id"],
                       "GO/NO-GO: %s" % rec["recommendation"], actor="vera", store=store)
    return rec


def business_case(name: str, idea: dict, *, monthly_cost: float = 0.0,
                  store: Path | None = None) -> dict:
    budget = float(idea.get("budget_limit", 0) or 0)
    goal = float(idea.get("revenue_goal", 0) or 0)
    runway_months = (budget / monthly_cost) if monthly_cost > 0 else None
    rec = {"business_case_id": "bc_" + uuid.uuid4().hex[:12], "idea_id": idea["idea_id"],
           "startup_budget": budget, "monthly_operating_cost": monthly_cost,
           "runway_months": runway_months, "revenue_goal": goal,
           "scenarios": {"worst": goal * 0.2, "base": goal * 0.6, "best": goal},
           "kill_thresholds": ["spend exceeds budget", "no paying customer by end of runway"],
           "created_at": storage.now()}
    storage.save(name, "business_case_%s" % idea["idea_id"], rec, store)
    return rec


def blueprint(name: str, idea: dict, validation: dict, comm: dict, bcase: dict, *,
              store: Path | None = None) -> dict:
    """The full operating blueprint — DRAFT, requires founder approval before any execution."""
    rec = {"blueprint_id": "bp_" + uuid.uuid4().hex[:12], "idea_id": idea["idea_id"],
           "status": "draft",
           "sections": {
               "mission": idea.get("proposed_solution", ""),
               "customer": idea.get("target_customer", ""),
               "problem": idea.get("problem", ""),
               "business_model": "(to refine)", "go_no_go": comm["recommendation"],
               "budget": bcase["startup_budget"], "revenue_goal": bcase["revenue_goal"],
               "market_unknowns": validation.get("unknowns", []),
               "account_setup_checklist": "(planned in account registry — registry only, human-created)",
               "legal_checklist": "(planned in legal coordinator — drafts only)",
               "90_day_plan": [], "1_year_plan": [], "10_year_plan": [],
               "approval_queue": "all external actions queue for approval",
           },
           "requires_approval_before_execution": True, "created_at": storage.now()}
    storage.save(name, "blueprint_%s" % idea["idea_id"], rec, store)
    storage.emit_truth(name, "blueprint", idea["idea_id"], "BLUEPRINT draft for idea %s"
                       % idea["idea_id"], actor="vera", store=store)
    return rec
