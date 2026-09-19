"""agency_suggest — Wave 2 Alpha: Vera may SUGGEST, never EXECUTE.

A suggestion is a *proposal object*. It carries its reason, evidence, risk, and action type, and it is
born with ``execution_allowed=False`` and ``requires_approval=True``. Creating a suggestion changes
NOTHING in the world — no mail, no write, no host action, no identity mutation. Execution is a SEPARATE,
separately-certified wave (Wave 2B); this module cannot execute anything and must never be made to.

Fail-safe: an unknown risk coerces to "high"; an unknown action_type coerces to "draft". The object is
pure data — the approval queue (anima/agency_approval_queue.py) is what persists + audits it.
"""
from __future__ import annotations

import datetime
import uuid

RISK_LEVELS = ("low", "medium", "high")
ACTION_TYPES = ("draft", "organize", "cert", "reminder", "connector", "host", "memory", "identity")
STATUSES = ("proposed", "approved", "rejected", "expired")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def make_suggestion(suggestion: str, reason: str, *, evidence=None,
                    risk: str = "low", action_type: str = "draft") -> dict:
    """Build a suggest-only intent object. NEVER executes; ``execution_allowed`` is always False here.
    The exact schema the founder directive specified, with two fail-safe coercions."""
    risk = risk if risk in RISK_LEVELS else "high"            # unknown risk -> treat as the worst
    action_type = action_type if action_type in ACTION_TYPES else "draft"
    return {
        "intent_id": uuid.uuid4().hex[:12],
        "suggestion": str(suggestion),
        "reason": str(reason),
        "evidence": list(evidence or []),
        "risk": risk,
        "requires_approval": True,
        "action_type": action_type,
        "execution_allowed": False,
        "status": "proposed",
        "created_at": _now(),
    }


def is_executable(obj: dict) -> bool:
    """The ONLY thing that could ever permit execution: a dict that is BOTH approved AND has
    execution_allowed True. In Wave 2 Alpha that combination is never produced (approval never flips
    execution_allowed) — so this returns False for everything the suggest+approve loop creates. A later
    certified execution wave is the only thing allowed to set execution_allowed, behind its own gate."""
    return bool(obj.get("execution_allowed")) and obj.get("status") == "approved"
