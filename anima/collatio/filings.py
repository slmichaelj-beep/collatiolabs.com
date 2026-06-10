"""collatio.filings — filing/compliance calendar + tax/accounting operating packets.

Vera prepares filing checklists and packets, reminds, and queues approval. Vera never files a legal
or tax document, never decides `not_applicable` without evidence/review, and never moves money. An
unknown jurisdiction blocks a specific due-date claim. Overdue filings surface in the briefing.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from .entity import ENTITY_ID, UNKNOWN

FILING_TYPES = ("annual_report", "tax", "license", "boi", "ip", "contract", "insurance", "domain",
                "account_verification")
FILING_STATUS = ("unknown", "not_started", "prepared", "approval_needed", "filed", "not_applicable",
                 "needs_professional_review", "overdue")


def _all(name, store): return storage.load(name, "collatio_filings", store, default={"filings": []})["filings"]
def _save(name, a, store): storage.save(name, "collatio_filings", {"filings": a}, store)


def create_filing(name: str, *, filing_type: str, description: str, jurisdiction: str = UNKNOWN,
                  due_date: str | None = None, professional_review_required: bool = True,
                  store: Path | None = None) -> dict:
    if filing_type not in FILING_TYPES:
        return {"ok": False, "error": "unknown filing type %r" % filing_type}
    # an unknown jurisdiction cannot carry a specific, authoritative due-date claim
    claimed_due = due_date if (jurisdiction != UNKNOWN and due_date) else None
    rec = {"filing_id": "fil_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID,
           "filing_type": filing_type, "jurisdiction": jurisdiction, "description": description,
           "due_date": claimed_due,
           "due_date_note": (None if claimed_due else "jurisdiction unverified — no authoritative due date"),
           "status": "not_started", "source_ref": "", "professional_review_required": professional_review_required,
           "approval_ref": None, "action_refs": [], "truth_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    storage.emit_truth(name, "collatio_filing", rec["filing_id"], "FILING task: " + description,
                       actor="user", store=store)
    return {"ok": True, "filing": rec}


def file_action(name: str, filing_id: str, *, approval_ref: str = "", store: Path | None = None) -> dict:
    """Mark a filing as filed. REFUSED without approval — Vera never files on its own."""
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "filing requires explicit approval — Vera does not file"}
    a = _all(name, store)
    for r in a:
        if r["filing_id"] == filing_id:
            r["status"] = "filed"; r["approval_ref"] = approval_ref; _save(name, a, store)
            return {"ok": True, "filing": r, "note": "recorded as filed by human; Vera did not file"}
    return {"ok": False, "error": "no such filing"}


def calendar(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "filings": a, "overdue": [r["description"] for r in a if r["status"] == "overdue"],
            "approval_needed": [r["description"] for r in a if r["status"] == "approval_needed"]}


# ---- tax / accounting packets (prepare only) ----
def build_packet(name: str, *, packet_type: str, items: list, store: Path | None = None) -> dict:
    """Prepare a bookkeeper/CPA/monthly-close packet. Never files taxes, never moves money."""
    PT = ("monthly_close", "cpa_packet", "bookkeeper_packet", "tax_document_checklist",
          "runway_report", "budget_variance", "sales_tax_applicability")
    if packet_type not in PT:
        return {"ok": False, "error": "unknown packet type %r" % packet_type}
    rec = {"packet_id": "pkt_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID,
           "packet_type": packet_type, "items": list(items), "status": "prepared",
           "filing_action": "NONE — tax filing + bank movement are human/professional-only",
           "created_at": storage.now()}
    storage.save(name, "collatio_packet_%s" % rec["packet_id"], rec, store)
    return {"ok": True, "packet": rec}
