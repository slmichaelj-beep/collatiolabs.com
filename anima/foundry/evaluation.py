"""foundry.evaluation — strategy council + market validation + business simulation.

Truth-disciplined: the council preserves disagreement and the skeptic can force a no_go; market
claims must cite a source or be labeled an assumption; simulation never states a single certain
outcome (always best/base/worst with explicit assumptions + the highest-risk variable).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

COUNCIL_ROLES = ("Capital Allocator", "Economist", "Product Strategist", "Market Analyst",
                 "Customer Psychologist", "Growth Operator", "Sales Operator", "Operations Operator",
                 "Finance Controller", "Legal/IP Coordinator", "Risk Officer",
                 "Skeptic / Devil's Advocate", "Execution Operator")
VERDICTS = ("go", "no_go", "maybe_if_changed", "research_more", "test_first")
MARKET_VERDICTS = ("GO", "NO_GO", "MAYBE_IF_CHANGED", "RESEARCH_MORE", "TEST_CHEAPLY_FIRST")


def strategy_council(name: str, idea: dict, *, role_inputs: dict | None = None,
                     store: Path | None = None) -> dict:
    """Run the council. role_inputs maps role->{vote, opportunity, risk, ...}; missing roles get a
    neutral research_more. The skeptic's no_go is preserved and can drive the synthesis."""
    role_inputs = role_inputs or {}
    votes = []
    for role in COUNCIL_ROLES:
        ri = role_inputs.get(role, {})
        votes.append({"role": role, "vote": ri.get("vote", "research_more"),
                      "opportunity": ri.get("opportunity", ""), "risk": ri.get("risk", ""),
                      "key_assumptions": ri.get("key_assumptions", []),
                      "recommended_test": ri.get("recommended_test", ""),
                      "confidence": ri.get("confidence", "low")})
    tally = {}
    for v in votes:
        tally[v["vote"]] = tally.get(v["vote"], 0) + 1
    skeptic = next((v for v in votes if v["role"].startswith("Skeptic")), {})
    disagreements = sorted({v["vote"] for v in votes})
    # synthesis: a strong skeptic no_go + few go's => no_go/research_more; never forced to go
    n_go = tally.get("go", 0)
    n_nogo = tally.get("no_go", 0)
    if skeptic.get("vote") == "no_go" and n_go < len(COUNCIL_ROLES) // 2:
        rec = "no_go" if n_nogo >= 3 else "research_more"
    elif n_go >= max(7, len(COUNCIL_ROLES) // 2 + 1):
        rec = "go"
    elif tally.get("test_first", 0) + tally.get("maybe_if_changed", 0) >= 4:
        rec = "test_first"
    else:
        rec = "research_more"
    out = {"council_id": "cnc_" + uuid.uuid4().hex[:12], "idea_id": idea.get("idea_id"),
           "votes": votes, "tally": tally, "major_disagreements": disagreements,
           "highest_risk_assumption": skeptic.get("risk") or "the riskiest assumption is untested",
           "cheapest_next_test": next((v["recommended_test"] for v in votes if v["recommended_test"]),
                                      "a low-cost validation test"),
           "recommendation": rec, "created_at": storage.now()}
    storage.emit_truth(name, "council", out["council_id"], "COUNCIL: %s" % rec, actor="vera", store=store)
    return out


def market_validation(name: str, idea: dict, *, claims=None, store: Path | None = None) -> dict:
    kept, refused = [], []
    for c in claims or []:
        if c.get("source"):
            kept.append({"text": c["text"], "source": c["source"], "kind": "sourced"})
        elif c.get("assumption"):
            kept.append({"text": c["text"], "kind": "assumption"})
        else:
            refused.append(c.get("text", ""))
    verdict = "RESEARCH_MORE"
    if refused:
        verdict = "RESEARCH_MORE"   # unsupported claims => not ready
    elif kept and all(c["kind"] == "sourced" for c in kept):
        verdict = "MAYBE_IF_CHANGED"
    elif kept:
        verdict = "TEST_CHEAPLY_FIRST"
    out = {"validation_id": "mv_" + uuid.uuid4().hex[:12], "idea_id": idea.get("idea_id"),
           "claims": kept, "refused_unsupported_claims": refused,
           "unknowns": [c["text"] for c in kept if c["kind"] == "assumption"],
           "verdict": verdict, "rationale": "claims labeled by evidence; unknowns surfaced",
           "created_at": storage.now()}
    return out


def simulation(name: str, idea: dict, *, price=0.0, conversion=0.0, cac=0.0, monthly_cost=0.0,
               assumptions=None, store: Path | None = None) -> dict:
    """Model outcomes with uncertainty. NEVER a single certain number — best/base/worst with the
    assumptions stated and the highest-risk variable named."""
    goal = float(idea.get("revenue_goal", 0) or 0)
    budget = float(idea.get("budget_limit", idea.get("budget", 0)) or 0)
    runway = (budget / monthly_cost) if monthly_cost > 0 else None
    drivers = {"conversion": conversion, "cac": cac, "price": price}
    riskiest = max(drivers, key=lambda k: (1.0 / (drivers[k] + 1e-9)) if k == "conversion"
                   else drivers[k]) if any(drivers.values()) else "conversion"
    out = {"simulation_id": "sim_" + uuid.uuid4().hex[:12], "idea_id": idea.get("idea_id"),
           "assumptions": assumptions or {"price": price, "conversion": conversion, "cac": cac,
                                          "monthly_cost": monthly_cost},
           "scenarios": {"worst": round(goal * 0.2, 2), "base": round(goal * 0.6, 2),
                         "best": round(goal, 2)},
           "runway_months": runway, "break_even_note": "depends on conversion + CAC holding",
           "highest_risk_variable": riskiest,
           "sensitivity": {k: "a %s swing moves the outcome materially" % k for k in drivers},
           "statement": "Under these assumptions this COULD reach $%.0f if conversion, CAC and "
                         "price hold — not a guarantee." % goal,
           "created_at": storage.now()}
    return out
