"""company_operator.budget — the Budget Ledger. Every spend is governed.

No spend without an approved budget. Category caps, per-transaction caps, and an
approval-required-above threshold are all enforced here. Exhaustion blocks further spend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from anima.company import storage

STATUS = ("draft", "approved", "paused", "exhausted", "closed")


def get(name: str, store: Path | None = None) -> dict:
    return storage.load(name, "budget", store, default={
        "total_approved": 0.0, "monthly_cap": 0.0, "category_caps": {},
        "per_transaction_cap": 0.0, "approval_required_above": 0.0,
        "forbidden_categories": [], "vendor_whitelist": [],
        "spent": 0.0, "committed": 0.0, "status": "draft", "ledger": []})


def approve_budget(name: str, *, total: float, monthly_cap: float = 0.0, category_caps=None,
                   per_transaction_cap: float = 0.0, approval_required_above: float = 0.0,
                   forbidden_categories=None, vendor_whitelist=None, by: str = "founder",
                   store: Path | None = None) -> dict:
    b = get(name, store)
    b.update({"total_approved": float(total), "monthly_cap": float(monthly_cap),
              "category_caps": category_caps or {}, "per_transaction_cap": float(per_transaction_cap),
              "approval_required_above": float(approval_required_above),
              "forbidden_categories": forbidden_categories or [],
              "vendor_whitelist": vendor_whitelist or [], "status": "approved"})
    storage.save(name, "budget", b, store)
    storage.emit_truth(name, "budget", "approve", "BUDGET approved: $%.2f total by %s" % (total, by),
                       actor="user", risk="high", store=store)
    return {"ok": True, "budget": b}


def remaining(name: str, store: Path | None = None) -> float:
    b = get(name, store)
    return _remaining_from_budget(b)


def _remaining_from_budget(b: dict) -> float:
    return max(0.0, float(b["total_approved"]) - float(b["spent"]) - float(b["committed"]))


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _ledger_amount(entry: dict) -> float:
    try:
        return float(entry.get("amount") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _category_spent(b: dict, category: str) -> float:
    return sum(_ledger_amount(x) for x in b.get("ledger", []) if x.get("category") == category)


def _month_spent(b: dict, month: str | None = None) -> float:
    month = month or _current_month()
    total = 0.0
    for entry in b.get("ledger", []):
        at = str(entry.get("at") or "")
        if not at or at[:7] == month:
            total += _ledger_amount(entry)
    return total


def can_spend(name: str, amount: float, *, category: str = "", vendor: str = "",
              store: Path | None = None) -> dict:
    """The spend verdict. needs_approval=True means: allowed by budget but over the
    approval-required threshold, so it must also clear the approval queue."""
    b = get(name, store)
    amount = float(amount)
    if amount <= 0:
        return {"allowed": False, "reason": "spend amount must be positive"}
    if b["status"] != "approved":
        return {"allowed": False, "reason": "no approved budget — spending is blocked"}
    if category and category in b["forbidden_categories"]:
        return {"allowed": False, "reason": "category %r is forbidden" % category}
    if vendor and b["vendor_whitelist"] and vendor not in b["vendor_whitelist"]:
        return {"allowed": False, "reason": "vendor %r not on the whitelist" % vendor}
    if b["per_transaction_cap"] and amount > b["per_transaction_cap"]:
        return {"allowed": False, "reason": "exceeds per-transaction cap $%.2f" % b["per_transaction_cap"]}
    cap = b["category_caps"].get(category) if category else None
    if cap is not None and _category_spent(b, category) + amount > float(cap):
        return {"allowed": False,
                "reason": "exceeds category cap for %r ($%.2f cumulative)" % (category, cap)}
    if b["monthly_cap"] and _month_spent(b) + amount > float(b["monthly_cap"]):
        return {"allowed": False,
                "reason": "exceeds monthly cap $%.2f" % float(b["monthly_cap"])}
    if amount > _remaining_from_budget(b):
        return {"allowed": False, "reason": "exceeds remaining budget ($%.2f)" % _remaining_from_budget(b)}
    needs_approval = b["approval_required_above"] and amount > b["approval_required_above"]
    return {"allowed": True, "needs_approval": bool(needs_approval),
            "reason": ("over the approval threshold — also needs approval" if needs_approval
                       else "within budget")}


def record_spend(name: str, amount: float, *, category: str = "", vendor: str = "",
                 description: str = "", approval_ref: str = "", subject: str = "",
                 store: Path | None = None) -> dict:
    amount = float(amount)
    v = can_spend(name, amount, category=category, vendor=vendor, store=store)
    if not v["allowed"]:
        return {"ok": False, "error": v["reason"]}
    if v["needs_approval"] and not approval_ref:
        return {"ok": False, "error": "this spend needs an approval_ref (over the threshold)"}
    if approval_ref:
        from anima.company_operator import approvals
        verdict = approvals.validate_for_action(
            name, approval_ref, "spend", cost=amount, category=category, vendor=vendor,
            subject=subject, store=store,
        )
        if not verdict["ok"]:
            return {"ok": False, "error": "approval rejected: " + verdict["reason"]}
    b = get(name, store)
    b["spent"] += amount
    b["ledger"].append({"amount": amount, "category": category, "vendor": vendor,
                        "description": description, "approval_ref": approval_ref, "subject": subject,
                        "at": storage.now()})
    if _remaining_from_budget(b) <= 0:
        b["status"] = "exhausted"
    storage.save(name, "budget", b, store)
    if approval_ref:
        from anima.company_operator import approvals
        approvals.mark_executed(name, approval_ref, store)
    return {"ok": True, "spent": b["spent"], "remaining": _remaining_from_budget(b)}
