"""teaching.schema — the Teaching record: structured learning with evidence, scope, approval,
rollback, and Truth Ledger integration. Teaching is NOT uncontrolled memory: nothing persists
without explicit approval, everything persisted is traceable and reversible.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

TYPES = ("preference", "project_rule", "behavior_rule", "concept", "method", "correction",
         "domain_note", "do_not_learn")
SOURCES = ("direct_user", "correction", "file", "conversation", "manual_entry",
           "auto_learn_draft", "pack_import")
SCOPES = ("chat", "project", "until_date", "until_revoked", "long_term", "knowledge_pack",
          "behavior")
RISKS = ("low", "medium", "high", "sensitive")
APPROVAL_STATES = ("pending", "approved", "rejected", "edited", "expired", "rolled_back")
TARGET_STORES = ("memory", "knowledge_pack", "behavior_policy", "project_context")

REQUIRED = ("teaching_id", "type", "content", "evidence_turns", "source", "scope", "expires_at",
            "risk", "approval_state", "target_store", "truth_ledger_event", "rollback_id",
            "created_at", "transitions")

_ID_RX = re.compile(r"^th_[0-9a-f]{12}$")


def new_id() -> str:
    return "th_" + uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(type_: str, content: str, *, evidence_turns: list | None = None,
         source: str = "direct_user", scope: str = "long_term", expires_at: str | None = None,
         risk: str = "low", target_store: str = "memory") -> dict:
    rec = {
        "teaching_id": new_id(),
        "type": type_,
        "content": str(content or "")[:4000],
        "evidence_turns": list(evidence_turns or [])[:40],
        "source": source,
        "scope": scope,
        "expires_at": expires_at,
        "risk": risk,
        "approval_state": "pending",
        "target_store": target_store,
        "truth_ledger_event": None,
        "rollback_id": None,
        "created_at": now(),
        "transitions": [{"at": now(), "to": "pending", "by": "proposer"}],
    }
    problems = validate(rec)
    if problems:
        raise ValueError("invalid teaching record: " + "; ".join(problems))
    return rec


def validate(rec: dict) -> list[str]:
    p: list[str] = []
    if not isinstance(rec, dict):
        return ["record is not a dict"]
    for k in REQUIRED:
        if k not in rec:
            p.append("missing field %r" % k)
    if p:
        return p
    if not _ID_RX.match(str(rec["teaching_id"])):
        p.append("bad teaching_id")
    if rec["type"] not in TYPES:
        p.append("bad type %r" % rec["type"])
    if rec["source"] not in SOURCES:
        p.append("bad source %r" % rec["source"])
    if rec["scope"] not in SCOPES:
        p.append("bad scope %r" % rec["scope"])
    if rec["risk"] not in RISKS:
        p.append("bad risk %r" % rec["risk"])
    if rec["approval_state"] not in APPROVAL_STATES:
        p.append("bad approval_state %r" % rec["approval_state"])
    if rec["target_store"] not in TARGET_STORES:
        p.append("bad target_store %r" % rec["target_store"])
    if not rec["content"].strip():
        p.append("empty content")
    if rec["scope"] == "until_date" and not rec["expires_at"]:
        p.append("scope until_date requires expires_at")
    return p
