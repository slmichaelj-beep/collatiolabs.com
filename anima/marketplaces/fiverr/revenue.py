"""marketplaces.fiverr.revenue — payout-true revenue + learning loop + owned-channel router.

Fiverr money is honest: a placed order is NOT cash until payout evidence; gross is not net (platform
fee); net platform revenue is not profit (fulfillment cost); a refund/cancellation reverses it. The
learning loop turns gig signals into recommendations. The owned-channel router lets a PROVEN gig feed
an owned offer concept — but never by circumventing Fiverr's payment/communication rules for
Fiverr-originated orders; owned expansion must use a separate, compliant acquisition channel.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

PAYOUT = ("pending", "available", "paid_out", "cancelled", "refunded")
SIGNALS = ("impression", "click", "inquiry", "order", "revision", "cancellation", "review", "repeat_buyer")
ACTIONS = ("revise_gig", "raise_price", "lower_scope", "pause", "scale", "productize", "move_to_direct_offer")


def record_revenue(name: str, *, order_id: str, gross_order_amount: float, payout_status: str = "pending",
                   direct_fulfillment_cost: float = 0.0, payout_evidence_ref: str = "",
                   store: Path | None = None) -> dict:
    """Record Fiverr order revenue honestly. cash_received is true ONLY with payout evidence AND a
    paid_out/available status. Refund/cancellation zeroes recognized revenue."""
    if payout_status not in PAYOUT:
        return {"ok": False, "error": "bad payout status %r" % payout_status}
    fee = round(gross_order_amount * 0.20, 2)
    net_platform = round(gross_order_amount - fee, 2)
    reversed_ = payout_status in ("cancelled", "refunded")
    cash = payout_status in ("available", "paid_out") and bool((payout_evidence_ref or "").strip()) and not reversed_
    net_profit = round((net_platform - direct_fulfillment_cost) if cash else 0.0, 2)
    rec = {"fiverr_revenue_id": "frev_" + uuid.uuid4().hex[:10], "order_id": order_id,
           "gross_order_amount": gross_order_amount, "platform_fee_estimate": fee,
           "net_platform_revenue_estimate": net_platform, "payout_status": payout_status,
           "direct_fulfillment_cost": direct_fulfillment_cost,
           "net_profit_estimate": net_profit, "cash_received": cash,
           "payout_evidence_ref": payout_evidence_ref or None,
           "reversed": reversed_, "evidence_refs": []}
    storage.save(name, "fiverr_rev_%s" % order_id, rec, store)
    _idx(name, "fiverr_rev_index", order_id, store)
    storage.emit_truth(name, "fiverr_rev", rec["fiverr_revenue_id"],
                       "FIVERR REV order=%s cash=%s" % (order_id, cash), actor="user", store=store)
    return {"ok": True, "revenue": rec}


def revenue_board(name: str, store: Path | None = None) -> dict:
    idx = storage.load(name, "fiverr_rev_index", store, default={"ids": []})["ids"]
    recs = [r for r in (storage.load(name, "fiverr_rev_%s" % i, store, default=None) for i in idx) if r]
    cash = round(sum(r["net_profit_estimate"] for r in recs if r["cash_received"]), 2)
    pending = round(sum(r["net_platform_revenue_estimate"] for r in recs if r["payout_status"] == "pending"), 2)
    return {"ok": True, "orders": len(recs), "cash_collected_net_profit": cash,
            "pending_not_yet_cash": pending,
            "honesty": "an order is not cash until payout evidence; gross≠net≠profit; refunds reverse it."}


def learn(name: str, *, gig_id: str, signal_type: str, lesson: str, recommended_action: str,
          confidence: str = "low", store: Path | None = None) -> dict:
    if signal_type not in SIGNALS:
        return {"ok": False, "error": "unknown signal %r" % signal_type}
    if recommended_action not in ACTIONS:
        return {"ok": False, "error": "unknown action %r" % recommended_action}
    rec = {"learning_id": "flrn_" + uuid.uuid4().hex[:10], "gig_id": gig_id, "signal_type": signal_type,
           "lesson": lesson, "confidence": confidence, "recommended_action": recommended_action,
           "evidence_refs": []}
    storage.save(name, "fiverr_learn_%s" % rec["learning_id"], rec, store)
    return {"ok": True, "learning": rec}


def route_to_owned(name: str, *, gig_id: str, demand_proven: bool, owned_offer_concept: str,
                   separate_acquisition_channel: str = "", store: Path | None = None) -> dict:
    """Route a proven gig to an owned offer concept. Refused without proven demand or without a
    SEPARATE compliant acquisition channel (never circumvent Fiverr for Fiverr-originated buyers)."""
    if not demand_proven:
        return {"ok": False, "error": "route needs proven Fiverr demand first"}
    if not (separate_acquisition_channel or "").strip():
        return {"ok": False, "error": "owned expansion needs a SEPARATE acquisition channel — no Fiverr circumvention"}
    rec = {"route_id": "froute_" + uuid.uuid4().hex[:10], "gig_id": gig_id,
           "owned_offer_concept": owned_offer_concept, "separate_acquisition_channel": separate_acquisition_channel,
           "circumvention": False, "productization_candidate": True,
           "note": "do NOT move Fiverr-originated orders/relationships off-platform; acquire new buyers compliantly"}
    storage.save(name, "fiverr_route_%s" % gig_id, rec, store)
    return {"ok": True, "route": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)
