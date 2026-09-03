"""company.briefing — the Daily Founder Briefing. Vera starts the day like a company operator.

Generated from CURRENT state only. If the engineering state is stale/dirty, the briefing says so
rather than asserting confident status — no hallucinated company status.
"""
from __future__ import annotations

from pathlib import Path

from . import decisions, engineering_state, founder_queue, release_tracker, risks


def build(name: str, store: Path | None = None) -> dict:
    eng = engineering_state.snapshot()
    rel = release_tracker.state()
    top = risks.top_risks(name, store)[:5]
    fq = founder_queue.open_items(name, store)[:8]
    open_dec = decisions.views(name, store)["open"][:5]

    # honest confidence: stale/dirty -> we flag it rather than claim status
    caveats = []
    if not eng["deploy_clean"]:
        caveats.append("engineering baseline is not clean (%s) — status below is provisional"
                       % eng["next_recommended_action"])
    if eng["stale_certs"] or eng["stale_reports"]:
        caveats.append("stale certs/reports present — regenerate before trusting release status")
    if not rel.get("ok"):
        caveats.append("verification data unreachable — cannot confirm release tier right now")

    blocking_q = [q for q in fq if q["urgency"] == "blocking"]
    highest_leverage = (eng["next_recommended_action"] if not eng["deploy_clean"]
                        else (("answer the blocking founder question: " + blocking_q[0]["question"])
                              if blocking_q else
                              ("mitigate the top risk: " + top[0]["title"]) if top else
                              "advance the next release-tier gate"))

    return {
        "ok": True,
        "generated_at": eng["generated_at"],
        "caveats": caveats,
        "sections": {
            "company_status": {
                "commit": eng["commit"], "deploy_clean": eng["deploy_clean"],
                "highest_green_tier": rel.get("highest_green"),
            },
            "what_changed": {"commit": eng["commit"], "server_commit": eng["server_commit"],
                             "dirty_files": eng["dirty_files"]},
            "open_blockers": {
                "stale_certs": eng["stale_certs"], "stale_reports": eng["stale_reports"],
                "product_red": rel.get("product_red", []), "product_partial": rel.get("product_partial", []),
                "unclassified": rel.get("unclassified", []),
            },
            "highest_leverage_next_move": highest_leverage,
            "founder_decisions_needed": [{"q": q["question"], "urgency": q["urgency"],
                                          "recommended": q.get("recommended_option")} for q in fq],
            "engineering_state": {"next_action": eng["next_recommended_action"]},
            "cert_release_state": {"tiers": rel.get("tiers", []),
                                   "deferred": rel.get("deferred_not_claimed", []),
                                   "enterprise_only": rel.get("enterprise_only", [])},
            "risks": [{"title": r["title"], "severity": r["severity"]} for r in top],
            "open_decisions": [{"title": d["title"]} for d in open_dec],
            "deferred_not_claimed": rel.get("deferred_not_claimed", []),
        },
    }


def render_text(b: dict) -> str:
    s = b["sections"]
    L = ["Today's founder briefing (%s):" % b["generated_at"]]
    if b["caveats"]:
        L += ["", "⚠️ confidence caveats:"] + ["- " + c for c in b["caveats"]]
    L += ["", "- Highest-leverage next move: " + s["highest_leverage_next_move"],
          "- Deploy clean: %s · highest green tier: %s" % (
              s["company_status"]["deploy_clean"], s["company_status"]["highest_green_tier"]),
          "- Open blockers: red=%s partial=%s stale_certs=%s" % (
              s["open_blockers"]["product_red"] or "none",
              s["open_blockers"]["product_partial"] or "none",
              s["open_blockers"]["stale_certs"] or "none"),
          "- Founder decisions needed: %d" % len(s["founder_decisions_needed"]),
          "- Top risks: " + (", ".join(r["title"] for r in s["risks"]) or "none"),
          "- Deferred / not claimed: " + (", ".join(s["deferred_not_claimed"]) or "none")]
    return "\n".join(L) + "\n"
