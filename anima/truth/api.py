"""truth.api — the organ-facing hooks. Every memory write, recall, retraction, source use, and
unsupported claim crosses HERE into the append-only ledger. Fully guarded: a ledger hiccup never
breaks a turn (errors return None), but a SUCCESSFUL write is always schema-valid.
"""
from __future__ import annotations

from pathlib import Path

from . import ledger, query, supersession


def _active_memory_event(name: str, subject: str, store: Path | None = None) -> dict | None:
    evs = query.active(name, subject=subject, claim_type="memory", store=store)
    return evs[-1] if evs else None


def on_memory_write(name: str, row: dict, user_text: str = "", turn_id: str = "",
                    store: Path | None = None) -> dict | None:
    """A LIRF row was written/updated from a user turn. Supersedes the prior active memory event
    for the same trait (a new value is a correction of the old, per the conflict policy)."""
    try:
        trait = row.get("trait") or "?"
        value = row.get("value")
        if (row.get("status") or "active") == "retracted":
            return on_memory_retraction(name, trait, row.get("id"), user_text, turn_id, store=store)
        prior = _active_memory_event(name, trait, store=store)
        refs = [r for r in (turn_id,) if r]
        ev_refs = [r for r in (row.get("id"),) if r]
        if prior is not None and prior.get("claim") != f"{trait} = {value}":
            return supersession.supersede(
                name, [prior["event_id"]], trait, f"{trait} = {value}",
                claim_type="correction", provenance_kind="user_turn", provenance_refs=refs,
                evidence_refs=ev_refs, scope="long_term",
                confidence=float(row.get("confidence") or 0.9), actor="user", store=store)
        if prior is not None:
            return prior                              # same value re-affirmed: no duplicate claim
        return ledger.record(name, trait, f"{trait} = {value}", "memory",
                             provenance_kind="user_turn", provenance_refs=refs,
                             evidence_refs=ev_refs, scope="long_term",
                             confidence=float(row.get("confidence") or 0.9), actor="user",
                             store=store)
    except Exception:
        return None


def on_memory_retraction(name: str, trait: str, row_id: str | None, user_text: str = "",
                         turn_id: str = "", store: Path | None = None) -> dict | None:
    """The user asked to forget: close every active memory/correction event for the trait."""
    try:
        olds = (query.active(name, subject=trait, claim_type="memory", store=store)
                + query.active(name, subject=trait, claim_type="correction", store=store))
        old_ids = [e["event_id"] for e in olds]
        if not old_ids:
            return None                              # nothing on record: a forget creates nothing
        return supersession.retract(name, old_ids, trait,
                                    reason="user asked to forget (%r)" % (user_text or "")[:120],
                                    provenance_refs=[r for r in (turn_id, row_id) if r],
                                    store=store)
    except Exception:
        return None


def on_memory_recall(name: str, row: dict, turn_id: str = "",
                     store: Path | None = None) -> dict | None:
    """A stored fact was USED in a reply (deterministic seam or bound model turn). Chat-scoped:
    the durable claim already exists; this is the displayed claim's traceable provenance."""
    try:
        return ledger.record(name, row.get("trait") or "?",
                             "recalled %s = %s" % (row.get("trait"), row.get("value")), "memory",
                             provenance_kind="memory_record",
                             provenance_refs=[r for r in (row.get("id"),) if r],
                             evidence_refs=[r for r in (turn_id,) if r], scope="chat",
                             confidence=float(row.get("confidence") or 0.9), actor="vera",
                             store=store)
    except Exception:
        return None


def on_source_use(name: str, sources: list, turn_id: str = "",
                  store: Path | None = None) -> list[dict]:
    """Source chips shipped with a reply — one source event per chip, traceable."""
    out = []
    for s in sources or []:
        try:
            sid = s.get("id") or s.get("source_id") or str(s)[:40] if isinstance(s, dict) else str(s)[:40]
            title = (s.get("title") or sid) if isinstance(s, dict) else sid
            out.append(ledger.record(name, sid, "answer grounded in source %r" % title, "source",
                                     provenance_kind="source", provenance_refs=[sid],
                                     evidence_refs=[r for r in (turn_id,) if r], scope="chat",
                                     confidence=0.9, actor="vera", store=store))
        except Exception:
            pass
    return out


def on_unsupported(name: str, phrases: list[str], excerpt: str, turn_id: str = "",
                   store: Path | None = None) -> dict | None:
    """The model shipped (and the guard rewrote) memory language with NO provenance — recorded,
    visible, and driven to zero."""
    try:
        return ledger.record(name, "memory_language",
                             "unsupported memory language %s in %r" % (phrases, excerpt[:160]),
                             "unsupported", provenance_kind="assistant_turn",
                             provenance_refs=[r for r in (turn_id,) if r], scope="chat",
                             confidence=0.0, actor="vera", risk="medium",
                             active_status="unsupported", store=store)
    except Exception:
        return None
