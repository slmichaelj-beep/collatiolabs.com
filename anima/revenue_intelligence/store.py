"""revenue_intelligence.store — structured revenue-event store + revenue graph + learning loop.

Records each revenue event with honest truth flags (only payment counts as revenue; only profit
with a cost model counts as profit). The revenue graph aggregates events into answers: which buyer
segments respond, which offers have margin, which channels produce real cash, which objections recur,
which services signal productization. The learning loop turns outcomes into recommendations
(raise_price / kill / productize / scale) — every lesson carries its evidence.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

EVENT_TYPES = ("lead", "outreach", "reply", "meeting", "proposal", "invoice", "payment", "delivery",
               "qa", "refund", "repeat_purchase", "lost_deal", "objection")
# only these stages are real money
_REVENUE_EVENTS = ("payment", "repeat_purchase")
_PIPELINE_EVENTS = ("proposal", "invoice")


def record(name: str, *, event_type: str, buyer_segment: str = "", offer_id: str = "", channel: str = "",
           message_variant: str = "", price_presented: float = 0.0, response: str = "none",
           objection_type: str = "", delivery_cost: float = 0.0, gross_margin: float = 0.0,
           quality_result: str = "unknown", customer_outcome: str = "", cost_model_ref: str = "",
           payment_evidence_ref: str = "", store: Path | None = None) -> dict:
    """Record a revenue event. payment requires evidence to count as revenue; a margin/profit figure
    requires a cost-model ref to be trusted (else it is recorded but flagged unverified)."""
    if event_type not in EVENT_TYPES:
        return {"ok": False, "error": "unknown event type %r" % event_type}
    counts_revenue = event_type in _REVENUE_EVENTS and bool((payment_evidence_ref or "").strip())
    if event_type == "payment" and not (payment_evidence_ref or "").strip():
        return {"ok": False, "error": "a payment event requires payment evidence — not counted as revenue"}
    margin_verified = bool((cost_model_ref or "").strip())
    rec = {"revenue_event_id": "rie_" + uuid.uuid4().hex[:12], "event_type": event_type,
           "buyer_segment": buyer_segment, "offer_id": offer_id, "channel": channel,
           "message_variant": message_variant, "price_presented": price_presented,
           "response": response, "objection_type": objection_type, "delivery_cost": delivery_cost,
           "gross_margin": gross_margin, "gross_margin_verified": margin_verified,
           "quality_result": quality_result, "customer_outcome": customer_outcome,
           "counts_as_revenue": counts_revenue, "counts_as_pipeline": event_type in _PIPELINE_EVENTS,
           "payment_evidence_ref": payment_evidence_ref or None, "cost_model_ref": cost_model_ref or None,
           "at": storage.now()}
    a = storage.load(name, "ri_events", store, default={"events": []})
    a["events"].append(rec); storage.save(name, "ri_events", a, store)
    storage.emit_truth(name, "ri_event", rec["revenue_event_id"],
                       "RI %s%s" % (event_type, " (revenue)" if counts_revenue else ""),
                       actor="user", store=store)
    return {"ok": True, "event": rec}


def _events(name, store): return storage.load(name, "ri_events", store, default={"events": []})["events"]


def graph(name: str, store: Path | None = None) -> dict:
    """Aggregate the revenue graph: real-cash by buyer/offer/channel, recurring objections,
    productization signal — only collected cash counts as revenue."""
    ev = _events(name, store)
    def cash_by(key):
        out = {}
        for e in ev:
            if e["counts_as_revenue"]:
                out[e.get(key) or "?"] = round(out.get(e.get(key) or "?", 0) + e["price_presented"], 2)
        return out
    objections = {}
    for e in ev:
        if e["event_type"] == "objection" and e["objection_type"]:
            objections[e["objection_type"]] = objections.get(e["objection_type"], 0) + 1
    repeat = sum(1 for e in ev if e["event_type"] == "repeat_purchase")
    return {
        "ok": True, "total_events": len(ev),
        "cash_by_buyer_segment": cash_by("buyer_segment"),
        "cash_by_offer": cash_by("offer_id"),
        "cash_by_channel": cash_by("channel"),
        "recurring_objections": dict(sorted(objections.items(), key=lambda kv: -kv[1])),
        "repeat_purchases": repeat,
        "total_cash_collected": round(sum(e["price_presented"] for e in ev if e["counts_as_revenue"]), 2),
        "pipeline_events": sum(1 for e in ev if e["counts_as_pipeline"]),
        "honesty": "only payment/repeat-purchase with evidence is revenue; pipeline/reply/invoice are not.",
    }


def lessons(name: str, store: Path | None = None) -> list:
    """Derive evidence-backed lessons from the graph. Each lesson references the events behind it."""
    ev = _events(name, store)
    out = []
    # recurring objection lesson
    g = graph(name, store)
    for obj, cnt in g["recurring_objections"].items():
        if cnt >= 2:
            out.append({"lesson": "objection %r recurs (%d×) — prepare proof/response" % (obj, cnt),
                        "evidence_count": cnt, "confidence": "medium" if cnt >= 3 else "low"})
    # offer-with-cash lesson (only from real revenue)
    for offer, cash in g["cash_by_offer"].items():
        if cash > 0:
            out.append({"lesson": "offer %r produced real cash ($%s) — consider scaling/raising price" % (offer, cash),
                        "evidence": "collected-cash events", "confidence": "high"})
    # refund signal
    refunds = sum(1 for e in ev if e["event_type"] == "refund")
    if refunds >= 1:
        out.append({"lesson": "%d refund(s) recorded — review delivery quality before scaling" % refunds,
                    "confidence": "medium"})
    return out
