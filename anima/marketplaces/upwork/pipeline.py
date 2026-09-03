"""marketplaces.upwork.pipeline — the bid funnel + Connects ledger + honest revenue truth.

Funnel stages for a bid: drafted → submitted → viewed → replied → interview → awarded → delivered →
paid (or declined/withdrawn). Honest accounting: submitted/replied = activity; awarded = pipeline
value (a forecast, not cash); only `paid` with payment evidence is collected cash. Connects are a
finite resource spent on submit. Every triage records bid/skip + reason so the funnel is auditable.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

STAGES = ("drafted", "submitted", "viewed", "replied", "interview", "awarded", "delivered", "paid",
          "declined", "withdrawn")
_ACTIVITY = ("submitted", "viewed", "replied", "interview")
_PIPELINE = ("awarded", "delivered")
_CASH = ("paid",)
_TERMINAL = ("paid", "declined", "withdrawn")
_ALLOWED_TRANSITIONS = {
    "drafted": {"submitted", "declined", "withdrawn"},
    "submitted": {"viewed", "replied", "interview", "declined", "withdrawn"},
    "viewed": {"replied", "interview", "declined", "withdrawn"},
    "replied": {"interview", "awarded", "declined", "withdrawn"},
    "interview": {"awarded", "declined", "withdrawn"},
    "awarded": {"delivered", "paid", "declined", "withdrawn"},
    "delivered": {"paid"},
}


# ---- job triage log (scanned → bid/skip) ----
def record_triage(name: str, *, job_title: str, verdict: str, reason: str, job_url: str = "",
                  fresh: bool = False, verified: bool = False, proposals: str = "",
                  store: Path | None = None) -> dict:
    """Log a triaged job. verdict in {bid, skip}. Builds the top of the funnel."""
    rec = {"triage_id": "tri_" + uuid.uuid4().hex[:8], "job_title": job_title, "job_url": job_url,
           "verdict": verdict if verdict in ("bid", "skip") else "skip", "reason": reason,
           "fresh": fresh, "verified": verified, "proposals": proposals, "at": storage.now()}
    a = storage.load(name, "uw_triage", store, default={"items": []})
    a["items"].append(rec); storage.save(name, "uw_triage", a, store)
    return {"ok": True, "triage": rec}


# ---- bids ----
def stage_bid(name: str, *, job_title: str, job_url: str = "", bid_amount: float = 0.0,
              connects_cost: int = 0, fit_reason: str = "", client_signals: dict | None = None,
              store: Path | None = None) -> dict:
    if int(connects_cost) < 0:
        return {"ok": False, "error": "connects_cost must be non-negative"}
    rec = {"bid_id": "bid_" + uuid.uuid4().hex[:10], "job_title": job_title, "job_url": job_url,
           "bid_amount": float(bid_amount), "connects_cost": int(connects_cost),
           "fit_reason": fit_reason, "client_signals": client_signals or {},
           "status": "drafted", "status_history": [{"status": "drafted", "at": storage.now()}],
           "paid_evidence_ref": None, "created_at": storage.now()}
    storage.save(name, "uw_bid_%s" % rec["bid_id"], rec, store)
    _idx(name, rec["bid_id"], store)
    storage.emit_truth(name, "uw_bid", rec["bid_id"], "BID staged: " + job_title, actor="vera", store=store)
    return {"ok": True, "bid": rec}


def advance(name: str, bid_id: str, status: str, *, connects_spent: int | None = None,
            paid_evidence_ref: str = "", store: Path | None = None) -> dict:
    """Advance a bid's status. `submitted` records Connects spent; `paid` requires payment evidence
    (no cash without proof)."""
    if status not in STAGES:
        return {"ok": False, "error": "bad status %r" % status}
    rec = storage.load(name, "uw_bid_%s" % bid_id, store, default=None)
    if not rec:
        return {"ok": False, "error": "no such bid"}
    if rec["status"] in _TERMINAL:
        return {"ok": False, "error": "bid is terminal (%s)" % rec["status"]}
    if status == rec["status"]:
        return {"ok": False, "error": "bid is already %s" % status}
    if status not in _ALLOWED_TRANSITIONS.get(rec["status"], set()):
        return {"ok": False, "error": "illegal transition %s -> %s" % (rec["status"], status)}
    if status == "paid" and not (paid_evidence_ref or "").strip():
        return {"ok": False, "error": "paid requires payment evidence — not counted as cash"}
    if status == "submitted" and connects_spent is not None:
        spend = spend_connects(name, amount=int(connects_spent), note="bid: " + rec["job_title"],
                               store=store)
        if not spend["ok"]:
            return {"ok": False, "error": spend["error"]}
        rec["connects_cost"] = int(connects_spent)
    elif status == "submitted" and int(rec.get("connects_cost") or 0) > 0:
        spend = spend_connects(name, amount=int(rec.get("connects_cost") or 0),
                               note="bid: " + rec["job_title"], store=store)
        if not spend["ok"]:
            return {"ok": False, "error": spend["error"]}
    rec["status"] = status
    rec["status_history"].append({"status": status, "at": storage.now()})
    if status == "paid":
        rec["paid_evidence_ref"] = paid_evidence_ref
    storage.save(name, "uw_bid_%s" % bid_id, rec, store)
    storage.emit_truth(name, "uw_bid", bid_id, "BID %s -> %s" % (rec["job_title"][:30], status),
                       actor="user", store=store)
    return {"ok": True, "bid": rec}


def _idx(name, bid_id, store):
    idx = storage.load(name, "uw_bid_index", store, default={"ids": []}); idx["ids"].append(bid_id)
    storage.save(name, "uw_bid_index", idx, store)


def bids(name, store=None) -> list:
    idx = storage.load(name, "uw_bid_index", store, default={"ids": []})["ids"]
    return [b for b in (storage.load(name, "uw_bid_%s" % i, store, default=None) for i in idx) if b]


# ---- connects ledger ----
def set_connects(name: str, *, available: int, store: Path | None = None) -> dict:
    if int(available) < 0:
        return {"ok": False, "error": "available Connects must be non-negative"}
    c = storage.load(name, "uw_connects", store, default={"available": 0, "spent": 0})
    c["available"] = int(available); storage.save(name, "uw_connects", c, store)
    return {"ok": True, "connects": c}


def spend_connects(name: str, *, amount: int, note: str = "", store: Path | None = None) -> dict:
    amount = int(amount)
    if amount <= 0:
        return {"ok": False, "error": "Connects spend amount must be positive"}
    c = storage.load(name, "uw_connects", store, default={"available": 0, "spent": 0})
    if amount > int(c["available"]):
        return {"ok": False,
                "error": "insufficient Connects: need %d, available %d" % (amount, c["available"])}
    c["available"] = int(c["available"]) - amount
    c["spent"] = int(c["spent"]) + amount
    storage.save(name, "uw_connects", c, store)
    return {"ok": True, "connects": c}


# ---- the board ----
def board(name: str, store: Path | None = None) -> dict:
    bs = bids(name, store)
    tri = storage.load(name, "uw_triage", store, default={"items": []})["items"]
    conn = storage.load(name, "uw_connects", store, default={"available": 0, "spent": 0})
    by_stage = {s: sum(1 for b in bs if b["status"] == s) for s in STAGES
                if any(b["status"] == s for b in bs)}
    awarded_value = round(sum(b["bid_amount"] for b in bs if b["status"] in _PIPELINE), 2)
    cash = round(sum(b["bid_amount"] for b in bs if b["status"] in _CASH), 2)
    return {
        "ok": True,
        "funnel": {
            "scanned": len(tri),
            "bid_verdicts": sum(1 for t in tri if t["verdict"] == "bid"),
            "skipped": sum(1 for t in tri if t["verdict"] == "skip"),
            "staged": sum(1 for b in bs if b["status"] == "drafted"),
            "submitted": sum(1 for b in bs if b["status"] not in ("drafted",) and b["status"] not in _TERMINAL) + by_stage.get("declined", 0) + by_stage.get("withdrawn", 0),
        },
        "by_stage": by_stage,
        "active_bids": [{"title": b["job_title"][:48], "amount": b["bid_amount"], "status": b["status"],
                         "connects": b["connects_cost"], "url": b.get("job_url", "")}
                        for b in bs if b["status"] not in ("declined", "withdrawn")],
        "recent_triage": [{"title": t["job_title"][:46], "verdict": t["verdict"], "reason": t["reason"][:70],
                           "fresh": t["fresh"], "verified": t["verified"]} for t in tri[-8:][::-1]],
        "connects": {"available": conn["available"], "spent": conn["spent"]},
        "money": {"activity_bids": sum(1 for b in bs if b["status"] in _ACTIVITY),
                  "pipeline_value_awarded": awarded_value, "collected_cash_paid": cash},
        "honesty": "submitted/replied bids are activity; an awarded contract is pipeline (a forecast); "
                   "only a PAID contract with evidence is collected cash. Vera never submits or sends.",
    }
