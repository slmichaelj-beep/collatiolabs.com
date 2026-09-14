"""teams.api — assemble the /teams dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from anima.company import storage


def _collect(name, prefix, store):
    # the company store is file-per-key; enumerate via the entity dir
    d = storage.company_dir(name, store)
    out = []
    try:
        for p in sorted(d.glob("%s*.json" % prefix)):
            import json
            try:
                out.append(json.loads(p.read_text()))
            except Exception:
                pass
    except Exception:
        pass
    return out


def dashboard(name: str, store: Path | None = None) -> dict:
    orgs = _collect(name, "team_org_", store)
    wos = _collect(name, "team_wo_", store)
    vendors = _collect(name, "team_vendor_", store)
    escal = _collect(name, "team_escalation_", store)
    agentt = _collect(name, "team_agentteam_", store)
    return {
        "ok": True,
        "orgs": [{"mission": o["mission"], "org_type": o["org_type"], "roles": len(o.get("roles", []))}
                 for o in orgs],
        "roles_total": sum(len(o.get("roles", [])) for o in orgs),
        "work_orders": [{"title": w["title"], "status": w["status"]} for w in wos],
        "agent_teams": [{"mission": a["mission"], "agents": len(a.get("agents", []))} for a in agentt],
        "vendors": [{"name": v["name"], "category": v["category"], "status": v["status"]} for v in vendors],
        "escalations": [{"trigger": x["trigger"], "severity": x["severity"]} for x in escal],
        "board_escalations": [x["trigger"] for x in escal if x.get("board_visible")],
        "honesty": "every role has authority bounds; paid work needs budget; external work needs "
                   "approval; no deliverable accepted without review; agents never bypass authority.",
    }
