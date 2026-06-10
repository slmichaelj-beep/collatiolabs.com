"""truth.supersession — corrections and retractions as APPEND-only chain links.

A correction never edits the old event: it appends a new one carrying `supersedes=[old_id]`.
The conflict policy (who wins) is encoded here in one place:

    user correction        > older memory
    explicit teaching      > inferred preference
    project rule           > general preference inside that project
    safety/system policy   > teaching
    newer same-scope correction > older same-scope record
    a source fact does NOT override user memory unless explicitly accepted
"""
from __future__ import annotations

from pathlib import Path

from . import ledger, schema

# claim-type precedence for conflicts (higher wins). The directive's order, bounded.
_PRECEDENCE = {
    "system": 60,          # safety/system policy beats everything below
    "correction": 50,      # an explicit user correction
    "teaching": 40,        # explicit teaching
    "memory": 30,          # a stored user memory
    "source": 20,          # a source fact never silently overrides user memory
    "pack_fact": 15,
    "inference": 10,       # an inferred preference loses to all of the above
    "unsupported": 0,
}


def wins(new_ev: dict, old_ev: dict) -> bool:
    """Does new_ev beat old_ev under the conflict policy? Same class -> newer wins iff same
    scope; a project-scoped rule beats a general (long_term) preference inside the project."""
    np = _PRECEDENCE.get(new_ev.get("claim_type"), 0)
    op = _PRECEDENCE.get(old_ev.get("claim_type"), 0)
    if np != op:
        return np > op
    if new_ev.get("scope") == "project" and old_ev.get("scope") == "long_term":
        return True                                   # project rule inside the project
    if new_ev.get("scope") == old_ev.get("scope"):
        return (new_ev.get("created_at", "") >= old_ev.get("created_at", ""))
    return False


def supersede(name: str, old_event_ids: list[str], subject: str, claim: str, *,
              claim_type: str = "correction", provenance_kind: str = "user_turn",
              provenance_refs: list | None = None, evidence_refs: list | None = None,
              scope: str = "long_term", confidence: float = 0.97, actor: str = "user",
              risk: str = "low", store: Path | None = None) -> dict:
    """Append the superseding event. The old events become superseded at fold time."""
    ev = schema.make(subject, claim, claim_type, provenance_kind=provenance_kind,
                     provenance_refs=provenance_refs, evidence_refs=evidence_refs, scope=scope,
                     confidence=confidence, supersedes=list(old_event_ids), actor=actor, risk=risk)
    return ledger.emit(name, ev, store=store)


def retract(name: str, old_event_ids: list[str], subject: str, *, reason: str,
            provenance_kind: str = "user_turn", provenance_refs: list | None = None,
            actor: str = "user", store: Path | None = None) -> dict:
    """Append a retraction: a correction event whose own status is 'retracted' — the chain link
    that closes the old claims without asserting a replacement value."""
    ev = schema.make(subject, "RETRACTED: " + reason, "correction",
                     provenance_kind=provenance_kind, provenance_refs=provenance_refs,
                     scope="long_term", confidence=1.0, supersedes=list(old_event_ids),
                     actor=actor, risk="low", active_status="retracted")
    return ledger.emit(name, ev, store=store)
