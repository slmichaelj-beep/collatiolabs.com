"""revenue.truth — the revenue-truth ledger. Honesty about money, enforced.

Separates the funnel into honest stages and refuses to conflate them: outreach_drafted →
outreach_sent → reply → meeting → proposal_sent → invoice_sent → cash_collected → gross_profit →
net_profit → repeat_purchase. Pipeline is never counted as revenue; a forecast is labeled an
assumption; an invoice is not cash; cash requires payment evidence; profit requires a cost model.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

STAGES = ("outreach_drafted", "outreach_sent", "reply", "meeting_booked", "proposal_sent",
          "invoice_sent", "cash_collected", "gross_profit", "net_profit", "repeat_purchase")
_REVENUE_STAGES = ("cash_collected",)   # only collected cash counts as revenue


def record_event(name: str, *, offer_id: str, stage: str, amount: float = 0.0,
                 payment_evidence_ref: str = "", cost_model_ref: str = "", store: Path | None = None) -> dict:
    """Record a funnel event. cash_collected requires payment evidence; gross/net_profit require a
    cost model. Otherwise the amount is recorded but NOT counted as revenue."""
    if stage not in STAGES:
        return {"ok": False, "error": "unknown stage %r" % stage}
    if stage == "cash_collected" and not (payment_evidence_ref or "").strip():
        return {"ok": False, "error": "cash_collected requires payment evidence — not counted"}
    if stage in ("gross_profit", "net_profit") and not (cost_model_ref or "").strip():
        return {"ok": False, "error": "profit requires a cost model — not counted"}
    rec = {"event_id": "rte_" + uuid.uuid4().hex[:10], "offer_id": offer_id, "stage": stage,
           "amount": amount, "counts_as_revenue": stage in _REVENUE_STAGES,
           "counts_as_pipeline": stage in ("proposal_sent", "invoice_sent"),
           "is_forecast": False, "payment_evidence_ref": payment_evidence_ref or None,
           "cost_model_ref": cost_model_ref or None, "at": storage.now()}
    a = storage.load(name, "rev_truth", store, default={"events": []})
    a["events"].append(rec); storage.save(name, "rev_truth", a, store)
    storage.emit_truth(name, "rev_truth", rec["event_id"], "REVENUE %s $%s%s" %
                       (stage, amount, "" if rec["counts_as_revenue"] else " (NOT revenue)"),
                       actor="user", store=store)
    return {"ok": True, "event": rec}


def board(name: str, store: Path | None = None) -> dict:
    a = storage.load(name, "rev_truth", store, default={"events": []})["events"]
    def total(stages): return round(sum(e["amount"] for e in a if e["stage"] in stages), 2)
    collected = total(("cash_collected",))
    pipeline = total(("proposal_sent", "invoice_sent"))
    return {
        "ok": True,
        "by_stage": {s: sum(1 for e in a if e["stage"] == s) for s in STAGES
                     if any(e["stage"] == s for e in a)},
        "outreach_sent": sum(1 for e in a if e["stage"] == "outreach_sent"),
        "pipeline_value_forecast": pipeline,
        "invoiced_not_yet_cash": total(("invoice_sent",)),
        "cash_collected": collected,
        "gross_profit": total(("gross_profit",)),
        "net_profit": total(("net_profit",)),
        "honesty": "pipeline/forecast/invoice are NOT revenue; only collected cash (with evidence) "
                   "is revenue; profit requires a cost model.",
    }
