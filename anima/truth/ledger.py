"""truth.ledger — the append-only Truth Ledger file: .anima/<name>.truth.jsonl.

One JSON event per line; never edited, never rewritten. The CURRENT truth of any claim is
derived by folding the whole ledger (truth.query) — supersession and retraction are new lines,
not mutations. A redirected store (certs) is honoured via the `store` argument.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from anima import secure_store

from . import schema

# Module-level store, so hermetic certs (gate0_prime_experience._temp_store) can redirect the
# Truth Ledger the SAME way every other store-bearing module is redirected — keeping the real
# .anima byte-identical during a cert. ANIMA_STORE env still wins when set.
STORE = Path(".anima")


def default_store() -> Path:
    env = os.environ.get("ANIMA_STORE")
    return Path(env) if env else STORE


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.truth.jsonl"


def emit(name: str, event: dict, store: Path | None = None) -> dict:
    """Validate + append one event. Raises on an invalid event — silence is never truth."""
    problems = schema.validate(event)
    if problems:
        raise ValueError("refusing to append invalid event: " + "; ".join(problems))
    secure_store.append_jsonl(path_for(name, store), event)
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
    for i, line in enumerate(secure_store.read_jsonl_lines(p)):
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
