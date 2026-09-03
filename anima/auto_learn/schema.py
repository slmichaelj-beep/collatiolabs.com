"""auto_learn.schema — an Auto Learn suggestion. It can NEVER persist; it can only become a
Teaching Mode draft.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

RISKS = ("low", "medium", "high", "sensitive")
SCOPES = ("chat", "project", "long_term", "knowledge_pack")
STATES = ("pending", "converted_to_teaching_draft", "dismissed", "never_ask_again")

REQUIRED = ("auto_learn_id", "proposed_learning", "evidence", "confidence", "risk",
            "scope_recommendation", "status", "created_at")

_ID_RX = re.compile(r"^al_[0-9a-f]{12}$")


def new_id() -> str:
    return "al_" + uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(proposed_learning: str, *, evidence: list | None = None, confidence: float = 0.0,
         risk: str = "low", scope_recommendation: str = "long_term") -> dict:
    rec = {
        "auto_learn_id": new_id(),
        "proposed_learning": str(proposed_learning or "")[:2000],
        "evidence": list(evidence or [])[:40],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "risk": risk,
        "scope_recommendation": scope_recommendation,
        "status": "pending",
        "created_at": now(),
    }
    problems = validate(rec)
    if problems:
        raise ValueError("invalid auto-learn suggestion: " + "; ".join(problems))
    return rec


def validate(rec: dict) -> list[str]:
    p: list[str] = []
    if not isinstance(rec, dict):
        return ["not a dict"]
    for k in REQUIRED:
        if k not in rec:
            p.append("missing %r" % k)
    if p:
        return p
    if not _ID_RX.match(str(rec["auto_learn_id"])):
        p.append("bad auto_learn_id")
    if rec["risk"] not in RISKS:
        p.append("bad risk %r" % rec["risk"])
    if rec["scope_recommendation"] not in SCOPES:
        p.append("bad scope_recommendation %r" % rec["scope_recommendation"])
    if rec["status"] not in STATES:
        p.append("bad status %r" % rec["status"])
    if not str(rec["proposed_learning"]).strip():
        p.append("empty proposed_learning")
    if not rec["evidence"]:
        p.append("a suggestion with NO evidence is not allowed")
    return p
