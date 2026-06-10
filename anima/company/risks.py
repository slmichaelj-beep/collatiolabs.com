"""company.risks — the Risk and Assumption register. What could hurt the company, tracked.

Risks and assumptions are durable, Truth-Ledger-traced records. An invalidated assumption can
never be used as a fact (status carries it); a high/critical risk surfaces in the founder briefing.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from . import storage

RISK_CATS = ("product", "technical", "security", "privacy", "business", "market", "legal",
             "operational", "founder")
RISK_SEV = ("low", "medium", "high", "critical")
RISK_STATUS = ("open", "mitigated", "accepted", "closed", "stale")
ASSUMPTION_STATUS = ("untested", "testing", "validated", "invalidated", "stale")


def _risks(name, store): return storage.load(name, "risks", store, default={"risks": []})["risks"]
def _save_risks(name, r, store): storage.save(name, "risks", {"risks": r}, store)
def _assumptions(name, store): return storage.load(name, "assumptions", store, default={"assumptions": []})["assumptions"]
def _save_assumptions(name, a, store): storage.save(name, "assumptions", {"assumptions": a}, store)


def add_risk(name, title, description, *, category="technical", severity="medium",
             likelihood="unknown", mitigation="", evidence_refs=None, store: Path | None = None) -> dict:
    rec = {"risk_id": "rsk_" + uuid.uuid4().hex[:12], "title": title[:200],
           "description": description[:2000],
           "category": category if category in RISK_CATS else "operational",
           "severity": severity if severity in RISK_SEV else "medium",
           "likelihood": likelihood, "status": "open", "owner": "Lamar",
           "mitigation": mitigation, "evidence_refs": evidence_refs or [],
           "truth_ledger_event": None, "review_date": None, "created_at": storage.now()}
    rec["truth_ledger_event"] = storage.emit_truth(name, "risk", rec["risk_id"],
                                                   "RISK[%s/%s]: %s" % (rec["category"], rec["severity"], title),
                                                   actor="user", risk="high" if severity in ("high", "critical") else "medium",
                                                   store=store)
    rs = _risks(name, store); rs.append(rec); _save_risks(name, rs, store)
    return {"ok": True, "risk": rec}


def set_risk_status(name, risk_id, status, store: Path | None = None) -> dict:
    rs = _risks(name, store)
    for r in rs:
        if r["risk_id"] == risk_id:
            r["status"] = status if status in RISK_STATUS else r["status"]
            _save_risks(name, rs, store)
            return {"ok": True, "risk": r}
    return {"ok": False, "error": "no such risk"}


def add_assumption(name, statement, *, category="product", confidence="medium",
                   proof_required="", evidence_refs=None, store: Path | None = None) -> dict:
    rec = {"assumption_id": "asm_" + uuid.uuid4().hex[:12], "statement": statement[:2000],
           "category": category, "confidence": confidence, "proof_required": proof_required,
           "status": "untested", "evidence_refs": evidence_refs or [], "owner": "Lamar",
           "truth_ledger_event": None, "review_date": None, "created_at": storage.now()}
    rec["truth_ledger_event"] = storage.emit_truth(name, "assumption", rec["assumption_id"],
                                                   "ASSUMPTION: " + statement[:160], actor="user",
                                                   store=store)
    a = _assumptions(name, store); a.append(rec); _save_assumptions(name, a, store)
    return {"ok": True, "assumption": rec}


def set_assumption_status(name, assumption_id, status, store: Path | None = None) -> dict:
    a = _assumptions(name, store)
    for r in a:
        if r["assumption_id"] == assumption_id:
            r["status"] = status if status in ASSUMPTION_STATUS else r["status"]
            _save_assumptions(name, a, store)
            return {"ok": True, "assumption": r}
    return {"ok": False, "error": "no such assumption"}


def top_risks(name, store: Path | None = None) -> list:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted([r for r in _risks(name, store) if r["status"] == "open"],
                  key=lambda r: order.get(r["severity"], 9))


def stale_or_unproven_assumptions(name, store: Path | None = None) -> list:
    return [a for a in _assumptions(name, store)
            if a["status"] in ("untested", "testing", "stale")]


def is_usable_as_fact(name, assumption_id, store: Path | None = None) -> bool:
    """An invalidated (or unvalidated) assumption may never be used as a fact."""
    a = next((x for x in _assumptions(name, store) if x["assumption_id"] == assumption_id), None)
    return bool(a) and a["status"] == "validated"
