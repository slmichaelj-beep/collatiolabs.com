"""revenue.milestone — the $16,000-net-profit cash-strike tracker (governed, honest).

Target: $16,000 NET profit by 2026-06-28 from a $1,000 budget, via high-ticket AI-enabled services
sold under Collatio Labs LLC. This module tracks the milestone HONESTLY:

  net_profit = collected_cash - direct_fulfillment_cost - approved_spend

Pipeline / replies / meetings / invoices are NOT cash; only collected cash with payment evidence
counts. Vera prepares offers, buyer lists, and outreach drafts and tracks progress — it never sends
outreach, never spends, never collects payment, never makes a customer commitment. Those are
human-only. If no payment path exists, the milestone is BLOCKED and that is surfaced, not hidden.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from anima.company import storage

TARGET_NET = 16000.0
DEADLINE = "2026-06-28"
START_BUDGET = 1000.0
START_DATE = "2026-06-10"

# the three milestone offers (high-ticket, fast-deliverable, AI-enabled services)
OFFERS = [
    {"offer_id": "mo_ai_revenue_audit", "name": "AI Revenue + Workflow Audit",
     "buyer": "founders / operators / agencies / SMBs", "price": 2500,
     "deliverable": "workflow map + revenue-opportunity report + prioritized implementation roadmap",
     "timeline": "5 business days", "upsell": "Implementation Sprint $5,000–$10,000",
     "limitation": "advisory + planning; revenue estimates are assumptions, not guarantees; "
                   "legal/tax/financial/regulated advice excluded unless professionally reviewed",
     "lead": True},
    {"offer_id": "mo_website_teardown", "name": "Website + Product Revenue Teardown",
     "buyer": "businesses with weak conversion", "price": 2500,
     "deliverable": "teardown + top-10 revenue fixes + landing/sales rewrite draft",
     "timeline": "5 business days", "upsell": "Implementation Sprint $5,000–$10,000",
     "limitation": "advisory; no revenue guarantee", "lead": False},
    {"offer_id": "mo_workforce_sprint", "name": "Digital Workforce Setup Sprint",
     "buyer": "operators adopting AI", "price": 5000,
     "deliverable": "digital-team map + AI/human role design + first 3 automations + roadmap",
     "timeline": "1–2 weeks", "upsell": "Done-with-you Build $10,000–$25,000",
     "limitation": "advisory + setup; no revenue guarantee", "lead": False},
]


def seed_offers(name: str, *, store: Path | None = None) -> dict:
    storage.save(name, "milestone_offers", {"offers": OFFERS}, store)
    return {"ok": True, "offers": OFFERS}


def offers(name: str, store: Path | None = None) -> list:
    return storage.load(name, "milestone_offers", store, default={"offers": OFFERS})["offers"]


# ---- payment path readiness (human-only to register) ----
def payment_path_status(name: str, store: Path | None = None) -> dict:
    rec = storage.load(name, "milestone_payment_path", store, default=None)
    if not rec:
        return {"exists": False, "blocking": True,
                "message": "No payment/invoice path exists. Vera cannot collect cash. Lamar must "
                           "approve or create one (Stripe invoice, bank, etc.) — a human-only action."}
    return {"exists": True, "blocking": False, "kind": rec["kind"], "approved_by": rec["approval_ref"]}


def register_payment_path(name: str, *, kind: str, approval_ref: str = "", store: Path | None = None) -> dict:
    """Register a payment path — REQUIRES human approval. Vera never creates a financial account itself."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "a payment path is a financial/account action — needs human approval"}
    rec = {"kind": kind, "approval_ref": approval_ref, "registered_at": storage.now()}
    storage.save(name, "milestone_payment_path", rec, store)
    storage.emit_truth(name, "milestone_payment", "path", "PAYMENT PATH registered (human): " + kind,
                       actor=approval_ref, store=store)
    return {"ok": True, "payment_path": rec}


# ---- cash / cost / spend ledgers (net-profit truth) ----
def record_cash(name: str, *, offer_id: str, amount: float, payment_evidence_ref: str = "",
                store: Path | None = None) -> dict:
    """Record collected cash. REFUSED without payment evidence and without a registered payment path
    (you cannot have collected cash with no way to collect it)."""
    if not (payment_evidence_ref or "").strip():
        return {"ok": False, "error": "collected cash requires payment evidence — not counted"}
    if not payment_path_status(name, store)["exists"]:
        return {"ok": False, "error": "no payment path registered — cannot record collected cash"}
    rec = {"id": "mc_" + uuid.uuid4().hex[:10], "offer_id": offer_id, "amount": float(amount),
           "payment_evidence_ref": payment_evidence_ref, "at": storage.now()}
    a = storage.load(name, "milestone_cash", store, default={"items": []})
    a["items"].append(rec); storage.save(name, "milestone_cash", a, store)
    storage.emit_truth(name, "milestone_cash", rec["id"], "CASH COLLECTED $%s (%s)" % (amount, offer_id),
                       actor="user", store=store)
    return {"ok": True, "cash": rec}


def record_cost(name: str, *, amount: float, note: str = "", store: Path | None = None) -> dict:
    rec = {"id": "cost_" + uuid.uuid4().hex[:8], "amount": float(amount), "note": note, "at": storage.now()}
    a = storage.load(name, "milestone_costs", store, default={"items": []})
    a["items"].append(rec); storage.save(name, "milestone_costs", a, store)
    return {"ok": True, "cost": rec}


def record_spend(name: str, *, amount: float, note: str = "", approval_ref: str = "",
                 store: Path | None = None) -> dict:
    """Record approved budget spend. REFUSED without approval; refused if it would exceed the budget."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "spend requires approval"}
    spent = sum(i["amount"] for i in storage.load(name, "milestone_spend", store, default={"items": []})["items"])
    if spent + amount > START_BUDGET:
        return {"ok": False, "error": "spend would exceed the $%.0f budget" % START_BUDGET}
    rec = {"id": "spend_" + uuid.uuid4().hex[:8], "amount": float(amount), "note": note,
           "approval_ref": approval_ref, "at": storage.now()}
    a = storage.load(name, "milestone_spend", store, default={"items": []})
    a["items"].append(rec); storage.save(name, "milestone_spend", a, store)
    return {"ok": True, "spend": rec}


def _sum(name, kind, store):
    return round(sum(i["amount"] for i in storage.load(name, kind, store, default={"items": []})["items"]), 2)


def _days_left(today: str) -> int:
    try:
        y1, m1, d1 = (int(x) for x in DEADLINE.split("-"))
        y0, m0, d0 = (int(x) for x in today.split("-"))
        return max(0, (date(y1, m1, d1) - date(y0, m0, d0)).days)
    except Exception:
        return 0


def board(name: str, *, today: str | None = None, store: Path | None = None) -> dict:
    """The milestone board: target, deadline, collected cash, costs, spend, NET PROFIT, gap, days
    left, required daily pace, payment-path status, and blockers — all honest."""
    today = today or storage.now()[:10]
    collected = _sum(name, "milestone_cash", store)
    costs = _sum(name, "milestone_costs", store)
    spend = _sum(name, "milestone_spend", store)
    net = round(collected - costs - spend, 2)
    gap = round(TARGET_NET - net, 2)
    days = _days_left(today)
    pay = payment_path_status(name, store)
    blockers = []
    if pay["blocking"]:
        blockers.append("NO PAYMENT PATH — cannot collect cash (needs Lamar approval)")
    # outreach is human-approved; we don't auto-send, so flag that selling is human-gated
    blockers.append("outreach/proposals/invoices are human-approved actions — Vera prepares, Lamar sends")
    return {
        "ok": True, "target_net_profit": TARGET_NET, "deadline": DEADLINE, "today": today,
        "starting_budget": START_BUDGET, "collected_cash": collected, "direct_costs": costs,
        "approved_spend": spend, "net_profit": net, "remaining_gap": gap, "days_left": days,
        "required_net_per_day": round(gap / days, 2) if days > 0 and gap > 0 else 0.0,
        "payment_path": pay,
        "status": ("MILESTONE MET" if net >= TARGET_NET else
                   "BLOCKED — no payment path" if pay["blocking"] else "in progress"),
        "blockers": blockers,
        "honesty": "net profit = collected cash − direct cost − approved spend; pipeline/invoices are "
                   "not cash; Vera never sends/spends/collects — those are human-only.",
    }


def daily_briefing(name: str, *, today: str | None = None, store: Path | None = None) -> dict:
    b = board(name, today=today, store=store)
    return {
        "ok": True, "date": b["today"],
        "cash_collected": b["collected_cash"], "net_profit": b["net_profit"],
        "remaining_gap": b["remaining_gap"], "days_left": b["days_left"],
        "required_net_per_day": b["required_net_per_day"],
        "approvals_needed_today": ([
            "approve/create a payment path"] if b["payment_path"]["blocking"] else []) + [
            "approve the first outreach batch (drafts ready, none sent)"],
        "resource_blockers": b["blockers"],
        "next_actions": ["package the lead offer", "build a 25-buyer approved shortlist",
                         "prepare the first outreach batch for Lamar's approval"],
        "honesty": b["honesty"],
    }


def resource_request(name: str, *, resource_needed: str, why_needed: str, milestone_impact: str,
                     cost: str, minimum_option: str, recommended_option: str,
                     risk_if_not_provided: str, store: Path | None = None) -> dict:
    """A milestone-tied resource request. Refused if it doesn't state milestone impact + a cost +
    options. Always approval-gated."""
    if not (milestone_impact or "").strip():
        return {"ok": False, "error": "a resource request must tie to the $16k milestone"}
    if not (minimum_option and recommended_option):
        return {"ok": False, "error": "a resource request needs minimum + recommended options"}
    rec = {"resource_request_id": "mrr_" + uuid.uuid4().hex[:10], "resource_needed": resource_needed,
           "why_needed": why_needed, "milestone_impact": milestone_impact, "cost": cost,
           "minimum_option": minimum_option, "recommended_option": recommended_option,
           "risk_if_not_provided": risk_if_not_provided, "deadline": DEADLINE,
           "approval_required": True, "status": "ready_for_lamar"}
    storage.save(name, "milestone_resource_%s" % rec["resource_request_id"], rec, store)
    storage.emit_truth(name, "milestone_resource", rec["resource_request_id"],
                       "RESOURCE REQUEST: " + resource_needed, actor="vera", store=store)
    return {"ok": True, "request": rec}


def standing_resource_requests(name: str, store: Path | None = None) -> list:
    """The known blockers Vera must surface for this milestone (honest, even before any cash)."""
    out = []
    if payment_path_status(name, store)["blocking"]:
        out.append({"resource_needed": "payment / invoice path",
                    "why_needed": "without it, no collected cash is possible",
                    "milestone_impact": "blocks 100% of the $16k milestone",
                    "risk_if_not_provided": "milestone cannot start", "approval_required": True})
    out.append({"resource_needed": "approved sender identity (business email) + calendar link",
                "why_needed": "high-ticket buyers need a credible sender + low-friction booking",
                "milestone_impact": "raises reply + call-booking rates",
                "risk_if_not_provided": "lower conversion", "approval_required": True})
    out.append({"resource_needed": "approval to send the first outreach batch",
                "why_needed": "Vera drafts but never sends; nothing reaches a buyer without approval",
                "milestone_impact": "no outreach = no pipeline = no cash",
                "risk_if_not_provided": "milestone stalls at 'drafts ready'", "approval_required": True})
    return out
