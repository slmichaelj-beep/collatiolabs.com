"""commercial.proposal — proposal / SOW DRAFT builder (prepared, never signed/sent).

Generates a proposal + statement-of-work draft from an approved offer. Scope, deliverables,
timeline, and price (a recommendation until a human commits it) are laid out. Sending the proposal
and SIGNING the contract are HUMAN-ONLY actions — Vera prepares and queues, it never executes them.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage


def draft(name: str, asset_id: str, *, client: str, scope: list, deliverables: list,
          timeline: str, price_recommendation: float, terms: str = "", store: Path | None = None) -> dict:
    rec = {
        "proposal_id": "sow_" + uuid.uuid4().hex[:10], "asset_id": asset_id,
        "client": client, "scope": list(scope), "deliverables": list(deliverables),
        "timeline": timeline,
        "price_recommendation": price_recommendation,
        "price_is_commitment": False,
        "terms": terms,
        "status": "draft",
        "send_status": "NOT sent — sending a proposal is a human action (approval required)",
        "sign_status": "sign_contract is HUMAN-ONLY (legal action; Vera never signs)",
        "created_at": storage.now(),
    }
    storage.save(name, "proposal_%s" % rec["proposal_id"], rec, store)
    storage.emit_truth(name, "proposal", rec["proposal_id"],
                       "PROPOSAL/SOW draft prepared for %s (not sent, not signed)" % client,
                       actor="vera", store=store)
    return rec


def render_md(rec: dict) -> str:
    lines = ["# Proposal / SOW — DRAFT", "",
             "**Client:** %s" % rec.get("client", ""), "",
             "## Scope"] + ["- %s" % s for s in rec.get("scope", [])]
    lines += ["", "## Deliverables"] + ["- %s" % d for d in rec.get("deliverables", [])]
    lines += ["", "**Timeline:** %s" % rec.get("timeline", ""),
              "", "**Price (recommendation, not a commitment):** $%s" % rec.get("price_recommendation", 0),
              "", "_Sending this proposal and signing any contract are human actions._"]
    return "\n".join(lines) + "\n"
