"""rollback.schema — the one rollback record shape, for every reversible surface."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

TARGET_KINDS = ("memory_correction", "forget_retraction", "teaching_record",
                "auto_learn_conversion", "knowledge_pack", "runtime_profile_override",
                "release_tier_classification")

REQUIRED = ("rollback_id", "target_kind", "target_event", "target_id", "previous_state",
            "new_state", "actor", "timestamp", "reason", "truth_ledger_event")

_ID_RX = re.compile(r"^rb_[0-9a-f]{12}$")


def new_id() -> str:
    return "rb_" + uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(target_kind: str, *, target_id: str, previous_state, new_state, reason: str,
         actor: str = "user", target_event: str | None = None,
         truth_ledger_event: str | None = None) -> dict:
    rec = {
        "rollback_id": new_id(),
        "target_kind": target_kind,
        "target_event": target_event,
        "target_id": target_id,
        "previous_state": previous_state,
        "new_state": new_state,
        "actor": actor,
        "timestamp": now(),
        "reason": str(reason or "")[:500],
        "truth_ledger_event": truth_ledger_event,
    }
    problems = validate(rec)
    if problems:
        raise ValueError("invalid rollback record: " + "; ".join(problems))
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
    if not _ID_RX.match(str(rec["rollback_id"])):
        p.append("bad rollback_id")
    if rec["target_kind"] not in TARGET_KINDS:
        p.append("bad target_kind %r" % rec["target_kind"])
    if not str(rec["target_id"]).strip():
        p.append("empty target_id")
    if not str(rec["reason"]).strip():
        p.append("empty reason")
    return p
