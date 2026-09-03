"""market_vision.signals — convert approved source material into cited market signals.

A signal is a weak, sourced observation: a complaint, a pricing pain, a privacy concern, a workflow
pain, an incumbent weakness, etc. RULES: one signal is not a market; a single complaint is weak
evidence; every active signal needs a source ref AND (for citation-required sources) a citation; a
blocked / unreviewed source cannot produce an active signal. Freshness is preserved from the source.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import source_registry

SIGNAL_TYPES = ("complaint", "pricing", "privacy", "workflow", "competitor", "feature_request",
                "trend", "asset_fit", "manual_admin", "bad_ux", "trust", "regulatory",
                "developer_pain", "open_source_gap", "service_to_software")
SEVERITY = ("low", "medium", "high")
CONFIDENCE = ("low", "medium", "high")


def _all(name, store): return storage.load(name, "mv_signals", store, default={"signals": []})["signals"]
def _save(name, a, store): storage.save(name, "mv_signals", {"signals": a}, store)


def extract(name: str, source_id: str, *, signal_type: str, text_summary: str, pain: str = "",
            evidence_excerpt_ref: str = "", customer_segment: str = "", industry: str = "",
            current_solution: str = "", severity: str = "low", frequency_hint: str = "single",
            store: Path | None = None) -> dict:
    """Extract one signal from an approved source. Refused if the source can't be scanned, or if a
    citation-required source has no evidence ref."""
    gate = source_registry.can_scan(name, source_id, store=store)
    if not gate["allowed"]:
        return {"ok": False, "error": "source cannot be scanned", "reason": gate}
    if gate.get("citation_required") and not (evidence_excerpt_ref or "").strip():
        return {"ok": False, "error": "citation-required source produced no evidence ref — refused"}
    rec = {"signal_id": "sig_" + uuid.uuid4().hex[:12], "source_id": source_id,
           "source_name": gate.get("source_name"), "signal_type": signal_type if signal_type in SIGNAL_TYPES else "trend",
           "text_summary": text_summary, "pain": pain, "evidence_excerpt_ref": evidence_excerpt_ref,
           "customer_segment": customer_segment, "industry": industry,
           "current_solution": current_solution,
           "severity": severity if severity in SEVERITY else "low",
           "frequency_hint": frequency_hint,
           # a single signal is weak by construction; clustering can raise this later
           "confidence": "low" if frequency_hint in ("single", "unknown") else "medium",
           "freshness": storage.now(), "truth_refs": [], "observation_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    storage.emit_truth(name, "mv_signal", rec["signal_id"],
                       "SIGNAL %s from %s" % (rec["signal_type"], rec["source_name"]),
                       actor="vera", store=store)
    return {"ok": True, "signal": rec}


def list_signals(name: str, *, signal_type: str | None = None, store: Path | None = None) -> list:
    a = _all(name, store)
    return [s for s in a if signal_type is None or s["signal_type"] == signal_type]


def by_ids(name: str, ids: list, store: Path | None = None) -> list:
    idset = set(ids)
    return [s for s in _all(name, store) if s["signal_id"] in idset]
