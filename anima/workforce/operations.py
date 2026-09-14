"""workforce.operations — margin monitor + capacity planner + reputation + productization + portfolio.

Margin monitor knows which workstreams are actually profitable (scale blocked if margin unknown).
Capacity planner surfaces bottlenecks (over-capacity selling is blocked/warned). Reputation tracks
quality (bad quality blocks scale; testimonials need permission). The productization engine turns a
repeated, high-QA workflow into a software hypothesis (build needs repeated-workflow evidence). The
portfolio + chairman briefing distinguish activity / pipeline / recognized revenue.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import execution as _ex, fulfillment as _ff, discovery as _disc


def margin_report(name: str, service_id: str, *, period: str = "current", store: Path | None = None) -> dict:
    """Compute a margin report from real work orders. Recommends scale/hold/fix/raise_price/automate/
    kill. Scale is blocked if there's no completed/recognized data."""
    orders = [o for o in _ex.list_orders(name, store) if o["service_id"] == service_id]
    done = [o for o in orders if o.get("revenue_recognition_status") == "recognized"]
    refunds = [o for o in orders if o.get("revenue_recognition_status") == "refunded"]
    revenue = sum(o["price"] for o in done)
    cost = sum(o.get("cost_estimate", 0) for o in done)
    gross = revenue - cost
    refund_rate = round(len(refunds) / len(orders), 3) if orders else 0.0
    if not done:
        rec_action = "hold"; note = "no recognized revenue yet — scale blocked (margin unknown)"
    elif refund_rate > 0.2:
        rec_action = "fix"; note = "refund rate too high"
    elif gross <= 0:
        rec_action = "raise_price"; note = "gross margin non-positive"
    else:
        rec_action = "scale"; note = "profitable with acceptable refunds"
    rec = {"margin_report_id": "mr_" + uuid.uuid4().hex[:10], "service_id": service_id, "period": period,
           "units_completed": len(done), "revenue": revenue, "estimated_cost": cost,
           "gross_margin": round(gross, 2), "refund_rate": refund_rate,
           "recommendation": rec_action, "note": note, "margins_are_estimates": True}
    storage.save(name, "wf_margin_%s" % service_id, rec, store)
    return {"ok": True, "margin": rec}


def capacity(name: str, service_id: str, *, tasks_per_day: int, committed_per_day: int,
             human_review_bottleneck: bool = False, store: Path | None = None) -> dict:
    over = committed_per_day > tasks_per_day
    rec = {"capacity_id": "cap_" + uuid.uuid4().hex[:10], "service_id": service_id,
           "tasks_per_day": tasks_per_day, "committed_per_day": committed_per_day,
           "over_capacity": over, "human_review_bottleneck": human_review_bottleneck,
           "selling_status": "BLOCK/warn: over capacity" if over else "ok",
           "can_sell_more": not over}
    storage.save(name, "wf_capacity_%s" % service_id, rec, store)
    return {"ok": True, "capacity": rec}


def reputation(name: str, service_id: str, *, quality_score: float, refund_rate: float,
               complaints: int = 0, store: Path | None = None) -> dict:
    bad = quality_score < 0.7 or refund_rate > 0.2
    rec = {"reputation_id": "rep_" + uuid.uuid4().hex[:10], "service_id": service_id,
           "quality_score": quality_score, "refund_rate": refund_rate, "complaints": complaints,
           "scale_allowed": not bad,
           "note": "bad quality/refunds block scale" if bad else "healthy",
           "testimonial_policy": "permission required; no fabricated testimonials"}
    storage.save(name, "wf_reputation_%s" % service_id, rec, store)
    return {"ok": True, "reputation": rec}


def productize(name: str, service_id: str, *, repeatable_steps: list, automation_candidates: list,
               software_hypothesis: str, observed_runs: int, store: Path | None = None) -> dict:
    """Recommend productizing a repeated service. A build recommendation requires evidence of a
    repeated workflow (>= a few runs); otherwise it's watch/prototype only."""
    if not repeatable_steps:
        return {"ok": False, "error": "no repeatable steps identified — nothing to productize"}
    if observed_runs >= 5 and automation_candidates:
        step = "build_internal_tool"
    elif observed_runs >= 2:
        step = "prototype"
    else:
        step = "watch"
    rec = {"productization_id": "prod_" + uuid.uuid4().hex[:10], "service_id": service_id,
           "repeatable_steps": list(repeatable_steps), "automation_candidates": list(automation_candidates),
           "software_product_hypothesis": software_hypothesis, "observed_runs": observed_runs,
           "recommended_next_step": step,
           "evidence_note": "build recommendation requires repeated-workflow evidence (>=5 runs)"}
    storage.save(name, "wf_productize_%s" % service_id, rec, store)
    return {"ok": True, "productization": rec}


def portfolio(name: str, store: Path | None = None) -> dict:
    gaps = _disc.list_gaps(name, store)
    services = _ff.list_services(name, store)
    orders = _ex.list_orders(name, store)
    recognized = [o for o in orders if o.get("revenue_recognition_status") == "recognized"]
    return {
        "ok": True, "work_gaps": len(gaps), "services": len(services),
        "selling": [s["name"] for s in services if s["status"] == "selling"],
        "work_orders": len(orders),
        "activity": {"orders": len(orders), "delivered": sum(1 for o in orders if o["status"] in ("delivered", "accepted"))},
        "recognized_revenue": sum(o["price"] for o in recognized),
        "honesty": "orders/deliveries are activity; only payment+acceptance counts as recognized revenue.",
    }


def chairman_briefing(name: str, store: Path | None = None) -> dict:
    gaps = _disc.list_gaps(name, store)
    pf = portfolio(name, store)
    by_band = {}
    for g in gaps:
        by_band.setdefault(g.get("ticket_size_estimate", "unknown"), []).append(g["title"])
    return {
        "ok": True, "new_gaps": len(gaps), "by_band": by_band,
        "services_selling": pf["selling"], "activity": pf["activity"],
        "recognized_revenue": pf["recognized_revenue"],
        "next_move": ("scan work gaps from approved sources" if not gaps else
                      "prove unit economics + design fulfillment for the top gap" if not pf["services"]
                      else "approve a service + run a governed first work order"),
        "honesty": pf["honesty"],
    }
