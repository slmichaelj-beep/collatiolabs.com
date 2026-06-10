"""teaching.queue — the persisted Teaching queue: .anima/<name>.teaching.json.

Records transition (pending -> approved/rejected/edited/expired/rolled_back) with an append-only
per-record transition log; the file itself is rewritten atomically but no transition is ever
erased. A redirected store (certs) is honoured via the `store` argument.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import schema


def default_store() -> Path:
    return Path(os.environ.get("ANIMA_STORE", ".anima"))


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.teaching.json"


def load(name: str, store: Path | None = None) -> list[dict]:
    try:
        return json.loads(path_for(name, store).read_text()).get("records", [])
    except Exception:
        return []


def _save(name: str, records: list[dict], store: Path | None = None) -> None:
    p = path_for(name, store)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "records": records}, indent=1, ensure_ascii=False))
    tmp.replace(p)


def propose(name: str, rec: dict, store: Path | None = None) -> dict:
    problems = schema.validate(rec)
    if problems:
        raise ValueError("refusing invalid teaching record: " + "; ".join(problems))
    records = load(name, store)
    records.append(rec)
    _save(name, records, store)
    return rec


def get(name: str, teaching_id: str, store: Path | None = None) -> dict | None:
    for r in load(name, store):
        if r.get("teaching_id") == teaching_id:
            return r
    return None


def update(name: str, teaching_id: str, *, to_state: str | None = None, by: str = "user",
           patch: dict | None = None, store: Path | None = None) -> dict | None:
    """Apply a state transition and/or field patch — the transition log is append-only."""
    records = load(name, store)
    for r in records:
        if r.get("teaching_id") == teaching_id:
            if patch:
                r.update(patch)
            if to_state:
                r["approval_state"] = to_state
                r.setdefault("transitions", []).append(
                    {"at": schema.now(), "to": to_state, "by": by})
            problems = schema.validate(r)
            if problems:
                raise ValueError("transition would invalidate the record: " + "; ".join(problems))
            _save(name, records, store)
            return r
    return None


def pending(name: str, store: Path | None = None) -> list[dict]:
    return [r for r in load(name, store) if r.get("approval_state") in ("pending", "edited")]


def active_do_not_learn(name: str, store: Path | None = None) -> list[dict]:
    """Approved do-not-learn rules — every learning path must consult these."""
    return [r for r in load(name, store)
            if r.get("type") == "do_not_learn" and r.get("approval_state") == "approved"]


def blocked_by_do_not_learn(name: str, text: str, store: Path | None = None) -> dict | None:
    """The do-not-learn rule that blocks learning `text`, or None. Substring match on the
    rule's content (lowercased) — conservative: when in doubt, it blocks."""
    low = (text or "").lower()
    for r in active_do_not_learn(name, store):
        key = (r.get("content") or "").lower().strip()
        if key and key in low:
            return r
    return None


def sweep_expired(name: str, store: Path | None = None) -> list[str]:
    """Expire every until_date record whose expires_at has passed. Returns expired ids."""
    out = []
    records = load(name, store)
    now = schema.now()
    changed = False
    for r in records:
        if (r.get("scope") == "until_date" and r.get("expires_at")
                and r["expires_at"] <= now and r.get("approval_state") == "approved"):
            r["approval_state"] = "expired"
            r.setdefault("transitions", []).append({"at": now, "to": "expired", "by": "system"})
            out.append(r["teaching_id"])
            changed = True
    if changed:
        _save(name, records, store)
    return out
