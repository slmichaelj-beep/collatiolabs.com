"""truth.ledger — the append-only Truth Ledger file: .anima/<name>.truth.jsonl.

One JSON event per line; never edited, never rewritten. The CURRENT truth of any claim is
derived by folding the whole ledger (truth.query) — supersession and retraction are new lines,
not mutations. A redirected store (certs) is honoured via the `store` argument.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import schema


def default_store() -> Path:
    return Path(os.environ.get("ANIMA_STORE", ".anima"))


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.truth.jsonl"


def emit(name: str, event: dict, store: Path | None = None) -> dict:
    """Validate + append one event. Raises on an invalid event — silence is never truth."""
    problems = schema.validate(event)
    if problems:
        raise ValueError("refusing to append invalid event: " + "; ".join(problems))
    p = path_for(name, store)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def record(name: str, subject: str, claim: str, claim_type: str, *, store: Path | None = None,
           **kw) -> dict:
    """make + emit in one step (the common path)."""
    return emit(name, schema.make(subject, claim, claim_type, **kw), store=store)


def load(name: str, store: Path | None = None) -> list[dict]:
    """Every event, in append order. A malformed line is surfaced as a system/unsupported marker
    (never silently dropped — a corrupt ledger line is itself a truth problem)."""
    p = path_for(name, store)
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"event_id": "te_corrupt%07d" % i, "claim_type": "system",
                        "active_status": "conflict", "subject": "ledger",
                        "claim": "CORRUPT LINE %d — unparseable ledger entry" % (i + 1),
                        "_corrupt": True})
    return out
