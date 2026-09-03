"""truth.schema — the Truth Ledger event: one bounded, validated shape for every claim Vera makes.

A Truth Ledger event records ONE claim, where it came from (provenance), what supports it
(evidence), what it replaced (supersession), and whether it is still active. The ledger is
APPEND-ONLY: an event is never edited; its CURRENT state is derived by folding later events
(supersedes / retraction) over it — see truth.query.fold().
"""
from __future__ import annotations

import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

CLAIM_TYPES = ("memory", "source", "inference", "correction", "teaching", "pack_fact",
               "system", "unsupported")
PROVENANCE_KINDS = ("user_turn", "assistant_turn", "source", "memory_record",
                    "teaching_record", "knowledge_pack", "system_cert")
SCOPES = ("chat", "project", "long_term", "knowledge_pack", "system")
ACTIVE_STATUSES = ("active", "superseded", "retracted", "expired", "unsupported", "conflict")
ACTORS = ("user", "vera", "system", "cert")
RISKS = ("low", "medium", "high", "sensitive")

REQUIRED = ("event_id", "subject", "claim", "claim_type", "provenance", "evidence_refs", "scope",
            "confidence", "supersedes", "superseded_by", "active_status", "created_at", "commit",
            "actor", "risk")

_ID_RX = re.compile(r"^te_[0-9a-f]{12}$")


def new_id() -> str:
    return "te_" + uuid.uuid4().hex[:12]


def head_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def make(subject: str, claim: str, claim_type: str, *, provenance_kind: str,
         provenance_refs: list | None = None, evidence_refs: list | None = None,
         scope: str = "chat", confidence: float = 0.0, supersedes: list | None = None,
         actor: str = "system", risk: str = "low", active_status: str = "active") -> dict:
    """Build a schema-complete event. Raises ValueError on a vocabulary violation — a claim that
    fits no bounded shape must never enter the ledger silently."""
    ev = {
        "event_id": new_id(),
        "subject": str(subject or "")[:200],
        "claim": str(claim or "")[:2000],
        "claim_type": claim_type,
        "provenance": {"kind": provenance_kind, "refs": list(provenance_refs or [])[:40]},
        "evidence_refs": list(evidence_refs or [])[:40],
        "scope": scope,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "supersedes": list(supersedes or [])[:20],
        "superseded_by": [],
        "active_status": active_status,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": head_commit(),
        "actor": actor,
        "risk": risk,
    }
    problems = validate(ev)
    if problems:
        raise ValueError("invalid truth event: " + "; ".join(problems))
    return ev


def validate(ev: dict) -> list[str]:
    """Every reason this event is NOT a valid ledger event ([] == valid)."""
    p: list[str] = []
    if not isinstance(ev, dict):
        return ["event is not a dict"]
    for k in REQUIRED:
        if k not in ev:
            p.append("missing field %r" % k)
    if p:
        return p
    if not _ID_RX.match(str(ev["event_id"])):
        p.append("bad event_id %r" % ev["event_id"])
    if ev["claim_type"] not in CLAIM_TYPES:
        p.append("bad claim_type %r" % ev["claim_type"])
    prov = ev.get("provenance") or {}
    if not isinstance(prov, dict) or prov.get("kind") not in PROVENANCE_KINDS:
        p.append("bad provenance %r" % prov)
    if ev["scope"] not in SCOPES:
        p.append("bad scope %r" % ev["scope"])
    if ev["active_status"] not in ACTIVE_STATUSES:
        p.append("bad active_status %r" % ev["active_status"])
    if ev["actor"] not in ACTORS:
        p.append("bad actor %r" % ev["actor"])
    if ev["risk"] not in RISKS:
        p.append("bad risk %r" % ev["risk"])
    try:
        c = float(ev["confidence"])
        if not (0.0 <= c <= 1.0):
            p.append("confidence out of [0,1]")
    except Exception:
        p.append("confidence not a number")
    if not isinstance(ev["supersedes"], list) or not isinstance(ev["superseded_by"], list):
        p.append("supersedes/superseded_by must be lists")
    return p
