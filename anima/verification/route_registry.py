"""verification.route_registry — every operator route carries an explicit classification.

The closure bar: a route is acceptable as un-built ONLY if it is affirmatively classified
not_claimed / future_tier — never merely absent. This is the single source of truth for which
operator routes are live (must be linked + served + proven) vs. honestly not-claimed (must NOT be
linked as active). If a route is later claimed live, flipping it here forces the nav/rover/
observation certs to require it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

STATUSES = ("linked_active", "not_claimed", "future_tier", "coming_soon", "removed")

# the canonical operator route classification
ROUTES = {
    "/learning":   {"status": "linked_active", "label": "Learning Integrity"},
    "/founder":    {"status": "linked_active", "label": "Founder Command Center"},
    "/chairman":   {"status": "linked_active", "label": "Chairman · Venture Portfolio"},
    "/observation": {"status": "linked_active", "label": "Observation"},
    # built-elsewhere live surfaces (linked from the chat UI already)
    "/verification": {"status": "linked_active", "label": "Verification Dashboard"},
    "/security":   {"status": "linked_active", "label": "Security & Quarantine"},
    "/console":    {"status": "linked_active", "label": "Founder Console (patterns)"},
    "/consent":    {"status": "linked_active", "label": "Consent & Boundaries"},
    # live revenue surfaces (the commercialization loop)
    "/sales":      {"status": "linked_active", "label": "Sales · pipeline + revenue"},
    "/commercial": {"status": "linked_active", "label": "Commercial · inventory → wedge → offer"},
    "/opportunities": {"status": "linked_active", "label": "Opportunities · market vision"},
    "/collatio":   {"status": "linked_active", "label": "Collatio · operating authority"},
    "/teams":      {"status": "linked_active", "label": "Teams · org + delegation"},
    "/workforce":  {"status": "linked_active", "label": "Workforce · digital workforce foundry"},
    "/self":       {"status": "linked_active", "label": "Self · observe / heal / evolve"},
    "/revenue":    {"status": "linked_active", "label": "Revenue · immediate strike engine"},
    "/revenue/cash": {"status": "linked_active", "label": "Revenue · $16k cash milestone"},
    "/marketplaces/fiverr": {"status": "linked_active", "label": "Fiverr · governed channel"},
    "/pipeline":   {"status": "linked_active", "label": "Pipeline · live Upwork bid funnel"},
    "/revenue/swarm": {"status": "linked_active", "label": "Revenue · swarm factory"},
    "/compounding": {"status": "linked_active", "label": "Compounding · global allocator"},
    "/revenue/intelligence": {"status": "linked_active", "label": "Revenue · intelligence"},
    "/distribution": {"status": "linked_active", "label": "Distribution · demand capture"},
    "/trust/moat":  {"status": "linked_active", "label": "Trust · proof + reputation moat"},
    "/resources":  {"status": "linked_active", "label": "Resources · expansion planner"},
    "/empire":     {"status": "linked_active", "label": "Empire · multi-host + capital"},
    # NOT built as standalone pages — affirmatively classified, never linked as active.
    "/board":      {"status": "not_claimed", "label": "Board",
                    "reason": "board surface is /chairman; no separate /board page is claimed"},
    "/board/revenue": {"status": "linked_active", "label": "Board · Revenue"},
}


def linked_active() -> list[str]:
    return [r for r, v in ROUTES.items() if v["status"] == "linked_active"]


def not_claimed() -> list[str]:
    return [r for r, v in ROUTES.items() if v["status"] in ("not_claimed", "future_tier", "coming_soon")]


def classification(route: str) -> str | None:
    rec = ROUTES.get(route)
    return rec["status"] if rec else None


def build_report() -> dict:
    out = {"report": "operator_route_registry", "routes": ROUTES,
           "linked_active": linked_active(), "not_claimed": not_claimed(),
           "counts": {s: sum(1 for v in ROUTES.values() if v["status"] == s) for s in STATUSES
                      if any(v["status"] == s for v in ROUTES.values())}}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "operator_route_registry.json").write_text(json.dumps(out, indent=1))
    md = ["# Operator route registry — every route classified", "",
          "| route | status | label |", "|---|---|---|"]
    md += ["| %s | **%s** | %s |" % (r, v["status"], v["label"]) for r, v in ROUTES.items()]
    (REPORTS / "operator_route_registry.md").write_text("\n".join(md) + "\n")
    return out


if __name__ == "__main__":
    print(json.dumps(build_report()["counts"], indent=1))
