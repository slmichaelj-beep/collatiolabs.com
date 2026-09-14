"""collatio.entity — the canonical Collatio Labs LLC profile + company records vault.

Unknown entity facts (jurisdiction, EIN, address, ownership, tax classification, registered agent)
stay `unknown_until_verified` — Vera never invents them. A verified fact requires an evidence ref.
The records vault tracks formation/tax/banking/contract/IP/compliance documents; a missing record
creates a task (never a fake fact); expired records surface; secrets are never stored raw.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

ENTITY_ID = "collatio_labs_llc"
UNKNOWN = "unknown_until_verified"
RECORD_TYPES = ("formation", "operating_agreement", "tax", "banking", "contract", "ip", "compliance",
                "insurance", "filing", "approval", "professional_review")
RECORD_STATUS = ("missing", "uploaded", "verified", "needs_review", "expired", "superseded")
SENSITIVITY = ("low", "medium", "high", "restricted")


def profile(name: str, *, store: Path | None = None) -> dict:
    p = storage.load(name, "collatio_entity", store, default=None)
    if not p:
        p = {"entity_id": ENTITY_ID, "legal_name": "Collatio Labs LLC", "entity_type": "LLC",
             "jurisdiction": UNKNOWN, "formation_date": UNKNOWN, "status": "unknown",
             "registered_agent": UNKNOWN, "principal_address": UNKNOWN, "mailing_address": UNKNOWN,
             "owners_members_managers": [], "tax_classification": UNKNOWN, "ein_status": "unknown",
             "banking_status": "none", "accounting_system": "none",
             "default_operating_authority": "L0_think_only",
             "professional_contacts": {"attorney": None, "cpa": None, "bookkeeper": None,
                                       "patent_attorney": None},
             "truth_refs": [], "evidence_refs": [], "last_verified_at": None}
        storage.save(name, "collatio_entity", p, store)
        storage.emit_truth(name, "collatio_entity", ENTITY_ID,
                           "ENTITY profile created (facts unknown until verified)", actor="user", store=store)
    return p


def verify_fact(name: str, field: str, value, *, evidence_ref: str, store: Path | None = None) -> dict:
    """Set a verified entity fact. Refused without an evidence ref (no invented facts)."""
    if not (evidence_ref or "").strip():
        return {"ok": False, "error": "a verified entity fact requires an evidence ref — refused"}
    p = profile(name, store=store)
    if field not in p:
        return {"ok": False, "error": "unknown entity field %r" % field}
    p[field] = value
    p["evidence_refs"].append(evidence_ref)
    p["last_verified_at"] = storage.now()
    storage.save(name, "collatio_entity", p, store)
    storage.emit_truth(name, "collatio_entity", ENTITY_ID, "ENTITY verified: %s" % field,
                       actor="user", evidence_refs=[evidence_ref], store=store)
    return {"ok": True, "profile": p}


# ---- company records vault ----
def _recs(name, store): return storage.load(name, "collatio_records", store, default={"records": []})["records"]
def _save_recs(name, a, store): storage.save(name, "collatio_records", {"records": a}, store)


def register_record(name: str, *, record_type: str, title: str, storage_ref: str = "",
                    sensitivity: str = "low", status: str = "uploaded", effective_date: str = "",
                    due_date: str = "", professional_review_required: bool = False,
                    store: Path | None = None) -> dict:
    if record_type not in RECORD_TYPES:
        return {"ok": False, "error": "unknown record type %r" % record_type}
    if "secret" in (storage_ref or "").lower() or "password" in (storage_ref or "").lower():
        return {"ok": False, "error": "raw secrets are not stored in records — use a vault ref"}
    rec = {"record_id": "rec_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID,
           "record_type": record_type, "title": title, "storage_ref": storage_ref,
           "sensitivity": sensitivity if sensitivity in SENSITIVITY else "low",
           "status": status if status in RECORD_STATUS else "uploaded",
           "effective_date": effective_date, "expiration_or_due_date": due_date,
           "review_required": status == "needs_review",
           "professional_review_required": professional_review_required,
           "truth_refs": [], "evidence_refs": []}
    a = _recs(name, store); a.append(rec); _save_recs(name, a, store)
    return {"ok": True, "record": rec}


def note_missing(name: str, *, record_type: str, title: str, store: Path | None = None) -> dict:
    """A missing record becomes a tracked task with status=missing — never a fabricated fact."""
    return register_record(name, record_type=record_type, title=title, status="missing", store=store)


def records(name: str, store: Path | None = None) -> dict:
    a = _recs(name, store)
    return {"ok": True, "records": a,
            "missing": [r["title"] for r in a if r["status"] == "missing"],
            "expired": [r["title"] for r in a if r["status"] == "expired"],
            "restricted": [r["title"] for r in a if r["sensitivity"] == "restricted"]}
