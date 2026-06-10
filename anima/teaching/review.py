"""teaching.review — the pre-approval review payload: proposed wording, scope, duration, risk,
evidence, target store, CONFLICTS, and the rollback plan. The user decides with everything visible.
"""
from __future__ import annotations

from pathlib import Path

from . import queue


def conflicts(name: str, rec: dict, store: Path | None = None) -> list[dict]:
    """Existing approved teachings + active memory events this record would collide with, each
    annotated with WHO WINS under the conflict policy (truth.supersession.wins)."""
    out = []
    try:
        from anima.truth import supersession as sup
        new_ev = {"claim_type": "teaching", "scope": ("project" if rec.get("scope") == "project"
                                                      else "long_term"),
                  "created_at": rec.get("created_at", "")}
        words = set((rec.get("content") or "").lower().split())
        for other in queue.load(name, store):
            if (other.get("teaching_id") != rec.get("teaching_id")
                    and other.get("approval_state") == "approved"
                    and other.get("type") == rec.get("type")):
                overlap = words & set((other.get("content") or "").lower().split())
                if len(overlap) >= max(2, len(words) // 4):
                    old_ev = {"claim_type": "teaching", "scope": ("project"
                              if other.get("scope") == "project" else "long_term"),
                              "created_at": other.get("created_at", "")}
                    out.append({"kind": "teaching", "id": other["teaching_id"],
                                "content": other.get("content", "")[:140],
                                "new_wins": sup.wins(new_ev, old_ev)})
        from anima.truth import query as tq
        for ev in tq.active(name, store=store):
            if ev.get("claim_type") in ("memory", "correction"):
                overlap = words & set((ev.get("claim") or "").lower().split())
                if len(overlap) >= max(2, len(words) // 4):
                    out.append({"kind": "memory", "id": ev["event_id"],
                                "content": ev.get("claim", "")[:140],
                                "new_wins": sup.wins({"claim_type": "teaching",
                                                      "scope": "long_term",
                                                      "created_at": rec.get("created_at", "")},
                                                     ev)})
    except Exception:
        pass
    return out


def payload(name: str, rec: dict, store: Path | None = None) -> dict:
    """Everything the user sees BEFORE deciding."""
    return {
        "proposed_wording": rec.get("content"),
        "type": rec.get("type"),
        "scope": rec.get("scope"),
        "duration": rec.get("expires_at") or ("until revoked" if rec.get("scope") in
                                              ("until_revoked", "long_term", "behavior")
                                              else rec.get("scope")),
        "risk": rec.get("risk"),
        "evidence": rec.get("evidence_turns") or [],
        "target_store": rec.get("target_store"),
        "conflicts": conflicts(name, rec, store=store),
        "rollback_plan": ("approval allocates a rollback id; Rollback retracts the persisted "
                          "memory/policy, marks the record rolled_back, and emits a Truth Ledger "
                          "event — fully reversible"),
        "controls": ["Approve", "Edit", "Reject", "Remember for this chat only",
                     "Never learn this", "Rollback"],
    }
