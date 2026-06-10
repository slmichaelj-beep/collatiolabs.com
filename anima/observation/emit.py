"""observation.emit — the one call every system uses to record a trace-linked event.

record() snapshots the LIVE governance state (authority level, kill switch, external/spending/
legal posture) so every event shows where the system stood when it happened. Fully guarded: an
emit failure never breaks the caller (returns None).
"""
from __future__ import annotations

from pathlib import Path

from . import schema, store


def governance_snapshot(name: str, store_path: Path | None = None) -> dict:
    """The live governance posture for the event. Default is the safe one (L0 think-only)."""
    level = 0
    killed = False
    try:
        from anima.company_operator import authority, kill_switch
        level = authority.current_level(name, store_path)
        killed = kill_switch.is_engaged(name, store_path)
    except Exception:
        pass
    return {
        "authority_level": "L%d" % level,
        "external_actions_enabled": level >= 3 and not killed,
        "spending_enabled": level >= 4 and not killed,
        "legal_financial_human_only": True,
        "kill_switch_active": bool(killed),
    }


def record(name: str, surface: str, system: str, action: str, *, actor: str = "user",
           result: str = "success", classification: str = "real", trace_id: str | None = None,
           truth_refs=None, decision_refs=None, approval_refs=None, budget_refs=None,
           action_refs=None, report_refs=None, cert_refs=None, store_path: Path | None = None) -> dict | None:
    try:
        gs = governance_snapshot(name, store_path)
        ev = schema.make(surface, system, action, actor=actor,
                         authority_level=gs["authority_level"], governance_state=gs,
                         truth_refs=truth_refs, decision_refs=decision_refs,
                         approval_refs=approval_refs, budget_refs=budget_refs,
                         action_refs=action_refs, report_refs=report_refs, cert_refs=cert_refs,
                         result=result, classification=classification, trace_id=trace_id)
        store.append(name, ev, store_path)
        return ev
    except Exception:
        return None
