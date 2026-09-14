"""company.handoff — high-quality engineering handoffs that preserve reality.

A handoff cites evidence (engineering state, decisions, risks, cert artifacts), separates the
product decision from the implementation, and REFUSES to claim a clean baseline from a dirty/stale
tree (it states the dirt instead). Output is a durable artifact + a Truth Ledger event.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import decisions, engineering_state, risks, storage

TYPES = ("engineering_increment", "bug_fix", "cert_failure", "product_decision",
         "architecture_change", "release_candidate", "agent_handoff", "codex_handoff",
         "claude_handoff")


def generate(name: str, objective: str, *, htype: str = "engineering_increment",
             non_negotiables=None, files=None, commands=None, certs=None, reports=None,
             success=None, failure=None, rollback="", do_not_build=None,
             store: Path | None = None) -> dict:
    eng = engineering_state.snapshot()
    baseline_clean = eng["deploy_clean"]
    rec = {
        "handoff_id": "ho_" + uuid.uuid4().hex[:12],
        "type": htype if htype in TYPES else "engineering_increment",
        "objective": objective,
        "current_state": {
            "commit": eng["commit"], "server_commit": eng["server_commit"],
            "dirty_worktree": eng["dirty_worktree"], "dirty_files": eng["dirty_files"][:20],
            "baseline_clean": baseline_clean,
            "stale_certs": eng["stale_certs"], "stale_reports": eng["stale_reports"],
            "known_deferred": eng["known_deferred"], "known_enterprise_only": eng["known_enterprise_only"],
        },
        "non_negotiables": non_negotiables or [
            "No fake green", "Commit + restart + deploy_check GREEN before claiming done",
            "Every claim traces to a Truth Ledger event"],
        "files_likely_involved": files or [],
        "commands_to_run": commands or ["python3 scripts/deploy_check.py"],
        "certs_to_update": certs or [],
        "reports_to_write": reports or [],
        "success_criteria": success or [],
        "failure_conditions": failure or [],
        "rollback_plan": rollback or "git revert the increment commit; restart server on HEAD",
        "stop_conditions": ["a product decision is needed (write it to the founder queue and stop)"],
        "do_not_build_yet": do_not_build or [],
        "open_risks": [{"title": r["title"], "severity": r["severity"]}
                       for r in risks.top_risks(name, store)[:5]],
        "open_decisions": [{"title": d["title"]} for d in
                           decisions.views(name, store)["open"][:5]],
        "baseline_warning": (None if baseline_clean else
                             "BASELINE NOT CLEAN — %s; this handoff does not claim a clean start, "
                             "fix the baseline first (%s)"
                             % (("dirty: " + ", ".join(eng["dirty_files"][:5])) if eng["dirty_worktree"]
                                else "server != HEAD", eng["next_recommended_action"])),
        "created_at": storage.now(),
    }
    items = storage.load(name, "handoffs", store, default={"handoffs": []})["handoffs"]
    items.append(rec)
    storage.save(name, "handoffs", {"handoffs": items}, store)
    rec["truth_ledger_event"] = storage.emit_truth(name, "handoff", rec["handoff_id"],
                                                   "HANDOFF[%s]: %s" % (rec["type"], objective[:160]),
                                                   actor="vera", store=store)
    items[-1]["truth_ledger_event"] = rec["truth_ledger_event"]
    storage.save(name, "handoffs", {"handoffs": items}, store)
    return rec


def render_markdown(rec: dict) -> str:
    L = ["# Handoff — %s" % rec["objective"], "", "Type: **%s** · %s" % (rec["type"], rec["created_at"]), ""]
    if rec.get("baseline_warning"):
        L += ["> ⚠️ %s" % rec["baseline_warning"], ""]
    cs = rec["current_state"]
    L += ["## Current state",
          "- commit `%s` · server `%s` · baseline clean: %s" % (cs["commit"], cs["server_commit"], cs["baseline_clean"]),
          "- dirty: %s" % (", ".join(cs["dirty_files"]) or "none"),
          "- stale certs: %s · stale reports: %s" % (cs["stale_certs"] or "none", cs["stale_reports"] or "none"),
          "- deferred: %s · enterprise-only: %s" % (cs["known_deferred"] or "none", cs["known_enterprise_only"] or "none"),
          ""]
    for title, key in [("Non-negotiables", "non_negotiables"), ("Files likely involved", "files_likely_involved"),
                       ("Commands", "commands_to_run"), ("Certs to update", "certs_to_update"),
                       ("Reports to write", "reports_to_write"), ("Success criteria", "success_criteria"),
                       ("Failure conditions", "failure_conditions"), ("Do NOT build yet", "do_not_build_yet")]:
        vals = rec.get(key) or []
        if vals:
            L += ["## " + title] + ["- %s" % v for v in vals] + [""]
    L += ["## Rollback", rec["rollback_plan"], "", "## Stop conditions"] + ["- %s" % s for s in rec["stop_conditions"]]
    return "\n".join(L) + "\n"
