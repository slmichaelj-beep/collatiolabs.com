"""truth.query — derive CURRENT truth from the append-only ledger.

fold() walks the ledger once: an event listed in a later event's `supersedes` is superseded; a
later `correction`/retraction targeting it closes it; everything else keeps its written status.
trace() returns the full chain for one claim — the dashboard's "why is this shown?" answer.
"""
from __future__ import annotations

from pathlib import Path

from . import ledger


def fold(name: str, store: Path | None = None) -> dict:
    """{event_id: event} with DERIVED active_status + superseded_by filled in."""
    events = ledger.load(name, store)
    by_id = {}
    for seq, ev in enumerate(events):
        eid = ev.get("event_id")
        if eid:
            by_id[eid] = dict(ev, _seq=seq)     # copy — the ledger itself is never mutated;
                                                # _seq = append order (the tiebreak for same-second events)
    for ev in events:
        for old in ev.get("supersedes") or []:
            tgt = by_id.get(old)
            if tgt is not None:
                tgt["active_status"] = ("retracted"
                                        if (ev.get("claim_type") == "correction"
                                            and ev.get("active_status") == "retracted")
                                        else "superseded")
                sb = tgt.setdefault("superseded_by", [])
                if ev.get("event_id") not in sb:
                    sb.append(ev.get("event_id"))
    return by_id


def active(name: str, subject: str | None = None, claim_type: str | None = None,
           store: Path | None = None) -> list[dict]:
    """Currently-active events, optionally filtered by subject and/or claim_type."""
    out = []
    for ev in fold(name, store).values():
        if ev.get("active_status") != "active":
            continue
        if subject is not None and ev.get("subject") != subject:
            continue
        if claim_type is not None and ev.get("claim_type") != claim_type:
            continue
        out.append(ev)
    return sorted(out, key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)))


def by_id(name: str, event_id: str, store: Path | None = None) -> dict | None:
    return fold(name, store).get(event_id)


def trace(name: str, event_id: str, store: Path | None = None) -> list[dict]:
    """The full supersession chain through `event_id` — oldest first. This is the provenance a
    displayed claim must be able to show."""
    folded = fold(name, store)
    if event_id not in folded:
        return []
    # walk backwards through everything this chain superseded, then forwards through supersessors
    chain_ids, frontier = set([event_id]), [event_id]
    while frontier:
        cur = folded[frontier.pop()]
        for nxt in (cur.get("supersedes") or []) + (cur.get("superseded_by") or []):
            if nxt in folded and nxt not in chain_ids:
                chain_ids.add(nxt)
                frontier.append(nxt)
    return sorted((folded[i] for i in chain_ids),
                  key=lambda e: (e.get("created_at", ""), e.get("_seq", 0)))


def unsupported(name: str, store: Path | None = None) -> list[dict]:
    """Currently unresolved unsupported claims — the count the directive drives to ZERO."""
    return [ev for ev in fold(name, store).values()
            if ev.get("active_status") == "unsupported"]
