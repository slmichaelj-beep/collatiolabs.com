"""market_vision.source_registry — the only sources Vera may scan.

A source must be approved, lawful, and policy-classified before it can produce an active signal.
Blocked sources cannot be scanned; needs_review sources cannot back an active claim; citation-
required sources cannot yield an uncited claim; high-PII sources route to review. This is the hard
gate the signal intake engine consults.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

SOURCE_TYPES = ("web", "review", "forum", "repo", "doc", "sales", "support", "market_report",
                "patent", "job_posting", "pricing", "social")
LEGAL = ("approved", "needs_review", "blocked")
STATUS = ("approved", "quarantined", "blocked", "needs_review")
# behaviors that are never permitted regardless of source status
FORBIDDEN = ("illegal_scraping", "credentialed_access_without_approval", "bypass_robots_or_terms",
             "private_data_collection", "platform_abuse", "contact_harvesting_for_spam",
             "leaked_or_nonpublic_data", "copyright_beyond_summary")

# seeded honestly: only sources that are genuinely lawful + public + Lamar-owned
SEED = [
    ("Lamar's repos/assets/docs", "doc", "local_file", "static", "low"),
    ("Vera sales conversations", "sales", "local_file", "manual", "low"),
    ("Lamar-owned product support", "support", "local_file", "manual", "medium"),
    ("Public competitor pricing pages", "pricing", "public_fetch", "weekly", "low"),
    ("Public app/software reviews", "review", "approved_api", "weekly", "low"),
    ("Public job postings", "job_posting", "public_fetch", "weekly", "low"),
    ("Open-source / public repo trends", "repo", "approved_api", "weekly", "low"),
    ("Uploaded market reports (Lamar-supplied)", "market_report", "uploaded", "manual", "low"),
]


def _all(name, store): return storage.load(name, "mv_sources", store, default={"sources": []})["sources"]
def _save(name, a, store): storage.save(name, "mv_sources", {"sources": a}, store)


def seed(name: str, *, store: Path | None = None) -> dict:
    existing = {s["name"] for s in _all(name, store)}
    a = _all(name, store); added = []
    for nm, stype, access, fresh, pii in SEED:
        if nm in existing:
            continue
        rec = {"source_id": "src_" + uuid.uuid4().hex[:12], "name": nm, "source_type": stype,
               "access_method": access, "allowed_use": ["research", "signal_extraction", "citation"],
               "forbidden_use": list(FORBIDDEN), "freshness_policy": fresh,
               "legal_policy": "approved", "citation_required": True, "pii_risk": pii,
               "status": "needs_review" if pii == "high" else "approved",
               "last_checked_at": storage.now(), "truth_refs": []}
        a.append(rec); added.append(nm)
        storage.emit_truth(name, "mv_source", rec["source_id"], "SOURCE registered: " + nm,
                           actor="user", store=store)
    _save(name, a, store)
    return {"ok": True, "added": added, "total": len(a)}


def add_source(name: str, source_name: str, source_type: str, *, access_method: str = "public_fetch",
               legal_policy: str = "needs_review", pii_risk: str = "low", citation_required: bool = True,
               store: Path | None = None) -> dict:
    rec = {"source_id": "src_" + uuid.uuid4().hex[:12], "name": source_name,
           "source_type": source_type if source_type in SOURCE_TYPES else "web",
           "access_method": access_method, "allowed_use": ["research", "signal_extraction"],
           "forbidden_use": list(FORBIDDEN), "freshness_policy": "manual",
           "legal_policy": legal_policy if legal_policy in LEGAL else "needs_review",
           "citation_required": citation_required, "pii_risk": pii_risk,
           "status": ("needs_review" if (legal_policy != "approved" or pii_risk == "high") else "approved"),
           "last_checked_at": storage.now(), "truth_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    return {"ok": True, "source": rec}


def get(name: str, source_id: str, *, store: Path | None = None) -> dict | None:
    return next((s for s in _all(name, store) if s["source_id"] == source_id), None)


def can_scan(name: str, source_id: str, *, intended_use: str = "signal_extraction",
             behavior: str | None = None, store: Path | None = None) -> dict:
    """The scan gate. A blocked/quarantined/needs_review source cannot be scanned for active
    signals; a forbidden behavior is refused regardless of source."""
    s = get(name, source_id, store=store)
    if s is None:
        return {"allowed": False, "reason": "no such source"}
    if behavior in FORBIDDEN:
        return {"allowed": False, "reason": "forbidden behavior: %s" % behavior}
    if s["legal_policy"] == "blocked" or s["status"] == "blocked":
        return {"allowed": False, "reason": "source blocked (legal/policy)"}
    if s["status"] == "quarantined":
        return {"allowed": False, "reason": "source quarantined"}
    if s["status"] == "needs_review" or s["legal_policy"] == "needs_review":
        return {"allowed": False, "reason": "source needs legal/policy review before active use",
                "needs_review": True}
    if s["pii_risk"] == "high":
        return {"allowed": False, "reason": "high PII risk — route to review", "needs_review": True}
    if intended_use not in s["allowed_use"]:
        return {"allowed": False, "reason": "use %r not in allowed_use" % intended_use}
    return {"allowed": True, "citation_required": s["citation_required"], "source_name": s["name"]}


def inventory(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "sources": a, "approved": [s["name"] for s in a if s["status"] == "approved"],
            "needs_review": [s["name"] for s in a if s["status"] == "needs_review"],
            "blocked": [s["name"] for s in a if s["status"] == "blocked"]}
