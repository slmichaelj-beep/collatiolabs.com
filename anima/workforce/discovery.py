"""workforce.discovery — work-gap scanner + unit classifier + product/service decision.

A work gap is repeatable, payable work someone needs done. Gaps draw on the Market Vision approved
source registry (a blocked source can't produce an active gap; a single weak signal stays low
confidence; regulated work is flagged). The classifier bands work by ticket size, and the lower the
ticket, the higher the automation requirement. The decision engine chooses product / service /
hybrid / audit / implementation / watch / kill — routing regulated work to professional review.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from anima.market_vision import source_registry as _src

TASK_TYPES = ("research", "cleanup", "audit", "support", "analysis", "content", "ops", "sales",
              "qa", "compliance", "admin", "technical")
UNIT_BANDS = ("micro", "small", "mid", "premium", "strategic")


def scan_work_gap(name: str, *, source_id: str, title: str, description: str, buyer_segment: str,
                  task_type: str, pain: str = "", frequency: str = "recurring",
                  automation_potential: str = "medium", human_review_need: str = "light",
                  risk_level: str = "low", evidence_refs: list | None = None,
                  store: Path | None = None) -> dict:
    """Detect a work gap from an approved source. Refused if the source can't be scanned."""
    gate = _src.can_scan(name, source_id, store=store)
    if not gate["allowed"]:
        return {"ok": False, "error": "source cannot be scanned", "reason": gate}
    evidence_refs = evidence_refs or []
    rec = {"work_gap_id": "wg_" + uuid.uuid4().hex[:10], "title": title, "description": description,
           "source_refs": [source_id], "buyer_segment": buyer_segment, "industry": "",
           "task_type": task_type if task_type in TASK_TYPES else "ops", "pain": pain,
           "frequency": frequency, "automation_potential": automation_potential,
           "human_review_need": human_review_need, "risk_level": risk_level,
           "ticket_size_estimate": "unknown",
           "confidence": "low" if len(evidence_refs) < 2 else "medium",
           "evidence_refs": list(evidence_refs), "truth_refs": [], "observation_refs": []}
    storage.save(name, "wf_gap_%s" % rec["work_gap_id"], rec, store)
    _idx(name, "wf_gap_index", rec["work_gap_id"], store)
    storage.emit_truth(name, "wf_gap", rec["work_gap_id"], "WORK GAP: " + title, actor="vera", store=store)
    return {"ok": True, "work_gap": rec}


def classify(name: str, work_gap_id: str, *, unit_type: str, price_per_unit: float, volume: int = 0,
             automation_requirement: str = "medium", support_burden: str = "low",
             store: Path | None = None) -> dict:
    """Classify a gap into a price band. Rule: micro/small work demands extreme/high automation;
    regulated work can't be micro-automated without review."""
    gap = storage.load(name, "wf_gap_%s" % work_gap_id, store, default=None)
    if not gap:
        return {"ok": False, "error": "no such work gap"}
    if unit_type not in UNIT_BANDS:
        return {"ok": False, "error": "bad unit band"}
    if unit_type == "micro" and automation_requirement not in ("high", "extreme"):
        return {"ok": False, "error": "micro-work requires extreme automation — refused"}
    if unit_type in ("micro", "small") and support_burden == "high":
        return {"ok": False, "error": "low-ticket work with high support burden is not viable"}
    if gap["risk_level"] == "regulated" and unit_type in ("micro", "small"):
        return {"ok": False, "error": "regulated work cannot be micro-automated without review"}
    rec_model = "product" if (unit_type in ("micro", "small") and automation_requirement == "extreme") \
        else "service" if unit_type in ("premium", "strategic") else "hybrid"
    gap.update({"unit_type": unit_type, "estimated_price_per_unit": price_per_unit,
                "estimated_volume": volume, "automation_requirement": automation_requirement,
                "support_burden": support_burden, "recommended_model": rec_model,
                "ticket_size_estimate": unit_type})
    storage.save(name, "wf_gap_%s" % work_gap_id, gap, store)
    return {"ok": True, "classification": {"unit_type": unit_type, "recommended_model": rec_model}}


def decide(name: str, work_gap_id: str, *, recommended_path: str, why: str,
           required_validation: list | None = None, confidence: str = "low",
           store: Path | None = None) -> dict:
    """Decide product/service/hybrid/audit/implementation/watch/kill. Regulated work routes to
    professional review; a low-confidence decision can't advance to build."""
    PATHS = ("product", "service", "hybrid", "audit", "implementation", "watch", "kill")
    gap = storage.load(name, "wf_gap_%s" % work_gap_id, store, default=None)
    if not gap:
        return {"ok": False, "error": "no such work gap"}
    if recommended_path not in PATHS:
        return {"ok": False, "error": "bad path"}
    path = recommended_path
    if gap["risk_level"] == "regulated" and path in ("product", "service", "hybrid"):
        path = "professional_review_required"
    can_build = confidence != "low" and path in ("product", "service", "hybrid")
    rec = {"decision_id": "dec_" + uuid.uuid4().hex[:10], "work_gap_id": work_gap_id,
           "recommended_path": path, "why": why,
           "required_validation": list(required_validation or ["unit economics", "demand check"]),
           "can_advance_to_build": can_build, "confidence": confidence}
    storage.save(name, "wf_decision_%s" % work_gap_id, rec, store)
    return {"ok": True, "decision": rec}


def _idx(name, idxkey, item_id, store):
    idx = storage.load(name, idxkey, store, default={"ids": []}); idx["ids"].append(item_id)
    storage.save(name, idxkey, idx, store)


def list_gaps(name, store=None) -> list:
    idx = storage.load(name, "wf_gap_index", store, default={"ids": []})["ids"]
    return [g for g in (storage.load(name, "wf_gap_%s" % i, store, default=None) for i in idx) if g]
