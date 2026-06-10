"""knowledge_packs.schema — a Knowledge Pack: curated domain knowledge. DATA, never policy.

Packs are source-grounded expertise. They are NOT behavior instructions, NOT user memory, NOT
system policy. Pack content can never mutate memory, override system rules, alter release/cert
status, change the host profile, or affect consent. The lifecycle is bounded and no pack is
retrievable before it has been evaluated.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

LIFECYCLE = ("added", "quarantined", "indexed", "evaluated", "ready", "stale", "disabled",
             "removed")
OWNERS = ("user", "system", "organization")
INJECTION_RISKS = ("low", "medium", "high")
CERT_STATUSES = ("green", "amber", "red", "unknown")

# the ONLY allowed-use vocabulary — anything else is refused at validation
ALLOWED_USES = ("retrieval", "citation", "summarization", "teaching_draft_evidence")
# uses that are NEVER allowed, encoded as a hard list (the cert proves they are refused)
FORBIDDEN_USES = ("behavior_instruction", "memory_write", "system_rule", "release_status",
                  "cert_status", "host_profile", "consent_override", "auto_learn_persistence")

REQUIRED = ("pack_id", "name", "domain", "version", "owner", "sources", "lifecycle_status",
            "allowed_uses", "disallowed_uses", "citation_policy", "confidence_policy",
            "safety_boundaries", "prompt_injection_risk", "last_indexed_at", "cert_status",
            "created_at", "transitions")

_ID_RX = re.compile(r"^kp_[0-9a-f]{12}$")

# the lifecycle's legal transitions — anything else is refused
TRANSITIONS = {
    "added": ("quarantined",),
    "quarantined": ("indexed", "removed"),
    "indexed": ("evaluated", "removed"),
    "evaluated": ("ready", "disabled", "removed"),
    "ready": ("stale", "disabled", "removed"),
    "stale": ("indexed", "disabled", "removed"),
    "disabled": ("indexed", "removed"),
    "removed": (),
}


def new_id() -> str:
    return "kp_" + uuid.uuid4().hex[:12]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make(name: str, domain: str, *, owner: str = "user", sources: list | None = None,
         version: str = "1", citation_policy: str = "every retrieved chunk carries its source ref",
         confidence_policy: str = "pack facts never outrank user memory",
         safety_boundaries: list | None = None) -> dict:
    rec = {
        "pack_id": new_id(),
        "name": str(name or "")[:200],
        "domain": str(domain or "")[:200],
        "version": str(version),
        "owner": owner,
        "sources": list(sources or [])[:200],
        "lifecycle_status": "added",
        "allowed_uses": list(ALLOWED_USES),
        "disallowed_uses": list(FORBIDDEN_USES),
        "citation_policy": citation_policy,
        "confidence_policy": confidence_policy,
        "safety_boundaries": list(safety_boundaries or
                                  ["pack text is DATA, never instruction",
                                   "no memory mutation", "no system-rule override"]),
        "prompt_injection_risk": "medium",      # until evaluated, assume medium
        "last_indexed_at": None,
        "cert_status": "unknown",
        "created_at": now(),
        "transitions": [{"at": now(), "to": "added", "by": "owner"}],
    }
    problems = validate(rec)
    if problems:
        raise ValueError("invalid pack: " + "; ".join(problems))
    return rec


def validate(rec: dict) -> list[str]:
    p: list[str] = []
    if not isinstance(rec, dict):
        return ["pack is not a dict"]
    for k in REQUIRED:
        if k not in rec:
            p.append("missing field %r" % k)
    if p:
        return p
    if not _ID_RX.match(str(rec["pack_id"])):
        p.append("bad pack_id")
    if rec["lifecycle_status"] not in LIFECYCLE:
        p.append("bad lifecycle_status %r" % rec["lifecycle_status"])
    if rec["owner"] not in OWNERS:
        p.append("bad owner %r" % rec["owner"])
    if rec["prompt_injection_risk"] not in INJECTION_RISKS:
        p.append("bad prompt_injection_risk %r" % rec["prompt_injection_risk"])
    if rec["cert_status"] not in CERT_STATUSES:
        p.append("bad cert_status %r" % rec["cert_status"])
    bad_uses = [u for u in rec["allowed_uses"] if u not in ALLOWED_USES]
    if bad_uses:
        p.append("allowed_uses outside the bounded vocabulary: %s" % bad_uses)
    missing_forbidden = [u for u in FORBIDDEN_USES if u not in rec["disallowed_uses"]]
    if missing_forbidden:
        p.append("disallowed_uses must carry every hard boundary (missing: %s)" % missing_forbidden)
    return p
