"""sales_mastery.pipeline — pipeline command center + learning loop + revenue accountability + safety.

Vera owns sales STATE and is measured by REVENUE, not activity. The pipeline distinguishes
activity / pipeline / closed revenue (no fake progress); the learning loop routes durable policy
changes through Teaching Mode (no silent mutation); the safety policy blocks spam/deception/
unapproved promises.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage

STAGES = ("new", "qualified", "outreach_pending_approval", "contacted", "meeting_booked",
          "demo_completed", "proposal_sent", "negotiation", "closed_won", "closed_lost", "nurture")
_DECEPTION = re.compile(r"\b(?:fake (?:testimonial|customer|case study|review)|"
                        r"impersonat|fake scarcity|fake urgency|unsubscribe ignored)\b", re.I)


# ---- pipeline -------------------------------------------------------------------------------
def add_opportunity(name, lead_id, *, value=0.0, stage="new", store: Path | None = None) -> dict:
    rec = {"opportunity_id": "opp_" + uuid.uuid4().hex[:12], "lead_id": lead_id,
           "value": float(value), "stage": stage if stage in STAGES else "new",
           "touches": 0, "created_at": storage.now(), "updated_at": storage.now()}
    opps = storage.load(name, "sales_pipeline", store, default={"opps": []})["opps"]
    opps.append(rec)
    storage.save(name, "sales_pipeline", {"opps": opps}, store)
    return {"ok": True, "opportunity": rec}


def advance(name, opportunity_id, stage, *, win_loss_reason="", store: Path | None = None) -> dict:
    opps = storage.load(name, "sales_pipeline", store, default={"opps": []})["opps"]
    rec = next((o for o in opps if o["opportunity_id"] == opportunity_id), None)
    if rec is None:
        return {"ok": False, "error": "no such opportunity"}
    if stage in ("closed_won", "closed_lost") and not win_loss_reason:
        return {"ok": False, "error": "closing requires a win/loss reason (evidence)"}
    rec["stage"] = stage if stage in STAGES else rec["stage"]
    rec["updated_at"] = storage.now()
    if win_loss_reason:
        rec["win_loss_reason"] = win_loss_reason
    storage.save(name, "sales_pipeline", {"opps": opps}, store)
    return {"ok": True, "opportunity": rec}


def briefing(name, store: Path | None = None) -> dict:
    opps = storage.load(name, "sales_pipeline", store, default={"opps": []})["opps"]
    by_stage = {}
    for o in opps:
        by_stage.setdefault(o["stage"], []).append(o["opportunity_id"])
    pipeline_value = sum(o["value"] for o in opps if o["stage"] not in ("closed_lost", "closed_won"))
    closed_won_value = sum(o["value"] for o in opps if o["stage"] == "closed_won")
    return {"ok": True, "by_stage": by_stage, "pipeline_value": pipeline_value,
            "closed_revenue": closed_won_value,
            "forecast_note": "pipeline_value is a forecast (assumption), NOT revenue",
            "approvals_needed": by_stage.get("outreach_pending_approval", [])}


# ---- revenue accountability ------------------------------------------------------------------
def revenue_truth(name, store: Path | None = None) -> dict:
    """Distinguish activity / pipeline / closed revenue — never count one as another."""
    b = briefing(name, store)
    opps = storage.load(name, "sales_pipeline", store, default={"opps": []})["opps"]
    return {"ok": True,
            "activity": {"opportunities": len(opps), "touches": sum(o.get("touches", 0) for o in opps)},
            "pipeline_value_forecast": b["pipeline_value"],
            "closed_revenue": b["closed_revenue"],
            "rule": "activity != pipeline != closed revenue; forecasts are labeled assumptions"}


# ---- learning loop --------------------------------------------------------------------------
def record_outcome(name, opportunity_id, *, outcome, message_id="", reason="",
                   store: Path | None = None) -> dict:
    rec = {"opportunity_id": opportunity_id, "outcome": outcome, "message_id": message_id,
           "reason": reason, "at": storage.now()}
    log = storage.load(name, "sales_learning", store, default={"outcomes": []})["outcomes"]
    log.append(rec)
    storage.save(name, "sales_learning", {"outcomes": log}, store)
    storage.emit_truth(name, "sales", opportunity_id, "SALES outcome: %s (%s)" % (outcome, reason),
                       actor="vera", store=store)
    return {"ok": True, "outcome": rec}


def propose_policy_change(name, change_text, *, store: Path | None = None) -> dict:
    """A durable sales-policy change is NOT applied silently — it becomes a Teaching draft."""
    try:
        from anima.teaching import queue as tq, schema as tsch
        draft = tsch.make("behavior_rule", "sales policy: " + change_text, source="conversation",
                          scope="behavior", risk="low", target_store="behavior_policy")
        tq.propose(name, draft, store=store)
        return {"ok": True, "teaching_draft": draft["teaching_id"],
                "note": "policy change queued as a Teaching draft — needs approval, never silent"}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


# ---- safety policy --------------------------------------------------------------------------
def screen(name, text, *, is_roi_claim=False, has_proof=False, store: Path | None = None) -> dict:
    low = (text or "").lower()
    if _DECEPTION.search(low):
        return {"allowed": False, "reason": "blocked: deception / fake-proof / opt-out violation"}
    if is_roi_claim and not has_proof:
        return {"allowed": False, "reason": "blocked: ROI claim without a proof point"}
    return {"allowed": True}
