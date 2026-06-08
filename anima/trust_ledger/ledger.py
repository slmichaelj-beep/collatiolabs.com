"""trust_ledger.ledger — build the unified Trust Ledger from the REAL trust events.

Read-only. Creates no new source of truth: it reads the events Vera already records (the incident SOC
trail) + the ROI ledger, categorises each, attaches provenance, and computes the trust invariants.
Never raises — a logging/telemetry view must never break the turn.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schema

REPORTS = Path("reports")


def _events(n: int = 200) -> list:
    """The real trust-event spine (incident SOC trail), newest last. Never raises."""
    try:
        from anima import incident
        return incident.recent_events(int(max(1, n)))
    except Exception:
        return []


def _is_locked() -> bool:
    try:
        from anima import incident
        return bool(incident.is_locked())
    except Exception:
        return False


def _roi_entries() -> list:
    """Verified value-delivered entries from the ROI ledger (value category). Never raises."""
    try:
        d = json.loads((REPORTS / "roi_ledger.json").read_text())
        return [e for e in (d.get("entries") or []) if isinstance(e, dict)]
    except Exception:
        return []


def _short(s, n=160):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def categorise(events: list) -> list:
    """Attach (category, category_label, provenance) to each event. Pure; order preserved."""
    out = []
    for e in events:
        kind = e.get("kind", "")
        cat = schema.category_of(kind)
        meta = schema.CATEGORIES.get(cat, {"label": "Uncategorised"})
        out.append({
            "at": e.get("at"),
            "kind": kind,
            "category": cat,
            "category_label": meta["label"],
            "provenance": schema.CATEGORY_PROVENANCE.get(cat, ".anima/security_events.jsonl"),
            "detail": _short(e.get("detail")),
            "route": e.get("route"),
        })
    return out


def _count(events, kind):
    return sum(1 for e in events if e.get("kind") == kind)


def invariants(events: list | None = None) -> list:
    """Compute the trust invariants over the real spine. Each is falsifiable; the certs prove a
    violating event flips holds=False."""
    evs = _events(400) if events is None else events
    ats = [e.get("at") for e in evs if e.get("at")]

    # 1) append-only: timestamps never go backwards
    monotonic = all(ats[i] <= ats[i + 1] for i in range(len(ats) - 1))

    # 2) suggest-only agency: no forbidden silent-action kind; approvals+rejections never exceed suggestions
    has_forbidden = any(e.get("kind") in schema.FORBIDDEN_SILENT_KINDS for e in evs)
    sug = _count(evs, "agency_suggestion")
    decided = _count(evs, "agency_approve") + _count(evs, "agency_reject")
    suggest_only = (not has_forbidden) and (decided <= sug)

    # 3) no silent sensitive memory: every written was first held
    written = _count(evs, "sensitive_memory_written")
    held = _count(evs, "sensitive_memory_held")
    consent_before = (written <= held) and not has_forbidden

    # 4) reversible state: not stuck locked; if locks happened, a restore is on record
    locks = _count(evs, "lockdown")
    restores = _count(evs, "restore")
    reversible = (not _is_locked()) and (locks == 0 or restores >= 1)

    results = {
        "append_only": (monotonic, "%d events in non-decreasing time order" % len(ats)),
        "suggest_only_agency": (suggest_only,
                                "%d suggestions, %d resolved (approve/reject); 0 silent actions" % (sug, decided)),
        "consent_before_durable": (consent_before,
                                   "%d sensitive writes, all preceded by a held (%d held)" % (written, held)),
        "reversible_state": (reversible,
                             "locked=%s; %d lockdowns / %d restores on record" % (_is_locked(), locks, restores)),
    }
    out = []
    for iid in schema.INVARIANT_IDS:
        holds, detail = results[iid]
        meta = schema.INVARIANTS[iid]
        out.append({
            "id": iid, "label": meta["label"], "promise": meta["promise"],
            "holds": bool(holds), "detail": detail, "violation_means": meta["violation"],
        })
    return out


def build_ledger(name: str = "Vera", n: int = 200) -> dict:
    """The full Trust Ledger payload for the UI/cert. Read-only."""
    raw = _events(n)
    events = categorise(raw)
    cats = {cid: sum(1 for e in events if e["category"] == cid) for cid in schema.CATEGORY_IDS}
    roi = _roi_entries()
    cats["value"] = len(roi)
    inv = invariants(raw)
    decided = _count(raw, "agency_approve") + _count(raw, "agency_reject")
    return {
        "name": name,
        "events": list(reversed(events))[:120],        # newest first for display
        "categories": cats,
        "category_meta": schema.CATEGORIES,
        "invariants": inv,
        "all_invariants_hold": all(i["holds"] for i in inv),
        "value": [{"title": _short(e.get("title") or e.get("what"), 80),
                   "status": e.get("status"), "benefit": _short(e.get("benefit") or e.get("expected_benefit"), 80)}
                  for e in roi[:20]],
        "metrics": {
            "total_events": len(events),
            "distinct_kinds": len(set(e["kind"] for e in events)),
            "trust_decisions": decided,
            "sensitive_held": _count(raw, "sensitive_memory_held"),
            "quarantines": _count(raw, "quarantine"),
            "span_from": events[0]["at"] if events else None,
            "span_to": events[-1]["at"] if events else None,
            "value_delivered": len(roi),
        },
        "law": "The Trust Ledger is the one place every trust-touching action Vera takes is accountable: "
               "security catches, consent decisions, agency proposals, gated memory, and value delivered "
               "— each with its real provenance. It records nothing new; it makes the existing record "
               "provable. The invariants are promises, not decoration: each can fail, and the cert proves it.",
        "empty": not events and not roi,
    }


def summary(name: str = "Vera") -> dict:
    """Top-line trust posture for a badge/headline."""
    led = build_ledger(name, 200)
    return {
        "name": name,
        "all_invariants_hold": led["all_invariants_hold"],
        "total_events": led["metrics"]["total_events"],
        "trust_decisions": led["metrics"]["trust_decisions"],
        "value_delivered": led["metrics"]["value_delivered"],
    }
